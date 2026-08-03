"""Voice approval rule (Section 16.4): an approval decision for an R2+
action MUST NOT be granted from voice input alone - the GUI MUST display
the exact action digest and require a non-voice (click/keypress)
confirmation. Voice MAY acknowledge R0/R1 prompts.
"""

import sqlite3

from awf.cli.core_ops import op_approval_approve

HIGH_RISK_CLASSES = ("R2", "R3")


def decide_voice_acknowledgement(risk_class: str, *, voice_confirmed: bool) -> dict:
    """Pure decision, no DB access: whether a voice-only acknowledgement is
    sufficient for this risk class.

    R2/R3: NEVER sufficient, regardless of `voice_confirmed` - always
    requires a separate on-screen (click/keypress) confirmation.
    R0/R1: voice MAY acknowledge.
    """
    if risk_class in HIGH_RISK_CLASSES:
        return {"decided": False, "requires_on_screen_confirmation": True, "channel": "voice"}
    return {
        "decided": bool(voice_confirmed),
        "requires_on_screen_confirmation": False,
        "channel": "voice",
    }


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
    result = op_approval_approve(conn, approval_id=approval_id)
    return {**decision, **result}
