"""control operation implementations."""

import sqlite3
from pathlib import Path

from awf.ops.approval import op_approval_list
from awf.ops.artifact import op_artifact_list
from awf.ops.improvement import op_improvement_list
from awf.ops.llm import op_llm_serve, op_llm_servers
from awf.ops.memory import op_episodic_timeline
from awf.ops.registry import op_registry_list
from awf.ops.run import op_run_list, op_run_outcome, op_run_status
from awf.ops.system import op_system_doctor, op_system_readiness
from awf.registry.kinds import KINDS


def _recent_verdict_artifacts(conn: sqlite3.Connection, *, limit: int = 5) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM artifacts WHERE artifact_type = 'verdict' ORDER BY created_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [dict(row) for row in rows]


def _registry_counts(repo_root: Path, conn: sqlite3.Connection) -> dict[str, int]:
    counts: dict[str, int] = {}
    for registry_kind in KINDS:
        counts[registry_kind.key] = len(op_registry_list(repo_root, kind=registry_kind.key, conn=conn))
    return counts


def _control_error(exc: Exception) -> dict:
    return {"error": str(exc)}


def op_events_snapshot(conn: sqlite3.Connection, *, run_id: str | None = None, limit: int = 100) -> dict:
    limit = max(1, min(int(limit), 500))
    if run_id:
        rows = conn.execute(
            "SELECT * FROM events WHERE run_id = ? ORDER BY occurred_at DESC, event_id DESC LIMIT ?",
            (run_id, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM events ORDER BY occurred_at DESC, event_id DESC LIMIT ?", (limit,)
        ).fetchall()
    return {"events": [dict(row) for row in reversed(rows)], "streaming": False}


def op_control_center_summary(repo_root: Path, conn: sqlite3.Connection) -> dict:
    readiness = op_system_readiness(repo_root)
    host_profile_id = readiness.get("profile_id") if isinstance(readiness, dict) else None
    try:
        llm_servers = op_llm_servers(repo_root, host_profile_id=host_profile_id, probe_timeout_seconds=0.25)
    except Exception as exc:
        llm_servers = _control_error(exc)
    try:
        llm_status = op_llm_serve(repo_root, conn, action="status", probe_timeout_seconds=0.25)
    except Exception as exc:
        llm_status = _control_error(exc)
    doctor = op_system_doctor(repo_root, readiness=readiness, quick=True)
    improvements = op_improvement_list(conn)
    return {
        "runs": op_run_list(conn),
        "approvals": op_approval_list(conn),
        "improvements": improvements,
        "recent_verdicts": _recent_verdict_artifacts(conn),
        "registry_counts": _registry_counts(repo_root, conn),
        "llm": {
            "servers": llm_servers,
            "status": llm_status,
        },
        "readiness": readiness,
        "doctor": doctor,
    }


def op_control_center_run_detail(repo_root: Path, conn: sqlite3.Connection, *, run_id: str) -> dict:
    status = op_run_status(conn, run_id=run_id)
    artifacts = op_artifact_list(conn, run_id=run_id)
    timeline = op_episodic_timeline(conn, run_id=run_id)
    improvements = [proposal for proposal in op_improvement_list(conn) if proposal.get("run_id") == run_id]
    verdicts = [artifact for artifact in artifacts if artifact.get("artifact_type") == "verdict"]
    return {
        "run": status,
        "outcome": op_run_outcome(conn, run_id=run_id),
        "artifacts": artifacts,
        "timeline": timeline,
        "improvements": improvements,
        "verdicts": verdicts,
    }


__all__ = ("op_control_center_run_detail", "op_control_center_summary", "op_events_snapshot")
