"""Approval bridge for governed machine actions (ADR-0021)."""

import json
import sqlite3

from awf.clock import utc_now_rfc3339
from awf.events.writer import write_event
from awf.guard.capability_guard import Decision, authorize
from awf.ids import uuid7
from awf.machine.action import MachineAction
from awf.registry.capability_record import CapabilityRecord


class MachineApprovalRejected(RuntimeError):
    def __init__(self, message: str, *, failure_class: str = "APPROVAL_REJECTED"):
        super().__init__(message)
        self.failure_class = failure_class


class MachinePolicyDenied(RuntimeError):
    def __init__(self, message: str, *, failure_class: str = "POLICY_DENIED"):
        super().__init__(message)
        self.failure_class = failure_class


def authorize_machine_action(
    conn: sqlite3.Connection,
    *,
    capability: CapabilityRecord,
    action: MachineAction,
    actor: str = "awf",
    role: str | None = None,
) -> dict | None:
    decision = authorize(
        conn,
        capability=capability,
        agent_allowlist=[capability.ref],
        run_id=action.run_id,
        actor=actor,
        step_id=action.step_id,
        role=role,
    )
    if decision == Decision.DENY:
        _machine_event(conn, action, "machine_action_denied", actor)
        raise MachinePolicyDenied(f"blocked by Capability Guard: {decision.value}")
    if decision == Decision.ALLOW:
        _machine_event(conn, action, "machine_action_allowed", actor)
        return None
    return _ensure_pending_approval(conn, action, actor=actor)


def approved_or_waiting(conn: sqlite3.Connection, *, action: MachineAction, actor: str = "awf") -> dict | None:
    row = conn.execute("SELECT * FROM approvals WHERE step_id = ?", (action.step_id,)).fetchone()
    if row is None:
        return None
    if row["action_digest"] != action.digest:
        raise MachinePolicyDenied("approved action digest does not match current machine action")
    if row["status"] == "pending":
        return {"waiting_input": True, "approval_id": row["approval_id"]}
    if row["status"] == "rejected":
        _machine_event(conn, action, "machine_action_denied", actor, approval_id=row["approval_id"])
        raise MachineApprovalRejected(f"approval {row['approval_id']} was rejected")
    return None


def _ensure_pending_approval(conn: sqlite3.Connection, action: MachineAction, *, actor: str) -> dict:
    row = conn.execute("SELECT * FROM approvals WHERE step_id = ?", (action.step_id,)).fetchone()
    if row is not None:
        if row["action_digest"] != action.digest:
            raise MachinePolicyDenied("pending approval digest does not match current machine action")
        return {"waiting_input": True, "approval_id": row["approval_id"]}

    approval_id = uuid7()
    now = utc_now_rfc3339()
    conn.execute(
        "INSERT INTO approvals (approval_id, run_id, step_id, action_digest, status, requested_at, risk_class) "
        "VALUES (?, ?, ?, ?, 'pending', ?, ?)",
        (approval_id, action.run_id, action.step_id, action.digest, now, action.risk_class),
    )
    conn.execute(
        "UPDATE steps SET status = 'WAITING_APPROVAL', started_at = ? WHERE step_id = ?",
        (now, action.step_id),
    )
    conn.execute(
        "UPDATE runs SET status = 'WAITING_APPROVAL', updated_at = ? WHERE run_id = ?",
        (now, action.run_id),
    )
    conn.commit()
    _machine_event(conn, action, "machine_action_waiting_approval", actor, approval_id=approval_id)
    return {"waiting_input": True, "approval_id": approval_id}


def _machine_event(
    conn: sqlite3.Connection, action: MachineAction, reason_code: str, actor: str, approval_id: str | None = None
) -> None:
    payload = {"machine_action": action.to_dict(), "machine_action_digest": action.digest}
    if approval_id is not None:
        payload["approval_id"] = approval_id
    write_event(
        conn,
        run_id=action.run_id,
        step_id=action.step_id,
        new_status=reason_code,
        actor=actor,
        reason_code=reason_code,
        payload_json=json.dumps(payload, sort_keys=True),
    )


def record_executed(conn: sqlite3.Connection, action: MachineAction, *, actor: str = "awf", output: dict) -> None:
    payload = {"machine_action": action.to_dict(), "machine_action_digest": action.digest, "output": output}
    write_event(
        conn,
        run_id=action.run_id,
        step_id=action.step_id,
        new_status="machine_action_executed",
        actor=actor,
        reason_code="machine_action_executed",
        payload_json=json.dumps(payload, sort_keys=True),
    )
