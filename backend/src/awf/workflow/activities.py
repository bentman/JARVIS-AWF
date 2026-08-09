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


def _llm_server_ensure(conn: sqlite3.Connection, _args: dict) -> dict:
    from dataclasses import asdict

    from awf.hardware.profiler import resolve_hardware_profile_id
    from awf.llm.discovery import local_models, model_by_name
    from awf.llm.selector import current_selection
    from awf.llm.servers import artifact_for, load_servers
    from awf.llm.sidecar import start, status
    from awf.paths import REPO_ROOT

    repo_root = REPO_ROOT
    default_id, servers = load_servers(repo_root)
    sel = current_selection(repo_root)

    if sel is not None and sel.server_id in servers:
        server = servers[sel.server_id]
        model_name = sel.model
    else:
        server = servers[default_id]
        model_name = None

    if not server.managed:
        st = status(server)
        return asdict(st)

    profile_id, _ = resolve_hardware_profile_id(repo_root)
    art = artifact_for(server, profile_id)

    model = None
    if model_name:
        try:
            model = model_by_name(repo_root, model_name)
        except Exception:
            pass
    if model is None:
        avail = local_models(repo_root)
        if avail:
            model = avail[0]

    st = start(repo_root, server, art, model, conn=conn)
    return asdict(st)


ACTIVITY_REGISTRY: dict[str, ActivityFn] = {
    "hardware_probe": _hardware_probe,
    "gpu_utilization_sample": _gpu_utilization_sample,
    "llm_server_ensure": _llm_server_ensure,
}



class UnknownActivityError(RuntimeError):
    def __init__(self, message: str, *, failure_class: str = "INVALID_INPUT"):
        super().__init__(message)
        self.failure_class = failure_class
