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
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from awf.cognition.envelope import PromptEnvelope, PromptSegment
from awf.cognition.render import render_chat
from awf.gateway.client import LLM_COMPLETE_CAPABILITY_REF, complete
from awf.hardware.gpu_sampler import sample_gpu_utilization
from awf.hardware.profiler import run_hardware_profiler
from awf.memory.context import retrieve_memory_context
from awf.memory.sessions import SessionError, show_session
from awf.registry.model_profile import load_model_profile
from awf.registry.persona import compile_persona, load_persona
from awf.registry.resolve import resolve_registry_object

ActivityFn = Callable[[sqlite3.Connection, dict], dict]
ActivityKind = Literal["local", "machine"]


@dataclass(frozen=True)
class ActivityRegistration:
    kind: ActivityKind
    fn: ActivityFn | None = None


MACHINE_ACTIVITY_NAMES = frozenset({"fs_read", "fs_write", "fs_delete", "command_run", "network_fetch"})


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
    segments: list[PromptSegment] = [
        PromptSegment(
            "application",
            "instruction",
            True,
            "Answer the operator directly and concisely as the AWF resident mind.",
        )
    ]
    persona_ref = args.get("personaRef")
    if isinstance(persona_ref, str) and persona_ref.strip():
        persona_name, _, persona_version = persona_ref.partition("@")
        persona_path, _persona_source = resolve_registry_object(repo_root, "personas", persona_name, persona_version)
        persona = compile_persona(load_persona(persona_path))
        if persona.system_text.strip():
            segments.append(PromptSegment("persona", "style", True, persona.system_text))
    session_id = args.get("voiceSessionId") or args.get("sessionId")
    if isinstance(session_id, str) and session_id.strip():
        try:
            session = show_session(conn, session_id=session_id)
            for entry in session["entries"][-12:]:
                summary = entry.get("summary")
                content = entry.get("content") if isinstance(entry.get("content"), dict) else {}
                text = summary or content.get("text")
                if isinstance(text, str) and text.strip():
                    segments.append(PromptSegment("session", "context", False, f"{entry['role']}: {text.strip()}"))
        except SessionError:
            pass
    memory_profile_ref = str(args.get("memoryProfileRef") or "default@1.0.0")
    try:
        segments.extend(retrieve_memory_context(repo_root, conn, query=objective, profile_ref=memory_profile_ref))
    except Exception:
        pass
    segments.append(PromptSegment("user", "input", False, objective))
    envelope = PromptEnvelope(segments=tuple(segments))
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

    from awf.hardware.profiler import resolve_hardware_profile_id
    from awf.llm.artifacts import select_managed_llm_artifact
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
    profile_id, art = select_managed_llm_artifact(repo_root, server, profile_id)

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


ACTIVITY_REGISTRY: dict[str, ActivityRegistration] = {
    "assistant_reply": ActivityRegistration("local", _assistant_reply),
    "hardware_probe": ActivityRegistration("local", _hardware_probe),
    "gpu_utilization_sample": ActivityRegistration("local", _gpu_utilization_sample),
    "llm_server_ensure": ActivityRegistration("local", _llm_server_ensure),
    "fs_read": ActivityRegistration("machine"),
    "fs_write": ActivityRegistration("machine"),
    "fs_delete": ActivityRegistration("machine"),
    "command_run": ActivityRegistration("machine"),
    "network_fetch": ActivityRegistration("machine"),
}


class UnknownActivityError(RuntimeError):
    def __init__(self, message: str, *, failure_class: str = "INVALID_INPUT"):
        super().__init__(message)
        self.failure_class = failure_class
