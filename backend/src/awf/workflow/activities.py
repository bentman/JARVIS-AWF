"""`activity` node (Section 12.2): runs a registered deterministic/
side-effecting Python function by name - the node declares `function`
(a key into `ACTIVITY_REGISTRY`) and an optional `args` mapping.

`hardware_probe` is the R0 hardware-probe activity Section 12.3's Adversary
resource-safety obligation describes ("triggers an R0 hardware-probe
activity at Step boundaries") - registering it here gives a workflow a real,
durable way to invoke the Hardware Profiler mid-Run, not just at voice setup.
"""

import sqlite3
from typing import Callable

from awf.hardware.gpu_sampler import sample_gpu_utilization
from awf.hardware.profiler import run_hardware_profiler

ActivityFn = Callable[[sqlite3.Connection, dict], dict]


def _hardware_probe(conn: sqlite3.Connection, _args: dict) -> dict:
    return {"profile_id": run_hardware_profiler(conn)}


def _gpu_utilization_sample(conn: sqlite3.Connection, _args: dict) -> dict:
    return {"utilization": sample_gpu_utilization()}


ACTIVITY_REGISTRY: dict[str, ActivityFn] = {
    "hardware_probe": _hardware_probe,
    "gpu_utilization_sample": _gpu_utilization_sample,
}


class UnknownActivityError(RuntimeError):
    def __init__(self, message: str, *, failure_class: str = "INVALID_INPUT"):
        super().__init__(message)
        self.failure_class = failure_class
