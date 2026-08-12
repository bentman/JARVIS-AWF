"""`activity` node (Section 12.2): runs a registered deterministic/
side-effecting Python function by name - the node declares `function`
(a key into `ACTIVITY_REGISTRY`) and an optional `args` mapping.

`hardware_probe` is the R0 hardware-probe activity Section 12.3's Adversary
resource-safety obligation describes ("triggers an R0 hardware-probe
activity at Step boundaries") - registering it here gives a workflow a real,
durable way to invoke the Hardware Profiler mid-Run, not just at voice setup.
"""

import sqlite3
from collections.abc import Callable
from pathlib import Path

from awf.cognition.envelope import PromptEnvelope, PromptSegment
from awf.cognition.render import render_chat
from awf.gateway.client import LLM_COMPLETE_CAPABILITY_REF, complete
from awf.registry.model_profile import load_model_profile
from awf.registry.resolve import resolve_registry_object
from awf.hardware.gpu_sampler import sample_gpu_utilization
from awf.hardware.profiler import run_hardware_profiler

ActivityFn = Callable[[sqlite3.Connection, dict], dict]


def _hardware_probe(conn: sqlite3.Connection, _args: dict) -> dict:
    return {"profile_id": run_hardware_profiler(conn)}


def _gpu_utilization_sample(conn: sqlite3.Connection, _args: dict) -> dict:
    return {"utilization": sample_gpu_utilization()}


def _assistant_reply(conn: sqlite3.Connection, args: dict) -> dict:
    objective = str(args.get("objective", "")).strip()
    if not objective:
        return {"response_text": "I am ready. Send a request or choose a workflow to run."}
    context = args.get("_awf") if isinstance(args.get("_awf"), dict) else {}
    repo_root = Path(str(context.get("repo_root"))) if context.get("repo_root") else None
    run_id = str(context.get("run_id")) if context.get("run_id") else None
    step_id = str(context.get("step_id")) if context.get("step_id") else None
    if repo_root is None or run_id is None:
        raise RuntimeError("assistant_reply requires AWF run context")
    name, version = "resident-mind", "1.0.0"
    path, _source = resolve_registry_object(repo_root, "model-profiles", name, version, conn=conn)
    profile = load_model_profile(path)
    envelope = PromptEnvelope(
        segments=(
            PromptSegment(
                "application",
                "instruction",
                True,
                "Answer the operator directly and concisely as the AWF resident mind.",
            ),
            PromptSegment("user", "input", False, objective),
        )
    )
    return {
        "response_text": complete(
            profile,
            render_chat(envelope).messages,
            conn=conn,
            run_id=run_id,
            step_id=step_id,
            actor="assistant_reply",
            repo_root=repo_root,
            agent_allowlist=[LLM_COMPLETE_CAPABILITY_REF],
        )
    }


def _llm_server_ensure(conn: sqlite3.Connection, _args: dict) -> dict:
    from dataclasses import asdict

    from awf.cli.core_ops import _select_managed_llm_artifact
    from awf.hardware.profiler import resolve_hardware_profile_id
    from awf.llm.discovery import local_models, model_by_name
    from awf.llm.selector import current_selection
    from awf.llm.servers import load_servers
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
    profile_id, art = _select_managed_llm_artifact(repo_root, server, profile_id)

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

    st = start(repo_root, server, art, model, conn=conn, detach=True)
    return asdict(st)


def _machine_placeholder(conn: sqlite3.Connection, _args: dict) -> dict:
    raise RuntimeError("machine activities are executed by awf.machine.activities")


ACTIVITY_REGISTRY: dict[str, ActivityFn] = {
    "assistant_reply": _assistant_reply,
    "hardware_probe": _hardware_probe,
    "gpu_utilization_sample": _gpu_utilization_sample,
    "llm_server_ensure": _llm_server_ensure,
    "fs_read": _machine_placeholder,
    "fs_write": _machine_placeholder,
    "fs_delete": _machine_placeholder,
    "command_run": _machine_placeholder,
    "network_fetch": _machine_placeholder,
}


class UnknownActivityError(RuntimeError):
    def __init__(self, message: str, *, failure_class: str = "INVALID_INPUT"):
        super().__init__(message)
        self.failure_class = failure_class
