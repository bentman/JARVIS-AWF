"""`approval` node (Section 12.2): waits for an operator decision bound to
an exact action digest - the default gate for anything R2+ under the
attended model.

A node MAY declare `riskClass` (R0-R3); it's stored on the `approvals` row
so a caller (a frontend rendering the pending-approvals list, or the voice-
approval rule below) can read the real risk class of a specific pending
approval instead of needing to already know it out of band. An
undeclared `riskClass` stores `NULL` - `op_approval_approve` treats an
unknown risk class as R2+ for the voice-refusal rule (Section 16.4),
never as R0/R1, since silently trusting an absent value would be a bypass.

The Step for this node does not go through `run_step` while still pending:
`run_step` marks a Step `SUCCEEDED` as soon as its function
returns, which would permanently cache the "still waiting" result across a
resume. Instead the Step sits in `WAITING_APPROVAL` (an existing Section 8
status) until a real decision lands in the `approvals` table, matching the
same "MUST NOT silently continue or silently succeed" rule the Handoff node
follows for `WAITING_INPUT`.
"""

import hashlib
import json
import sqlite3

from awf.clock import utc_now_rfc3339
from awf.events.writer import write_event
from awf.ids import uuid7


class ApprovalRejectedError(RuntimeError):
    def __init__(self, message: str, *, failure_class: str = "APPROVAL_REJECTED"):
        super().__init__(message)
        self.failure_class = failure_class


def _action_digest(run_id: str, node: dict) -> str:
    payload = json.dumps(
        {"run_id": run_id, "node_id": node["id"], "action": node.get("action", node["id"])},
        sort_keys=True,
    )
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def make_approval_node_executor():
    def executor(conn: sqlite3.Connection, run_id: str, step_id: str, node: dict) -> dict:
        step_row = conn.execute(
            "SELECT status, output_json FROM steps WHERE step_id = ?", (step_id,)
        ).fetchone()
        if step_row["status"] == "SUCCEEDED":
            return json.loads(step_row["output_json"])

        row = conn.execute(
            "SELECT approval_id, status FROM approvals WHERE step_id = ?", (step_id,)
        ).fetchone()

        if row is None:
            approval_id = uuid7()
            now = utc_now_rfc3339()
            conn.execute(
                "INSERT INTO approvals (approval_id, run_id, step_id, action_digest, status, requested_at, risk_class) "
                "VALUES (?, ?, ?, ?, 'pending', ?, ?)",
                (approval_id, run_id, step_id, _action_digest(run_id, node), now, node.get("riskClass")),
            )
            conn.execute(
                "UPDATE steps SET status = 'WAITING_APPROVAL', started_at = ? WHERE step_id = ?",
                (now, step_id),
            )
            conn.execute(
                "UPDATE runs SET status = 'WAITING_APPROVAL', updated_at = ? WHERE run_id = ?",
                (now, run_id),
            )
            conn.commit()
            write_event(
                conn, run_id=run_id, step_id=step_id, new_status="WAITING_APPROVAL",
                actor="engine", reason_code="approval_requested",
                payload_json=json.dumps({"approval_id": approval_id}),
            )
            return {"waiting_input": True, "approval_id": approval_id}

        if row["status"] == "pending":
            return {"waiting_input": True, "approval_id": row["approval_id"]}

        if row["status"] == "rejected":
            ended_at = utc_now_rfc3339()
            conn.execute(
                "UPDATE steps SET status = 'FAILED', failure_class = 'APPROVAL_REJECTED', ended_at = ? "
                "WHERE step_id = ?",
                (ended_at, step_id),
            )
            conn.commit()
            write_event(
                conn, run_id=run_id, step_id=step_id, new_status="FAILED",
                actor="engine", reason_code="approval_rejected",
                payload_json=json.dumps({"approval_id": row["approval_id"]}),
            )
            raise ApprovalRejectedError(f"approval {row['approval_id']} was rejected")

        # approved
        output = {"approved": True, "approval_id": row["approval_id"]}
        ended_at = utc_now_rfc3339()
        conn.execute(
            "UPDATE steps SET status = 'SUCCEEDED', output_json = ?, ended_at = ? WHERE step_id = ?",
            (json.dumps(output), ended_at, step_id),
        )
        conn.commit()
        write_event(
            conn, run_id=run_id, step_id=step_id, new_status="SUCCEEDED",
            actor="engine", reason_code="approval_granted", payload_json=json.dumps(output),
        )
        return output

    return executor
