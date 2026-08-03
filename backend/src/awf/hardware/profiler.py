"""Hardware Profiler (Section 16.4): a deterministic probe that resolves the
host to exactly one canonical profile ID, run at Phase 12 voice setup and
before any voice model is downloaded or loaded.

Resolution order per arch is QNN/CUDA -> GPU -> CPU; every profile falls
back to its arch's `*64-cpu` floor. A profile above `-cpu` is valid only
when the execution provider actually loads (probe-verified), not merely
listed as available. WSL2 resolves as Linux (platform.system() == "Linux"
under WSL2, so no special-casing is needed).
"""

import platform
import sqlite3

from awf.clock import utc_now_rfc3339
from awf.events.writer import write_event

CANONICAL_PROFILES = (
    "windows-x64-cpu",
    "windows-x64-gpu",
    "windows-x64-cuda",
    "windows-arm64-cpu",
    "windows-arm64-gpu",
    "windows-arm64-qnn",
    "linux-x64-cpu",
    "linux-x64-gpu",
    "linux-x64-cuda",
    "linux-arm64-cpu",
    "linux-arm64-gpu",
    "linux-arm64-qnn",
)

SYSTEM_RUN_ID = "system"
SYSTEM_WORKFLOW_REF = "system@0.0.0"


class HardwareProfilerError(RuntimeError):
    pass


def _detect_os() -> str:
    system = platform.system()
    if system == "Windows":
        return "windows"
    if system == "Linux":
        return "linux"  # WSL2 reports "Linux" here - resolves as Linux, per spec
    raise HardwareProfilerError(f"unsupported OS for the canonical profile enum: {system}")


def _detect_arch() -> str:
    machine = platform.machine().lower()
    if machine in ("x86_64", "amd64"):
        return "x64"
    if machine in ("arm64", "aarch64"):
        return "arm64"
    raise HardwareProfilerError(f"unsupported architecture for the canonical profile enum: {machine}")


def _verify_provider_loads(provider: str) -> bool:
    """Probe-verify (not just list) that an ONNX Runtime execution provider
    actually loads, by trying to construct a session that requests it."""
    try:
        import onnxruntime as ort
    except ImportError:
        return False

    if provider not in ort.get_available_providers():
        return False

    # A minimal valid ONNX model (single Identity node) - enough to prove
    # the provider genuinely initializes, not just that its package exists.
    import onnx
    from onnx import TensorProto, helper

    node = helper.make_node("Identity", ["x"], ["y"])
    graph = helper.make_graph(
        [node],
        "probe",
        [helper.make_tensor_value_info("x", TensorProto.FLOAT, [1])],
        [helper.make_tensor_value_info("y", TensorProto.FLOAT, [1])],
    )
    model = helper.make_model(graph)
    try:
        session = ort.InferenceSession(model.SerializeToString(), providers=[provider])
        return provider in session.get_providers()
    except Exception:
        return False


def _probe_evidence(arch: str) -> dict:
    evidence: dict = {"available_providers": []}
    try:
        import onnxruntime as ort

        evidence["available_providers"] = ort.get_available_providers()
    except ImportError:
        pass

    if arch == "x64":
        evidence["cuda_verified"] = _verify_provider_loads("CUDAExecutionProvider")
        evidence["gpu_verified"] = _verify_provider_loads("ROCMExecutionProvider") or _verify_provider_loads(
            "DmlExecutionProvider"
        )
    else:
        evidence["qnn_verified"] = _verify_provider_loads("QNNExecutionProvider")
        evidence["gpu_verified"] = _verify_provider_loads("OpenVINOExecutionProvider")
    return evidence


def resolve_hardware_profile_id() -> tuple[str, dict]:
    os_name = _detect_os()
    arch = _detect_arch()
    evidence = _probe_evidence(arch)

    if arch == "x64":
        if evidence.get("cuda_verified"):
            return f"{os_name}-{arch}-cuda", evidence
        if evidence.get("gpu_verified"):
            return f"{os_name}-{arch}-gpu", evidence
        return f"{os_name}-{arch}-cpu", evidence

    # arm64
    if evidence.get("qnn_verified"):
        return f"{os_name}-{arch}-qnn", evidence
    if evidence.get("gpu_verified"):
        return f"{os_name}-{arch}-gpu", evidence
    return f"{os_name}-{arch}-cpu", evidence


def _ensure_system_run(conn: sqlite3.Connection) -> None:
    row = conn.execute("SELECT 1 FROM runs WHERE run_id = ?", (SYSTEM_RUN_ID,)).fetchone()
    if row is not None:
        return
    now = utc_now_rfc3339()
    conn.execute(
        "INSERT INTO runs (run_id, workflow_ref, status, input_json, budget_json, created_at, updated_at) "
        "VALUES (?, ?, 'SUCCEEDED', '{}', '{}', ?, ?)",
        (SYSTEM_RUN_ID, SYSTEM_WORKFLOW_REF, now, now),
    )
    conn.commit()


def run_hardware_profiler(conn: sqlite3.Connection) -> str:
    """Resolves the host's canonical profile ID and writes the resolution +
    probe evidence to the `events` table (Section 16.4), anchored to a
    permanent sentinel "system" Run since probing isn't scoped to any one
    Run."""
    profile_id, evidence = resolve_hardware_profile_id()
    _ensure_system_run(conn)
    import json

    write_event(
        conn,
        run_id=SYSTEM_RUN_ID,
        new_status="RESOLVED",
        actor="hardware_profiler",
        reason_code="hardware_profile_resolved",
        payload_json=json.dumps({"profile_id": profile_id, "evidence": evidence}),
    )
    return profile_id
