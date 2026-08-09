"""Per-speech-function device selection (ADR-0008).

The four functions run on three different runtimes - CTranslate2 for STT,
ONNX Runtime for TTS and VAD, openWakeWord's own loader for wake - so one
device string cannot describe all of them. Each `derive_*_readiness`
function grants a device above `cpu` only when both the hardware fact (from
`hardware.profiler.collect_inventory`) and the runtime token (from
`hardware.preflight.collect_preflight_tokens`) agree; either alone floors to
`cpu`, with a reason naming what was missing.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from awf.hardware.profiler import HardwareInventory
    from awf.llm.servers import LlmServer


_QNN_PROVIDER = "QNNExecutionProvider"
_CUDA_PROVIDER = "CUDAExecutionProvider"
_DML_PROVIDER = "DmlExecutionProvider"


@dataclass(frozen=True)
class Readiness:
    device: str
    ready: bool
    reason: str


def _ct2_cuda_count(tokens: list[str]) -> int:
    for token in tokens:
        if token.startswith("ct2:cuda:"):
            try:
                return int(token.rsplit(":", 1)[-1])
            except ValueError:
                return 0
    return 0


def derive_stt_readiness(inventory: "HardwareInventory", tokens: list[str]) -> Readiness:
    cuda_capable = inventory.gpu_vendor == "nvidia" and inventory.cuda_available and _ct2_cuda_count(tokens) > 0
    device = "cuda" if cuda_capable else "cpu"
    ready = "import:faster_whisper" in tokens
    if not ready:
        return Readiness(device="cpu", ready=False, reason="faster_whisper not importable")
    if device == "cuda":
        return Readiness(device="cuda", ready=True, reason="gpu_vendor=nvidia, cuda_available, ct2 cuda device present")
    return Readiness(device="cpu", ready=True, reason="no verified CUDA device for CTranslate2")


def derive_tts_readiness(inventory: "HardwareInventory", tokens: list[str]) -> Readiness:
    ready = "import:kokoro_onnx" in tokens
    if not ready:
        return Readiness(device="cpu", ready=False, reason="kokoro_onnx not importable")

    if inventory.gpu_vendor == "nvidia" and inventory.cuda_available and f"ep:{_CUDA_PROVIDER}" in tokens:
        return Readiness(
            device="cuda", ready=True, reason="gpu_vendor=nvidia, cuda_available, CUDAExecutionProvider available"
        )
    if inventory.os_name == "windows" and inventory.gpu_available and f"ep:{_DML_PROVIDER}" in tokens:
        return Readiness(device="directml", ready=True, reason="windows, gpu_available, DmlExecutionProvider available")
    if inventory.npu_vendor == "qualcomm" and f"ep:{_QNN_PROVIDER}" in tokens and "dll:QnnHtp" in tokens:
        return Readiness(
            device="qnn", ready=True, reason="npu_vendor=qualcomm, QNNExecutionProvider available, QnnHtp present"
        )
    return Readiness(device="cpu", ready=True, reason="no verified accelerator execution provider for ONNX Runtime")


def derive_vad_readiness(inventory: "HardwareInventory", tokens: list[str], artifact_path: Path | None) -> Readiness:
    del inventory  # VAD has no accelerator branch; kept for signature symmetry with the other three functions
    if "import:onnxruntime" not in tokens:
        return Readiness(device="cpu", ready=False, reason="onnxruntime not importable")
    if artifact_path is None or not artifact_path.is_file():
        return Readiness(device="cpu", ready=False, reason=f"artifact missing: {artifact_path}")

    import onnxruntime as ort

    try:
        session = ort.InferenceSession(str(artifact_path))
        input_names = {node.name for node in session.get_inputs()}
    except Exception as exc:
        return Readiness(device="cpu", ready=False, reason=f"session construction failed: {exc}")

    required = {"input", "sr", "h", "c"}
    if not required.issubset(input_names):
        return Readiness(
            device="cpu",
            ready=False,
            reason=f"artifact input names {sorted(input_names)} do not cover {sorted(required)}",
        )
    return Readiness(device="cpu", ready=True, reason="artifact present and input names match")


def derive_wake_readiness(
    inventory: "HardwareInventory", tokens: list[str], artifact_paths: dict[str, Path]
) -> Readiness:
    del inventory  # wake selects no execution provider; kept for signature symmetry
    if "import:openwakeword" not in tokens:
        return Readiness(device="cpu", ready=False, reason="openwakeword not importable")
    missing = sorted(name for name, path in artifact_paths.items() if not path.is_file())
    if missing:
        return Readiness(device="cpu", ready=False, reason=f"missing artifacts: {missing}")
    return Readiness(device="cpu", ready=True, reason="all wake artifacts present")


def derive_llm_readiness(
    inventory: "HardwareInventory",
    tokens: list[str],
    *,
    server: "LlmServer",
    profile_id: str,
    model_path: Path | None,
    repo_root: Path | None = None,
) -> Readiness:
    if not server.managed:
        return Readiness(
            device="cpu",
            ready=True,
            reason=f"{server.id} is operator-run; device is the server's own concern",
        )

    from awf.llm.discovery import binary_path
    from awf.paths import REPO_ROOT

    if repo_root is None:
        repo_root = REPO_ROOT

    cuda_hw = inventory.gpu_vendor == "nvidia" and inventory.cuda_available
    cuda_tok = "ep:CUDAExecutionProvider" in tokens

    qnn_hw = inventory.npu_vendor == "qualcomm" and inventory.npu_available
    qnn_tok = "ep:QNNExecutionProvider" in tokens and "dll:QnnHtp" in tokens

    adreno_hw = inventory.gpu_vendor == "qualcomm" and inventory.gpu_available
    adreno_tok = "opencl:adreno" in tokens
    vulkan_hw = inventory.gpu_available
    vulkan_tok = "vulkan:available" in tokens

    rungs = [
        ("gpu.cuda", cuda_hw, cuda_tok, "gpu_vendor=nvidia, cuda_available, ep:CUDAExecutionProvider"),
        ("npu.qnn", qnn_hw, qnn_tok, "npu_vendor=qualcomm, npu_available, ep:QNNExecutionProvider, dll:QnnHtp"),
        ("gpu.opencl.adreno", adreno_hw, adreno_tok, "gpu_vendor=qualcomm, gpu_available, opencl:adreno"),
        ("gpu.vulkan", vulkan_hw, vulkan_tok, "gpu_available, vulkan:available"),
        ("cpu", True, True, "cpu floor"),
    ]

    accelerator_unavailable_reason: str | None = None

    for rung_accel, hw_ok, tok_ok, desc in rungs:
        if hw_ok and tok_ok:
            art = server.artifacts.get(profile_id)
            if art is None or art.accelerator != rung_accel:
                if rung_accel != "cpu" and accelerator_unavailable_reason is None:
                    accelerator_unavailable_reason = (
                        f"Degraded-accelerator-unavailable: no {rung_accel} artifact declared for {profile_id}"
                    )
                continue

            bin_p = binary_path(repo_root, profile_id, art)
            if not bin_p.is_file() or bin_p.stat().st_size == 0:
                return Readiness(
                    device=rung_accel,
                    ready=False,
                    reason=f"Degraded-no-sidecar-binary: {bin_p}",
                )

            if model_path is None or not model_path.is_file():
                return Readiness(
                    device=rung_accel,
                    ready=False,
                    reason=f"Degraded-no-local-model-artifact: {model_path}",
                )

            if rung_accel == "cpu":
                if accelerator_unavailable_reason is not None:
                    return Readiness(device="cpu", ready=True, reason=accelerator_unavailable_reason)
                return Readiness(device="cpu", ready=True, reason="no verified accelerator artifact; running on cpu")

            return Readiness(
                device=rung_accel,
                ready=True,
                reason=f"{desc}, {rung_accel} artifact declared",
            )

    if accelerator_unavailable_reason is not None:
        return Readiness(device="cpu", ready=True, reason=accelerator_unavailable_reason)

    return Readiness(device="cpu", ready=True, reason="no verified accelerator artifact; running on cpu")
