"""approval operation implementations."""

import json
import sqlite3

from awf.approval_policy import decide_voice_acknowledgement
from awf.clock import utc_now_rfc3339
from awf.ops.shared import CoreOpError


def _machine_action_preview_for_step(conn: sqlite3.Connection, *, step_id: str) -> dict | None:
    rows = conn.execute(
        "SELECT payload_json, reason_code FROM events "
        "WHERE step_id = ? AND reason_code IN ("
        "'machine_action_waiting_approval', 'machine_action_allowed', 'machine_action_denied', "
        "'machine_action_executed', 'improvement_merge_approval_requested'"
        ") ORDER BY occurred_at DESC",
        (step_id,),
    ).fetchall()
    for row in rows:
        try:
            payload = json.loads(row["payload_json"] or "{}")
        except json.JSONDecodeError:
            continue
        action = payload.get("machine_action")
        if action:
            return {"machine_action": action, "machine_action_digest": payload.get("machine_action_digest")}
        if payload.get("improvement_id"):
            imp_id = payload["improvement_id"]
            from awf.improvement.proposals import get as get_proposal

            try:
                proposal = get_proposal(conn, improvement_id=imp_id)
                return {
                    "kind": "improvement_merge",
                    "improvement_id": imp_id,
                    "human_summary": proposal.get("human_summary"),
                    "scope_classification": proposal.get("scope_classification"),
                    "safety_assessment": proposal.get("safety_assessment"),
                    "proposal_review": proposal.get("proposal_review"),
                    "diff_stats": proposal.get("diff_stats"),
                    "verdict_artifact_id": proposal.get("verdict_artifact_id"),
                    "merge_action_digest": payload.get("merge_action_digest"),
                    "proposal": proposal,
                }
            except Exception:
                pass
    return None


def _decide_approval(conn: sqlite3.Connection, *, approval_id: str, status: str, reason: str | None) -> dict:
    row = conn.execute("SELECT * FROM approvals WHERE approval_id = ?", (approval_id,)).fetchone()
    if row is None:
        raise CoreOpError(f"no such approval: {approval_id}")
    if row["status"] != "pending":
        raise CoreOpError(f"approval {approval_id} is not pending (status={row['status']})")
    conn.execute(
        "UPDATE approvals SET status = ?, reason = ?, decided_at = ? WHERE approval_id = ?",
        (status, reason, utc_now_rfc3339(), approval_id),
    )
    conn.commit()
    return {"approval_id": approval_id, "status": status, "reason": reason}


def op_approval_list(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT * FROM approvals WHERE status = 'pending' ORDER BY requested_at").fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["preview"] = _machine_action_preview_for_step(conn, step_id=row["step_id"])
        result.append(item)
    return result


def op_approval_detail(conn: sqlite3.Connection, *, approval_id: str) -> dict:
    row = conn.execute("SELECT * FROM approvals WHERE approval_id = ?", (approval_id,)).fetchone()
    if row is None:
        raise CoreOpError(f"no such approval: {approval_id}")
    preview = _machine_action_preview_for_step(conn, step_id=row["step_id"])
    return {"approval": dict(row), "preview": preview}


def op_machine_action_preview(conn: sqlite3.Connection, *, approval_id: str) -> dict:
    detail = op_approval_detail(conn, approval_id=approval_id)
    if detail["preview"] is None:
        raise CoreOpError(f"approval {approval_id} has no machine action preview")
    return detail["preview"]


def op_approval_approve(
    conn: sqlite3.Connection, *, approval_id: str, channel: str = "manual", risk_class: str | None = None
) -> dict:
    # `channel="manual"` (CLI/TUI click-equivalent, the existing default) is
    # unrestricted. `channel="voice"` (Section 16.4) MUST NOT grant an R2+
    # approval from voice alone - enforced here, in the core, not only by
    # the GUI's own TypeScript copy of this same rule, so no frontend can
    # bypass it by skipping its own check.
    if channel == "voice":
        row = conn.execute("SELECT risk_class FROM approvals WHERE approval_id = ?", (approval_id,)).fetchone()
        if row is None:
            raise CoreOpError(f"no such approval: {approval_id}")
        stored_risk_class = row["risk_class"]
        if risk_class is not None and stored_risk_class is not None and risk_class != stored_risk_class:
            raise CoreOpError(
                f"risk_class={risk_class!r} does not match this approval's real risk_class={stored_risk_class!r} "
                "- a caller may not claim a different risk class than the one recorded when this approval was requested"
            )
        # An approval whose node never declared `riskClass` has no value to
        # check against - the safe default is R2 (never auto-grantable
        # from voice alone), not R0/R1, since trusting an absent value as
        # low-risk would bypass the rule below.
        effective_risk_class = risk_class or stored_risk_class or "R2"
        decision = decide_voice_acknowledgement(effective_risk_class, voice_confirmed=True)
        if not decision["decided"]:
            return {
                "approval_id": approval_id,
                "status": "pending",
                "requires_on_screen_confirmation": True,
            }
        result = _decide_approval(conn, approval_id=approval_id, status="approved", reason=None)
        return {**decision, **result}
    return _decide_approval(conn, approval_id=approval_id, status="approved", reason=None)


def op_approval_reject(conn: sqlite3.Connection, *, approval_id: str, reason: str) -> dict:
    return _decide_approval(conn, approval_id=approval_id, status="rejected", reason=reason)


__all__ = (
    "op_approval_approve",
    "op_approval_detail",
    "op_approval_list",
    "op_approval_reject",
    "op_machine_action_preview",
)
