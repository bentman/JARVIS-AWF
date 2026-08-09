"""Managed LLM sidecar process runner and lifecycle controller (ADR-0017)."""

import json
import os
import signal
import subprocess
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from awf.hardware.profiler import SYSTEM_RUN_ID
from awf.llm.discovery import LocalModel, binary_path
from awf.llm.servers import Artifact, LlmServer

if TYPE_CHECKING:
    pass

HEALTH_TIMEOUT_SECONDS = 60.0
HEALTH_POLL_SECONDS = 0.5
STOP_TIMEOUT_SECONDS = 5.0

_TURN_ISOLATION_KEYS = {"cache_ram_mb", "cache_ram", "parallel", "cont_batching"}

_INT_KEYS = {"ctx_size", "batch_size", "ubatch_size", "main_gpu"}
_AUTO_INT_KEYS = {"threads", "threads_batch"}
_ALL_INT_KEYS = {"gpu_layers"}
_STR_KEYS = {"cache_type_k", "cache_type_v", "split_mode", "flash_attn", "device"}
_BOOL_KEYS = {"warmup"}

_FLAG_TRANSLATIONS = {
    "ctx_size": "--ctx-size",
    "threads": "--threads",
    "threads_batch": "--threads-batch",
    "batch_size": "--batch-size",
    "ubatch_size": "--ubatch-size",
    "gpu_layers": "--gpu-layers",
    "cache_type_k": "--cache-type-k",
    "cache_type_v": "--cache-type-v",
    "split_mode": "--split-mode",
    "main_gpu": "--main-gpu",
    "flash_attn": "--flash-attn",
    "device": "--device",
}

# Module-level state for managing single sidecar process per worker process lifetime
_SIDECAR_PROCESS: subprocess.Popen | None = None
_CURRENT_STATUS: "SidecarStatus | None" = None


def _state_path(repo_root: Path) -> Path:
    return repo_root / "cache" / "llm" / "sidecar.json"


def _log_path(repo_root: Path) -> Path:
    return repo_root / "cache" / "llm" / "sidecar.log"


def _write_state(repo_root: Path, status_obj: "SidecarStatus") -> None:
    path = _state_path(repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(status_obj.__dict__, indent=2, sort_keys=True), encoding="utf-8")


def _clear_state(repo_root: Path) -> None:
    path = _state_path(repo_root)
    if path.exists():
        path.unlink()


def _read_state(repo_root: Path) -> "SidecarStatus | None":
    path = _state_path(repo_root)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        warnings = data.get("warnings") or ()
        return SidecarStatus(
            state=data["state"],
            server_id=data.get("server_id"),
            base_url=data.get("base_url"),
            model_path=data.get("model_path"),
            profile_id=data.get("profile_id"),
            pid=data.get("pid"),
            adopted=bool(data.get("adopted")),
            warnings=tuple(warnings),
            reason=data.get("reason"),
        )
    except Exception:
        return None


def _pid_alive(pid: int | None) -> bool:
    if pid is None:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


@dataclass(frozen=True)
class Health:
    reachable: bool
    reason: str


@dataclass(frozen=True)
class Command:
    argv: tuple[str, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class SidecarStatus:
    state: str  # "running" | "adopted" | "stopped" | "degraded"
    server_id: str | None
    base_url: str | None
    model_path: str | None
    profile_id: str | None
    pid: int | None
    adopted: bool
    warnings: tuple[str, ...]
    reason: str | None


def probe(server: LlmServer) -> Health:
    last_reason = "No health paths declared"
    for path in server.health_paths:
        url = f"{server.base_url.rstrip('/')}{path}"
        req = urllib.request.Request(url, headers={"User-Agent": "AWF-HealthProbe/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                if 200 <= resp.status < 300:
                    return Health(reachable=True, reason=f"{path} reachable")
                last_reason = f"{path} returned HTTP {resp.status}"
        except Exception as exc:
            last_reason = f"{path} check failed: {exc}"

    return Health(reachable=False, reason=last_reason)


def _is_int_like(val: Any) -> bool:
    if isinstance(val, int) and not isinstance(val, bool):
        return True
    if isinstance(val, str):
        try:
            int(val)
            return True
        except ValueError:
            return False
    return False


def build_command(binary: Path, model_path: Path, base_url: str, launch: dict) -> Command:
    parsed_url = urllib.parse.urlparse(base_url)
    host = parsed_url.hostname or "127.0.0.1"
    port = str(parsed_url.port or 8080)

    argv: list[str] = [str(binary), "--model", str(model_path), "--host", host, "--port", port]
    warnings: list[str] = []

    for key, value in launch.items():
        if key in _TURN_ISOLATION_KEYS:
            warnings.append(f"launch key '{key}' is overridden by turn isolation")
            continue

        if key in _INT_KEYS:
            if _is_int_like(value):
                argv.extend([_FLAG_TRANSLATIONS[key], str(value)])
            else:
                warnings.append(f"unsupported launch value: {key}={value!r}")
        elif key in _AUTO_INT_KEYS:
            if value == "auto":
                argv.extend([_FLAG_TRANSLATIONS[key], "-1"])
            elif _is_int_like(value):
                argv.extend([_FLAG_TRANSLATIONS[key], str(value)])
            else:
                warnings.append(f"unsupported launch value: {key}={value!r}")
        elif key in _ALL_INT_KEYS:
            if value == "all":
                argv.extend([_FLAG_TRANSLATIONS[key], "all"])
            elif _is_int_like(value):
                argv.extend([_FLAG_TRANSLATIONS[key], str(value)])
            else:
                warnings.append(f"unsupported launch value: {key}={value!r}")
        elif key in _STR_KEYS:
            if isinstance(value, str):
                argv.extend([_FLAG_TRANSLATIONS[key], value])
            else:
                warnings.append(f"unsupported launch value: {key}={value!r}")
        elif key in _BOOL_KEYS:
            if isinstance(value, bool):
                argv.append("--warmup" if value else "--no-warmup")
            else:
                warnings.append(f"unsupported launch value: {key}={value!r}")
        else:
            warnings.append(f"unsupported launch key: {key}")

    # Turn isolation flags appended last and non-configurable
    argv.extend(["--cache-ram", "0", "--parallel", "1", "--no-cont-batching"])

    return Command(argv=tuple(argv), warnings=tuple(warnings))


def _record_event(conn: Any, reason_code: str, payload: dict) -> None:
    if conn is None:
        return
    try:
        from awf.events.writer import write_event
        from awf.hardware.profiler import _ensure_system_run

        _ensure_system_run(conn)
        write_event(
            conn,
            run_id=SYSTEM_RUN_ID,
            new_status="RESOLVED" if "started" in reason_code else "STOPPED",
            actor="sidecar",
            reason_code=reason_code,
            payload_json=json.dumps(payload, default=str),
        )
    except Exception:
        pass


def start(
    repo_root: Path,
    server: LlmServer,
    artifact: Artifact | None,
    model: LocalModel | None,
    conn: Any = None,
    *,
    detach: bool = False,
) -> SidecarStatus:
    global _SIDECAR_PROCESS, _CURRENT_STATUS

    # Step 1: Probe server - adopt if reachable
    health = probe(server)
    if health.reachable:
        model_p = str(model.primary) if model else None
        prof_id = artifact.profile_id if artifact else None
        status_obj = SidecarStatus(
            state="adopted",
            server_id=server.id,
            base_url=server.base_url,
            model_path=model_p,
            profile_id=prof_id,
            pid=None,
            adopted=True,
            warnings=(),
            reason="server reachable; adopted existing process",
        )
        _CURRENT_STATUS = status_obj
        _write_state(repo_root, status_obj)
        _record_event(
            conn,
            "llm_server_started",
            {
                "server_id": server.id,
                "base_url": server.base_url,
                "model_path": model_p,
                "profile_id": prof_id,
                "adopted": True,
                "pid": None,
                "argv": [],
                "warnings": [],
                "readiness": "adopted",
            },
        )
        return status_obj

    # Step 2: Validate binary and model presence

    if artifact is None:
        status_obj = SidecarStatus(
            state="degraded",
            server_id=server.id,
            base_url=server.base_url,
            model_path=str(model.primary) if model else None,
            profile_id=None,
            pid=None,
            adopted=False,
            warnings=(),
            reason="Degraded-no-sidecar-binary",
        )
        _CURRENT_STATUS = status_obj
        return status_obj

    target_bin = binary_path(repo_root, artifact.profile_id, artifact)
    if not target_bin.is_file() or target_bin.stat().st_size == 0:
        status_obj = SidecarStatus(
            state="degraded",
            server_id=server.id,
            base_url=server.base_url,
            model_path=str(model.primary) if model else None,
            profile_id=artifact.profile_id,
            pid=None,
            adopted=False,
            warnings=(),
            reason=f"Degraded-no-sidecar-binary: {target_bin}",
        )
        _CURRENT_STATUS = status_obj
        return status_obj

    if model is None or not model.primary.is_file():
        status_obj = SidecarStatus(
            state="degraded",
            server_id=server.id,
            base_url=server.base_url,
            model_path=str(model.primary) if model else None,
            profile_id=artifact.profile_id,
            pid=None,
            adopted=False,
            warnings=(),
            reason="Degraded-no-local-model-artifact",
        )
        _CURRENT_STATUS = status_obj
        return status_obj

    # Step 3: Build command and launch process
    cmd = build_command(target_bin, model.primary, server.base_url, artifact.launch)
    log_handle = None
    try:
        popen_kwargs: dict[str, Any] = {"cwd": target_bin.parent}
        if detach:
            log_path = _log_path(repo_root)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_handle = open(log_path, "ab")
            popen_kwargs.update({"stdout": log_handle, "stderr": subprocess.STDOUT, "start_new_session": True})
        proc = subprocess.Popen(cmd.argv, **popen_kwargs)
    except Exception as exc:
        if log_handle is not None:
            log_handle.close()
        status_obj = SidecarStatus(
            state="degraded",
            server_id=server.id,
            base_url=server.base_url,
            model_path=str(model.primary),
            profile_id=artifact.profile_id,
            pid=None,
            adopted=False,
            warnings=cmd.warnings,
            reason=f"Failed to spawn process: {exc}",
        )
        _CURRENT_STATUS = status_obj
        return status_obj

    _SIDECAR_PROCESS = proc

    # Step 4: Poll health until reachable or timeout
    start_time = time.time()
    while time.time() - start_time < HEALTH_TIMEOUT_SECONDS:
        if proc.poll() is not None:
            # Process terminated prematurely
            status_obj = SidecarStatus(
                state="degraded",
                server_id=server.id,
                base_url=server.base_url,
                model_path=str(model.primary),
                profile_id=artifact.profile_id,
                pid=None,
                adopted=False,
                warnings=cmd.warnings,
                reason=f"Process exited early with return code {proc.returncode}",
            )
            _SIDECAR_PROCESS = None
            _CURRENT_STATUS = status_obj
            if log_handle is not None:
                log_handle.close()
            return status_obj

        if probe(server).reachable:
            status_obj = SidecarStatus(
                state="running",
                server_id=server.id,
                base_url=server.base_url,
                model_path=str(model.primary),
                profile_id=artifact.profile_id,
                pid=proc.pid,
                adopted=False,
                warnings=cmd.warnings,
                reason=None,
            )
            if detach:
                _SIDECAR_PROCESS = None
                if log_handle is not None:
                    log_handle.close()
            _CURRENT_STATUS = status_obj
            _write_state(repo_root, status_obj)
            _record_event(
                conn,
                "llm_server_started",
                {
                    "server_id": server.id,
                    "base_url": server.base_url,
                    "model_path": str(model.primary),
                    "profile_id": artifact.profile_id,
                    "adopted": False,
                    "pid": proc.pid,
                    "argv": list(cmd.argv),
                    "warnings": list(cmd.warnings),
                    "readiness": "ready",
                },
            )
            return status_obj

        time.sleep(HEALTH_POLL_SECONDS)

    # Step 5: Timeout reached - terminate process
    try:
        proc.terminate()
        proc.wait(timeout=STOP_TIMEOUT_SECONDS)
    except Exception:
        proc.kill()

    _SIDECAR_PROCESS = None
    if log_handle is not None:
        log_handle.close()
    status_obj = SidecarStatus(
        state="degraded",
        server_id=server.id,
        base_url=server.base_url,
        model_path=str(model.primary),
        profile_id=artifact.profile_id,
        pid=None,
        adopted=False,
        warnings=cmd.warnings,
        reason="Degraded-health-timeout",
    )
    _CURRENT_STATUS = status_obj
    return status_obj


def stop(conn: Any = None, *, repo_root: Path | None = None) -> SidecarStatus:
    global _SIDECAR_PROCESS, _CURRENT_STATUS

    if _CURRENT_STATUS is not None and _CURRENT_STATUS.adopted:
        stopped_status = SidecarStatus(
            state="stopped",
            server_id=_CURRENT_STATUS.server_id,
            base_url=_CURRENT_STATUS.base_url,
            model_path=_CURRENT_STATUS.model_path,
            profile_id=_CURRENT_STATUS.profile_id,
            pid=None,
            adopted=True,
            warnings=(),
            reason="adopted server left running",
        )
        _record_event(
            conn,
            "llm_server_stopped",
            {
                "server_id": stopped_status.server_id,
                "base_url": stopped_status.base_url,
                "adopted": True,
                "reason": stopped_status.reason,
            },
        )
        _CURRENT_STATUS = stopped_status
        if repo_root is not None:
            _clear_state(repo_root)
        return stopped_status

    if _SIDECAR_PROCESS is not None:
        pid = _SIDECAR_PROCESS.pid
        server_id = _CURRENT_STATUS.server_id if _CURRENT_STATUS else None
        base_url = _CURRENT_STATUS.base_url if _CURRENT_STATUS else None
        model_p = _CURRENT_STATUS.model_path if _CURRENT_STATUS else None
        prof_id = _CURRENT_STATUS.profile_id if _CURRENT_STATUS else None

        try:
            _SIDECAR_PROCESS.terminate()
            _SIDECAR_PROCESS.wait(timeout=STOP_TIMEOUT_SECONDS)
        except Exception:
            _SIDECAR_PROCESS.kill()
            _SIDECAR_PROCESS.wait()

        _SIDECAR_PROCESS = None
        stopped_status = SidecarStatus(
            state="stopped",
            server_id=server_id,
            base_url=base_url,
            model_path=model_p,
            profile_id=prof_id,
            pid=pid,
            adopted=False,
            warnings=(),
            reason="process stopped",
        )
        _record_event(
            conn,
            "llm_server_stopped",
            {
                "server_id": server_id,
                "base_url": base_url,
                "adopted": False,
                "reason": "process stopped",
            },
        )
        _CURRENT_STATUS = stopped_status
        if repo_root is not None:
            _clear_state(repo_root)
        return stopped_status

    if repo_root is not None:
        stored = _read_state(repo_root)
        if stored is not None and stored.pid is not None and not stored.adopted and _pid_alive(stored.pid):
            try:
                os.kill(stored.pid, signal.SIGTERM)
                deadline = time.time() + STOP_TIMEOUT_SECONDS
                while time.time() < deadline and _pid_alive(stored.pid):
                    time.sleep(0.1)
                if _pid_alive(stored.pid):
                    os.kill(stored.pid, signal.SIGKILL)
            except OSError:
                pass
            stopped_status = SidecarStatus(
                state="stopped",
                server_id=stored.server_id,
                base_url=stored.base_url,
                model_path=stored.model_path,
                profile_id=stored.profile_id,
                pid=stored.pid,
                adopted=False,
                warnings=(),
                reason="process stopped",
            )
            _clear_state(repo_root)
            _CURRENT_STATUS = stopped_status
            return stopped_status

    stopped_status = SidecarStatus(
        state="stopped",
        server_id=None,
        base_url=None,
        model_path=None,
        profile_id=None,
        pid=None,
        adopted=False,
        warnings=(),
        reason="no sidecar running",
    )
    _CURRENT_STATUS = stopped_status
    if repo_root is not None:
        _clear_state(repo_root)
    return stopped_status


def status(server: LlmServer | None = None, *, repo_root: Path | None = None) -> SidecarStatus:
    if _CURRENT_STATUS is not None:
        return _CURRENT_STATUS

    if repo_root is not None:
        stored = _read_state(repo_root)
        if stored is not None:
            if stored.adopted:
                if server is not None and probe(server).reachable:
                    return stored
            elif _pid_alive(stored.pid):
                if server is None or probe(server).reachable:
                    return stored
            _clear_state(repo_root)

    if server is not None:
        h = probe(server)
        if h.reachable:
            return SidecarStatus(
                state="adopted",
                server_id=server.id,
                base_url=server.base_url,
                model_path=None,
                profile_id=None,
                pid=None,
                adopted=True,
                warnings=(),
                reason="server reachable; adopted",
            )

    return SidecarStatus(
        state="stopped",
        server_id=None,
        base_url=None,
        model_path=None,
        profile_id=None,
        pid=None,
        adopted=False,
        warnings=(),
        reason="no sidecar running",
    )
