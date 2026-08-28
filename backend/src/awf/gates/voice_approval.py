"""Voice approval rule (Section 16.4): an approval decision for an R2+
action MUST NOT be granted from voice input alone - the GUI MUST display
the exact action digest and require a non-voice (click/keypress)
confirmation. Voice MAY acknowledge R0/R1 prompts.
"""

import sqlite3

from awf.approval_policy import decide_voice_acknowledgement
from awf.clock import utc_now_rfc3339


def attempt_voice_approval(
    conn: sqlite3.Connection, *, approval_id: str, risk_class: str, voice_confirmed: bool
) -> dict:
    """Attempts to acknowledge a pending approval via voice alone.

    For R2/R3, this NEVER calls the real approve operation - the approval
    stays pending, and the caller (the GUI) MUST separately display the
    action digest and obtain a non-voice confirmation before approving.
    """
    decision = decide_voice_acknowledgement(risk_class, voice_confirmed=voice_confirmed)
    if not decision["decided"]:
        return decision
    row = conn.execute("SELECT status FROM approvals WHERE approval_id = ?", (approval_id,)).fetchone()
    if row is None:
        raise ValueError(f"no such approval: {approval_id}")
    if row["status"] != "pending":
        raise ValueError(f"approval {approval_id} is not pending (status={row['status']})")
    conn.execute(
        "UPDATE approvals SET status = 'approved', reason = NULL, decided_at = ? WHERE approval_id = ?",
        (utc_now_rfc3339(), approval_id),
    )
    conn.commit()
    result = {"approval_id": approval_id, "status": "approved", "reason": None}
    return {**decision, **result}


__all__ = ("attempt_voice_approval", "decide_voice_acknowledgement")
