"""Adversary/Optimizer role obligations (Section 12.3): resource safety,
safety-gate bypass, and memory contamination. Each check returns `None` when
no violation is found, else a `Finding`. Only run in the high-risk tier -
the default tier omits the Adversary/Optimizer pass entirely.
"""

import sqlite3
from pathlib import Path

from awf.gates.schema import Finding
from awf.hardware.gpu_sampler import (
    GPU_UTILIZATION_CEILING,
    GpuSamplerUnavailable,
    sample_gpu_utilization,
)


def check_resource_safety() -> Finding | None:
    try:
        utilization = sample_gpu_utilization()
    except GpuSamplerUnavailable:
        # Cannot verify on this host (e.g. no NVIDIA GPU) - not a violation.
        return None
    if utilization > GPU_UTILIZATION_CEILING:
        return Finding(
            role="adversary",
            category="resource_safety",
            severity="high",
            summary=f"GPU utilization {utilization:.0%} exceeded the {GPU_UTILIZATION_CEILING:.0%} ceiling",
            details={"utilization": utilization, "ceiling": GPU_UTILIZATION_CEILING},
        )
    return None


def check_safety_gate_bypass(guard_bypassed: bool, *, detail: str = "") -> Finding | None:
    if not guard_bypassed:
        return None
    return Finding(
        role="adversary",
        category="safety_gate_bypass",
        severity="critical",
        summary="Capability Guard was bypassed, circumvented, or silenced",
        details={"detail": detail},
    )


def check_memory_contamination(
    conn: sqlite3.Connection, run_id: str, cache_sandbox_dir: Path
) -> Finding | None:
    if not cache_sandbox_dir.is_dir():
        return None
    other_run_ids = {
        row["run_id"]
        for row in conn.execute("SELECT run_id FROM runs WHERE run_id != ?", (run_id,)).fetchall()
    }
    if not other_run_ids:
        return None
    for path in cache_sandbox_dir.rglob("*"):
        if any(other_id in path.name for other_id in other_run_ids):
            return Finding(
                role="adversary",
                category="memory_contamination",
                severity="high",
                summary=f"cache/sandbox/{run_id}/ contains an artifact referencing another run: {path.name}",
                details={"path": str(path)},
            )
    return None
