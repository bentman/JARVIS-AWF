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
    cuda_capable = (
        inventory.gpu_vendor == "nvidia" and inventory.cuda_available and _ct2_cuda_count(tokens) > 0
    )
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
        return Readiness(device="cuda", ready=True, reason="gpu_vendor=nvidia, cuda_available, CUDAExecutionProvider available")
    if inventory.os_name == "windows" and inventory.gpu_available and f"ep:{_DML_PROVIDER}" in tokens:
        return Readiness(device="directml", ready=True, reason="windows, gpu_available, DmlExecutionProvider available")
    if inventory.npu_vendor == "qualcomm" and f"ep:{_QNN_PROVIDER}" in tokens and "dll:QnnHtp" in tokens:
        return Readiness(device="qnn", ready=True, reason="npu_vendor=qualcomm, QNNExecutionProvider available, QnnHtp present")
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
