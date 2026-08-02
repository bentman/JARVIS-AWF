"""GPU-utilization sampler (Section 12.3): the Adversary/Optimizer role's
resource-safety probe. Ceiling: GPU utilization MUST NOT exceed 0.55 (55%)
at any point during a candidate's execution path.
"""

import subprocess

GPU_UTILIZATION_CEILING = 0.55


class GpuSamplerUnavailable(RuntimeError):
    pass


def sample_gpu_utilization() -> float:
    """Return current GPU utilization as a 0.0-1.0 fraction.

    Raises GpuSamplerUnavailable when no supported probe is available on
    this host (e.g. no NVIDIA GPU / no `nvidia-smi`) - callers MUST treat
    that as "cannot verify," never as "0% utilization."
    """
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise GpuSamplerUnavailable(f"nvidia-smi probe failed: {exc}") from exc

    if result.returncode != 0:
        raise GpuSamplerUnavailable(f"nvidia-smi exited {result.returncode}: {result.stderr.strip()}")

    first_line = result.stdout.strip().splitlines()[0] if result.stdout.strip() else ""
    try:
        percent = float(first_line)
    except ValueError as exc:
        raise GpuSamplerUnavailable(f"unexpected nvidia-smi output: {first_line!r}") from exc

    return percent / 100.0


def exceeds_ceiling(utilization: float) -> bool:
    return utilization > GPU_UTILIZATION_CEILING
