"""system operation implementations."""

import os
import shutil
import sqlite3
import subprocess
import sys
from dataclasses import asdict, is_dataclass
from pathlib import Path

from awf.envfile import get_env_value
from awf.paths import db_path as resolve_db_path
from awf.paths import env_path
from awf.pyexec import repo_python_executable
from awf.secrets.store import list_secret_names, set_secret


def _jsonable(value):
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, Path):
        return str(value)
    return value


def _doctor_check(name: str, status: str, summary: str, *, detail=None, next_action: str | None = None) -> dict:
    return {
        "name": name,
        "status": status,
        "summary": summary,
        "detail": _jsonable(detail or {}),
        "next_action": next_action,
    }


def _doctor_overall(checks: list[dict]) -> str:
    if any(check["status"] == "error" for check in checks):
        return "error"
    if any(check["status"] == "warn" for check in checks):
        return "warn"
    return "ok"


def _command_version(command: str, *args: str) -> tuple[bool, str | None]:
    executable = shutil.which(command)
    if executable is None:
        return False, None
    try:
        result = subprocess.run(
            [executable, *args],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception as exc:
        return True, str(exc)
    output = (result.stdout or result.stderr).strip().splitlines()
    return True, output[0] if output else None


def _doctor_python(repo_root: Path) -> dict:
    selected = repo_python_executable(repo_root)
    selected_path = selected[1] if selected else None
    current = Path(sys.executable)
    expected = Path(selected_path) if selected_path else None
    in_repo_venv = expected is not None and current.resolve() == expected.resolve()
    version_ok = (3, 12) <= sys.version_info[:2] < (3, 15)
    if not version_ok:
        return _doctor_check(
            "python",
            "error",
            f"Python {sys.version.split()[0]} is outside the supported >=3.12,<3.15 range.",
            detail={"executable": sys.executable, "expected": selected_path},
            next_action="Recreate backend/.venv with Python 3.12, 3.13, or 3.14.",
        )
    if not in_repo_venv:
        return _doctor_check(
            "python",
            "warn",
            "Current Python is supported but is not the repo venv interpreter.",
            detail={"executable": sys.executable, "expected": selected_path},
            next_action="Run commands through backend/.venv/Scripts/python.exe on Windows or backend/.venv/bin/python on Linux.",
        )
    return _doctor_check(
        "python",
        "ok",
        f"Using repo venv Python {sys.version.split()[0]}.",
        detail={"executable": sys.executable, "marker": selected[0] if selected else None},
    )


def _doctor_node(repo_root: Path) -> dict:
    node_present, node_version = _command_version("node", "--version")
    npm_present, npm_version = _command_version("npm", "--version")
    node_modules = repo_root / "frontend" / "node_modules"
    detail = {"node": node_version, "npm": npm_version, "node_modules": str(node_modules)}
    frontend_node_requirement = "Node.js 24 LTS >=24.15.0"
    if not node_present or not npm_present:
        return _doctor_check(
            "frontend",
            "warn",
            "Node.js or npm is not available; CLI/GUI frontends cannot run from this shell.",
            detail=detail,
            next_action=f"Install {frontend_node_requirement} and run `npm --prefix frontend install`.",
        )
    node_parts = None
    if node_version and node_version.startswith("v"):
        try:
            node_parts = tuple(int(part) for part in node_version[1:].split(".")[:3])
        except ValueError:
            node_parts = None
    if node_parts is not None and node_parts < (24, 15, 0):
        return _doctor_check(
            "frontend",
            "warn",
            f"Node.js {node_version} is below the frontend requirement.",
            detail=detail,
            next_action=f"Install {frontend_node_requirement} and rerun `npm --prefix frontend install`.",
        )
    if not node_modules.is_dir():
        return _doctor_check(
            "frontend",
            "warn",
            "Frontend dependencies are not installed.",
            detail=detail,
            next_action="Run `npm --prefix frontend install`.",
        )
    return _doctor_check("frontend", "ok", "Node, npm, and frontend dependencies are present.", detail=detail)


def _doctor_registry(repo_root: Path) -> dict:
    targets = [
        (repo_root / "config" / "app_registry" / "workflows" / "assistant-default" / "1.0.0.yaml", "workflows"),
        (repo_root / "config" / "app_registry" / "capabilities" / "assistant_reply" / "1.0.0.yaml", "capabilities"),
    ]
    results = []
    for path, kind in targets:
        if not path.is_file():
            return _doctor_check(
                "registry",
                "error",
                f"Required default registry object is missing: {path.relative_to(repo_root)}",
                detail={"path": str(path), "kind": kind},
                next_action="Restore the repo-tracked default registry object.",
            )
        try:
            from awf.ops.registry import op_registry_validate

            results.append(op_registry_validate(path, kind=kind))
        except Exception as exc:
            return _doctor_check(
                "registry",
                "error",
                f"Default registry object failed validation: {path.relative_to(repo_root)}",
                detail={"path": str(path), "kind": kind, "error": str(exc)},
                next_action="Fix or restore the invalid default registry object.",
            )
    return _doctor_check(
        "registry", "ok", "Default assistant workflow and capability validate.", detail={"validated": results}
    )


def _doctor_database(repo_root: Path) -> dict:
    path = resolve_db_path(repo_root)
    if not path.is_file():
        return _doctor_check(
            "database",
            "error",
            "AWF database has not been bootstrapped.",
            detail={"path": str(path)},
            next_action="Run `awf-setup` from the repo venv.",
        )
    return _doctor_check("database", "ok", "AWF database exists.", detail={"path": str(path)})


def _doctor_env(repo_root: Path) -> dict:
    path = env_path(repo_root)
    if not path.is_file():
        return _doctor_check(
            "env",
            "error",
            ".env is missing.",
            detail={"path": str(path)},
            next_action="Run `awf-setup` to generate local secrets.",
        )
    try:
        secret = get_env_value(path, "AWF_SECRET_KEY")
    except Exception as exc:
        return _doctor_check(
            "env",
            "error",
            ".env does not contain a usable AWF_SECRET_KEY.",
            detail={"error": str(exc)},
            next_action="Regenerate .env with `awf-setup` or restore the correct local key.",
        )
    if not secret or secret == "<your-secret-key-here>":
        return _doctor_check(
            "env",
            "error",
            ".env still contains a placeholder secret key.",
            next_action="Run `awf-setup` or replace AWF_SECRET_KEY with a generated local key.",
        )
    return _doctor_check("env", "ok", ".env contains a local AWF secret key.")


def _doctor_paths(repo_root: Path) -> dict:
    cache_temp = repo_root / "cache" / "temp"
    cache_sandbox = repo_root / "cache" / "sandbox"
    missing = [path.relative_to(repo_root).as_posix() for path in (cache_temp, cache_sandbox) if not path.is_dir()]
    if missing:
        return _doctor_check(
            "local_paths",
            "warn",
            "Some local cache directories are missing.",
            detail={"missing": missing, "platform": os.name},
            next_action="Run `awf-setup`; Windows operators should use cache/temp for temp-heavy commands.",
        )
    return _doctor_check(
        "local_paths",
        "ok",
        "Local cache and sandbox paths exist.",
        detail={"cache_temp": str(cache_temp), "cache_sandbox": str(cache_sandbox), "platform": os.name},
    )


def _doctor_agent_clis(*, with_versions: bool = True) -> dict:
    commands = {
        "codex": ("codex", "--version"),
        "claude-code": ("claude", "--version"),
        "antigravity": ("antigravity", "--version"),
        "copilot": ("gh", "--version"),
        "cline": ("cline", "--version"),
    }
    found = {}
    for adapter, command in commands.items():
        if with_versions:
            present, version = _command_version(*command)
        else:
            present = shutil.which(command[0]) is not None
            version = None
        found[adapter] = {"present": present, "version": version}
    if any(item["present"] for item in found.values()):
        return _doctor_check("agent_clis", "ok", "At least one implementation agent CLI is visible.", detail=found)
    return _doctor_check(
        "agent_clis",
        "warn",
        "No implementation agent CLI is visible; first-run assistant still works.",
        detail=found,
        next_action="Install and authenticate Codex, Claude Code, Antigravity, GitHub Copilot CLI, or Cline before running implementation workflows.",
    )


def _doctor_speech(readiness: dict) -> dict:
    results = readiness.get("readiness", {}) if isinstance(readiness, dict) else {}
    speech = {name: result for name, result in results.items() if name in {"stt", "tts", "vad", "wake"}}
    if not speech:
        return _doctor_check(
            "speech",
            "warn",
            "Speech readiness is unavailable.",
            detail=readiness,
            next_action="Run `awf-speech models verify`; run `awf-speech models sync` if artifacts are missing.",
        )
    if all(result.get("ready") for result in speech.values()):
        return _doctor_check("speech", "ok", "Speech readiness checks are ready.", detail=speech)
    return _doctor_check(
        "speech",
        "warn",
        "One or more speech functions are not ready.",
        detail=speech,
        next_action="Run `awf-speech models verify`, then `awf-speech models sync` for missing artifacts.",
    )


def op_secret_set(repo_root: Path, conn: sqlite3.Connection, *, name: str, value: str) -> dict:
    key = get_env_value(env_path(repo_root), "AWF_SECRET_KEY").encode("ascii")
    set_secret(conn, name, value, key)
    return {"name": name, "status": "set"}


def op_secret_list_names(conn: sqlite3.Connection) -> list[str]:
    return list_secret_names(conn)


def op_system_readiness(repo_root: Path) -> dict:
    from awf.hardware.profiler import resolve_hardware_profile_id

    try:
        profile_id, payload = resolve_hardware_profile_id(repo_root)
        return {
            "profile_id": profile_id,
            "inventory": _jsonable(payload.get("inventory")),
            "tokens": _jsonable(payload.get("tokens", [])),
            "readiness": _jsonable(payload.get("readiness", {})),
        }
    except Exception as exc:
        return {
            "profile_id": None,
            "inventory": None,
            "tokens": [],
            "readiness": {},
            "error": str(exc),
        }


def op_system_doctor(repo_root: Path, *, readiness: dict | None = None, quick: bool = False) -> dict:
    readiness = readiness or op_system_readiness(repo_root)
    checks = [
        _doctor_python(repo_root),
        _doctor_env(repo_root),
        _doctor_database(repo_root),
        _doctor_paths(repo_root),
        _doctor_registry(repo_root),
        _doctor_node(repo_root),
        _doctor_agent_clis(with_versions=not quick),
        _doctor_speech(readiness),
    ]
    next_actions = [check["next_action"] for check in checks if check.get("next_action")]
    return {
        "status": _doctor_overall(checks),
        "checks": checks,
        "readiness": readiness,
        "next_actions": next_actions,
        "first_run_command": 'awf run assistant-default@1.0.0 --objective "check the system"',
    }


__all__ = ("op_secret_list_names", "op_secret_set", "op_system_doctor", "op_system_readiness")
