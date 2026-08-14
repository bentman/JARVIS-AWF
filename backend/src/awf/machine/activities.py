"""Standard governed machine activities (ADR-0021)."""

import json
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from awf.clock import utc_now_rfc3339
from awf.engine.executor import DEFAULT_FAILURE_CLASS
from awf.machine.action import MachineAction, content_digest
from awf.machine.approvals import approved_or_waiting, authorize_machine_action, record_executed
from awf.machine.artifacts import write_report_artifact
from awf.machine.policy import (
    MachinePolicyError,
    constraint_family,
    resolve_allowed_path,
    validate_command,
    validate_url,
)
from awf.paths import artifacts_dir
from awf.registry.capability_record import CapabilityRecord


class MachineActivityError(RuntimeError):
    def __init__(self, message: str, *, failure_class: str = DEFAULT_FAILURE_CLASS):
        super().__init__(message)
        self.failure_class = failure_class


def _repo_python_executable(repo_root: Path) -> str:
    for candidate in (
        repo_root / "backend" / ".venv" / "Scripts" / "python.exe",
        repo_root / "backend" / ".venv" / "bin" / "python",
    ):
        if candidate.is_file():
            return str(candidate)
    return sys.executable


def _execution_argv(repo_root: Path, argv: list[str]) -> list[str]:
    if not argv:
        return argv
    executable = argv[0].replace("\\", "/").lower()
    if executable in {
        "python",
        "python.exe",
        "py",
        "python3",
        "python3.12",
        "python3.13",
        "python3.14",
        "backend/.venv/bin/python",
        "backend/.venv/scripts/python.exe",
    }:
        return [_repo_python_executable(repo_root), *argv[1:]]
    return argv


def run_machine_activity(
    conn: sqlite3.Connection,
    *,
    repo_root: Path,
    worktree_path: Path,
    run_id: str,
    step_id: str,
    node: dict,
    capability: CapabilityRecord,
) -> dict:
    row = conn.execute("SELECT status, output_json FROM steps WHERE step_id = ?", (step_id,)).fetchone()
    if row["status"] == "SUCCEEDED":
        return json.loads(row["output_json"])

    args = node.get("args", {})
    try:
        action = _build_action(repo_root, worktree_path, run_id, step_id, node, capability, args)
        waiting = approved_or_waiting(conn, action=action)
        if waiting is not None:
            return waiting
        if row["status"] != "WAITING_APPROVAL":
            waiting = authorize_machine_action(conn, capability=capability, action=action)
            if waiting is not None:
                return waiting
        _mark_running(conn, run_id, step_id)
        output = _execute(conn, repo_root, worktree_path, run_id, step_id, node["function"], args, capability)
        _mark_succeeded(conn, step_id, output)
        record_executed(conn, action, output=output)
        return output
    except Exception as exc:
        _mark_failed(conn, run_id, step_id, exc)
        raise


def _build_action(
    repo_root: Path,
    worktree: Path,
    run_id: str,
    step_id: str,
    node: dict,
    capability: CapabilityRecord,
    args: dict,
) -> MachineAction:
    kind = node["function"]
    if kind.startswith("fs_"):
        constraints = constraint_family(capability.constraints, "filesystem")
        path = resolve_allowed_path(
            repo_root=repo_root,
            worktree=worktree,
            run_id=run_id,
            relative_or_absolute=args["path"],
            constraints=constraints,
            must_exist=kind in {"fs_read", "fs_delete"},
        )
        body_digest = content_digest(args.get("content", "")) if kind == "fs_write" else None
        return MachineAction(
            kind=kind,
            run_id=run_id,
            step_id=step_id,
            node_id=node["id"],
            operation=capability.effects.operation,
            capability_ref=capability.ref,
            risk_class=capability.risk_class,
            approval=capability.approval,
            target={"path": str(path)},
            body_digest=body_digest,
        )
    if kind == "command_run":
        constraints = constraint_family(capability.constraints, "command")
        argv = list(args["argv"])
        cwd = resolve_allowed_path(
            repo_root=repo_root,
            worktree=worktree,
            run_id=run_id,
            relative_or_absolute=args.get("cwd", "."),
            constraints={"allowedRoots": [constraints.get("cwdRoot", "worktree")]},
            must_exist=True,
        )
        validate_command(argv=argv, cwd=cwd, worktree=worktree, constraints=constraints)
        return MachineAction(
            kind=kind,
            run_id=run_id,
            step_id=step_id,
            node_id=node["id"],
            operation=capability.effects.operation,
            capability_ref=capability.ref,
            risk_class=capability.risk_class,
            approval=capability.approval,
            target={"argv": argv, "cwd": str(cwd)},
        )
    if kind == "network_fetch":
        constraints = constraint_family(capability.constraints, "network")
        method = args.get("method", "GET").upper()
        validate_url(args["url"], method, constraints)
        return MachineAction(
            kind=kind,
            run_id=run_id,
            step_id=step_id,
            node_id=node["id"],
            operation=capability.effects.operation,
            capability_ref=capability.ref,
            risk_class=capability.risk_class,
            approval=capability.approval,
            target={"method": method, "url": args["url"]},
            body_digest=content_digest(args.get("body", "")) if args.get("body") else None,
        )
    raise MachinePolicyError(f"unsupported machine activity: {kind}")


def _execute(
    conn: sqlite3.Connection,
    repo_root: Path,
    worktree: Path,
    run_id: str,
    step_id: str,
    kind: str,
    args: dict,
    capability: CapabilityRecord,
) -> dict:
    if kind == "fs_read":
        return _fs_read(repo_root, worktree, run_id, args, capability)
    if kind == "fs_write":
        return _fs_write(repo_root, worktree, run_id, args, capability)
    if kind == "fs_delete":
        return _fs_delete(repo_root, worktree, run_id, args, capability)
    if kind == "command_run":
        return _command_run(conn, repo_root, worktree, run_id, step_id, args, capability)
    if kind == "network_fetch":
        return _network_fetch(conn, repo_root, run_id, step_id, args, capability)
    raise MachinePolicyError(f"unsupported machine activity: {kind}")


def _fs_read(repo_root: Path, worktree: Path, run_id: str, args: dict, capability: CapabilityRecord) -> dict:
    constraints = constraint_family(capability.constraints, "filesystem")
    path = resolve_allowed_path(
        repo_root=repo_root,
        worktree=worktree,
        run_id=run_id,
        relative_or_absolute=args["path"],
        constraints=constraints,
        must_exist=True,
    )
    max_bytes = int(args.get("maxBytes", constraints.get("maxBytes", 262144)))
    data = path.read_bytes()
    if len(data) > max_bytes:
        raise MachineActivityError(f"file exceeds maxBytes ({len(data)} > {max_bytes})", failure_class="POLICY_DENIED")
    text = data.decode(args.get("encoding", "utf-8"))
    return {"path": str(path), "sha256": content_digest(data), "content": text}


def _fs_write(repo_root: Path, worktree: Path, run_id: str, args: dict, capability: CapabilityRecord) -> dict:
    constraints = constraint_family(capability.constraints, "filesystem")
    path = resolve_allowed_path(
        repo_root=repo_root,
        worktree=worktree,
        run_id=run_id,
        relative_or_absolute=args["path"],
        constraints=constraints,
    )
    data = args.get("content", "").encode(args.get("encoding", "utf-8"))
    max_bytes = int(args.get("maxBytes", constraints.get("maxBytes", 262144)))
    if len(data) > max_bytes:
        raise MachineActivityError(
            f"content exceeds maxBytes ({len(data)} > {max_bytes})", failure_class="POLICY_DENIED"
        )
    tmp = path.with_name(f".{path.name}.awf-tmp")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_bytes(data)
    tmp.replace(path)
    return {"path": str(path), "sha256": content_digest(data), "bytes": len(data)}


def _fs_delete(repo_root: Path, worktree: Path, run_id: str, args: dict, capability: CapabilityRecord) -> dict:
    constraints = constraint_family(capability.constraints, "filesystem")
    path = resolve_allowed_path(
        repo_root=repo_root,
        worktree=worktree,
        run_id=run_id,
        relative_or_absolute=args["path"],
        constraints=constraints,
        must_exist=True,
    )
    trash_dir = worktree / ".awf-trash"
    trash_dir.mkdir(exist_ok=True)
    target = trash_dir / f"{content_digest(str(path))[7:19]}-{path.name}"
    shutil.move(str(path), target)
    return {"path": str(path), "trash_path": str(target), "reversible": True}


def _command_run(
    conn: sqlite3.Connection,
    repo_root: Path,
    worktree: Path,
    run_id: str,
    step_id: str,
    args: dict,
    capability: CapabilityRecord,
) -> dict:
    constraints = constraint_family(capability.constraints, "command")
    argv = list(args["argv"])
    cwd = resolve_allowed_path(
        repo_root=repo_root,
        worktree=worktree,
        run_id=run_id,
        relative_or_absolute=args.get("cwd", "."),
        constraints={"allowedRoots": [constraints.get("cwdRoot", "worktree")]},
        must_exist=True,
    )
    validate_command(argv=argv, cwd=cwd, worktree=worktree, constraints=constraints)
    timeout = int(constraints["timeoutSeconds"])
    env = {"PATH": os.environ.get("PATH", os.defpath)}
    try:
        result = subprocess.run(
            _execution_argv(repo_root, argv), cwd=cwd, capture_output=True, text=True, timeout=timeout, env=env
        )
    except subprocess.TimeoutExpired as exc:
        raise MachineActivityError(f"command timed out after {timeout}s", failure_class="TIMEOUT") from exc
    stdout = result.stdout.encode("utf-8")
    stderr = result.stderr.encode("utf-8")
    max_output = int(constraints.get("maxOutputBytes", 65536))
    if len(stdout) + len(stderr) > max_output:
        payload = json.dumps({"stdout": result.stdout, "stderr": result.stderr}).encode("utf-8")
        artifact_id = write_report_artifact(
            conn,
            artifacts_root=artifacts_dir(repo_root),
            run_id=run_id,
            step_id=step_id,
            payload=payload,
            media_type="application/json",
        )
        return {"returncode": result.returncode, "output_artifact_id": artifact_id, "output_truncated": True}
    return {"returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr}


def _network_fetch(
    conn: sqlite3.Connection,
    repo_root: Path,
    run_id: str,
    step_id: str,
    args: dict,
    capability: CapabilityRecord,
) -> dict:
    constraints = constraint_family(capability.constraints, "network")
    method = args.get("method", "GET").upper()
    url = args["url"]
    validate_url(url, method, constraints)
    request = Request(url, method=method)
    opener = build_opener(_ValidatingRedirectHandler(method=method, constraints=constraints))
    try:
        with opener.open(request, timeout=int(constraints.get("timeoutSeconds", 30))) as response:
            final_url = response.geturl()
            validate_url(final_url, method, constraints)
            max_bytes = int(constraints["maxResponseBytes"])
            body = response.read(max_bytes + 1)
            if len(body) > max_bytes:
                raise MachineActivityError("response exceeds maxResponseBytes", failure_class="POLICY_DENIED")
            output = {
                "url": url,
                "final_url": final_url,
                "status": response.status,
                "content_type": response.headers.get("content-type"),
                "bytes": len(body),
                "body_digest": content_digest(body),
            }
            if constraints.get("retainBodyAsArtifact", False):
                output["artifact_id"] = write_report_artifact(
                    conn,
                    artifacts_root=artifacts_dir(repo_root),
                    run_id=run_id,
                    step_id=step_id,
                    payload=body,
                    media_type=response.headers.get("content-type") or "application/octet-stream",
                )
            return output
    except (HTTPError, URLError) as exc:
        raise MachineActivityError(str(exc), failure_class="TOOL_ERROR") from exc


class _ValidatingRedirectHandler(HTTPRedirectHandler):
    def __init__(self, *, method: str, constraints: dict):
        self._method = method
        self._constraints = constraints

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_url(newurl, self._method, self._constraints)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _mark_running(conn: sqlite3.Connection, run_id: str, step_id: str) -> None:
    conn.execute("UPDATE steps SET status = 'RUNNING', started_at = ? WHERE step_id = ?", (utc_now_rfc3339(), step_id))
    conn.commit()


def _mark_succeeded(conn: sqlite3.Connection, step_id: str, output: dict) -> None:
    conn.execute(
        "UPDATE steps SET status = 'SUCCEEDED', output_json = ?, ended_at = ? WHERE step_id = ?",
        (json.dumps(output), utc_now_rfc3339(), step_id),
    )
    conn.commit()


def _mark_failed(conn: sqlite3.Connection, run_id: str, step_id: str, exc: Exception) -> None:
    failure_class = getattr(exc, "failure_class", DEFAULT_FAILURE_CLASS)
    conn.execute(
        "UPDATE steps SET status = 'FAILED', failure_class = ?, ended_at = ? WHERE step_id = ?",
        (failure_class, utc_now_rfc3339(), step_id),
    )
    conn.execute("UPDATE runs SET status = 'FAILED', updated_at = ? WHERE run_id = ?", (utc_now_rfc3339(), run_id))
    conn.commit()
