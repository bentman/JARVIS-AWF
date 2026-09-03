"""llm operation implementations."""

import sqlite3
from dataclasses import asdict
from pathlib import Path

from awf.llm.artifacts import cpu_fallback_profile_id, select_managed_llm_artifact
from awf.ops.shared import CoreOpError


def op_llm_servers(
    repo_root: Path,
    *,
    host_profile_id: str | None = None,
    probe_timeout_seconds: float = 2.0,
) -> dict:
    from awf.hardware.profiler import resolve_hardware_profile_id
    from awf.llm.discovery import binary_path, local_models
    from awf.llm.selector import current_selection
    from awf.llm.servers import artifact_for, load_servers
    from awf.llm.sidecar import probe

    default_id, servers = load_servers(repo_root)
    profile_id = host_profile_id
    if not profile_id:
        profile_id, _ = resolve_hardware_profile_id(repo_root)
    selection = current_selection(repo_root)
    models = local_models(repo_root)

    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, len(servers))) as executor:
        probe_futures = {
            s_id: executor.submit(probe, s, timeout_seconds=probe_timeout_seconds) for s_id, s in servers.items()
        }
        probed_health = {s_id: fut.result() for s_id, fut in probe_futures.items()}

    server_reports = {}
    for s_id, s in servers.items():
        h = probed_health[s_id]
        art = artifact_for(s, profile_id)
        bin_p = binary_path(repo_root, profile_id, art) if art else None

        server_reports[s_id] = {
            "managed": s.managed,
            "base_url": s.base_url,
            "provider": s.provider,
            "reachable": h.reachable,
            "reachability_reason": h.reason,
            "declared_artifact": art.profile_id if art else None,
            "binary_present": bin_p.is_file() if bin_p else False,
            "binary_path": str(bin_p) if bin_p else None,
            "local_models_available": [m.name for m in models] if s.managed else [],
        }

    return {
        "default_server": default_id,
        "host_profile_id": profile_id,
        "current_selection": asdict(selection) if selection else None,
        "servers": server_reports,
    }


def op_llm_models(repo_root: Path) -> dict:
    from awf.llm.discovery import local_models
    from awf.llm.servers import load_servers
    from awf.llm.sidecar import probe

    models = local_models(repo_root)
    res: dict[str, object] = {
        "local_models": [
            {
                "name": m.name,
                "primary": str(m.primary),
                "files": [str(f) for f in m.files],
            }
            for m in models
        ]
    }

    try:
        _, servers = load_servers(repo_root)
        if "ollama" in servers:
            ollama_s = servers["ollama"]
            h = probe(ollama_s)
            if h.reachable:
                import json
                import urllib.request

                url = f"{ollama_s.base_url.rstrip('/')}/api/tags"
                try:
                    with urllib.request.urlopen(url, timeout=2.0) as resp:
                        tags_data = json.loads(resp.read().decode())
                        res["ollama_models"] = tags_data.get("models", [])
                except Exception as exc:
                    res["ollama_models_error"] = str(exc)
    except Exception:
        pass

    return res


def op_llm_acquire(repo_root: Path) -> dict:
    from awf.hardware.profiler import resolve_hardware_profile_id
    from awf.llm.discovery import acquire_binary
    from awf.llm.servers import artifact_for, load_servers

    profile_id, _ = resolve_hardware_profile_id(repo_root)
    _, servers = load_servers(repo_root)

    llama_s = servers.get("llama-server")
    if llama_s is None:
        raise CoreOpError("llama-server is not declared in the llm-servers registry object")

    art = artifact_for(llama_s, profile_id)
    if art is not None and art.archive == "manual":
        cpu_profile_id = cpu_fallback_profile_id(profile_id)
        cpu_art = artifact_for(llama_s, cpu_profile_id)
        if cpu_art is not None and cpu_art.archive != "manual":
            profile_id, art = cpu_profile_id, cpu_art
    if art is None:
        raise CoreOpError(f"No artifact declared for canonical profile ID '{profile_id}'")

    try:
        return acquire_binary(repo_root, profile_id, art)
    except Exception as exc:
        raise CoreOpError(f"Failed to acquire binary for '{profile_id}': {exc}") from exc


def op_llm_select(
    repo_root: Path,
    conn: sqlite3.Connection,
    *,
    server_id: str,
    model: str | None = None,
    allow_remote: bool = False,
) -> dict:
    from awf.llm.selector import select
    from awf.llm.servers import LlmServerError

    try:
        return select(repo_root, conn, server_id=server_id, model=model, allow_remote=allow_remote)
    except LlmServerError as exc:
        raise CoreOpError(str(exc)) from exc


def op_llm_serve(
    repo_root: Path,
    conn: sqlite3.Connection,
    *,
    action: str,
    probe_timeout_seconds: float = 2.0,
) -> dict:
    from dataclasses import asdict

    from awf.hardware.profiler import resolve_hardware_profile_id
    from awf.llm.discovery import local_models, model_by_name
    from awf.llm.selector import current_selection
    from awf.llm.servers import load_servers
    from awf.llm.sidecar import start, status, stop

    default_id, servers = load_servers(repo_root)
    sel = current_selection(repo_root)

    if sel is not None and sel.server_id in servers:
        server = servers[sel.server_id]
        model_name = sel.model
    else:
        server = servers[default_id]
        model_name = None

    if action == "stop":
        st = stop(conn=conn, repo_root=repo_root)
        return asdict(st)

    if action == "status":
        st = status(server, repo_root=repo_root, probe_timeout_seconds=probe_timeout_seconds)
        return asdict(st)

    if action == "start":
        profile_id, _ = resolve_hardware_profile_id(repo_root)
        if server.managed:
            profile_id, art = select_managed_llm_artifact(repo_root, server, profile_id)
        else:
            art = None

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

    raise CoreOpError(f"Unknown serve action '{action}'. Valid: start, stop, status")


__all__ = ("op_llm_acquire", "op_llm_models", "op_llm_select", "op_llm_serve", "op_llm_servers")
