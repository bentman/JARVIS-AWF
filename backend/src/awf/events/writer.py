"""Append-only writer for the `events` table (Section 14: required, cross-cutting, never pruned)."""

import sqlite3

from awf.clock import utc_now_rfc3339
from awf.ids import uuid7


def write_event(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    new_status: str,
    actor: str,
    reason_code: str,
    step_id: str | None = None,
    attempt: int | None = None,
    prior_status: str | None = None,
    payload_json: str = "{}",
) -> str:
    event_id = uuid7()
    conn.execute(
        """
        INSERT INTO events (
            event_id, run_id, step_id, attempt,
            prior_status, new_status, occurred_at, actor, reason_code, payload_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event_id,
            run_id,
            step_id,
            attempt,
            prior_status,
            new_status,
            utc_now_rfc3339(),
            actor,
            reason_code,
            payload_json,
        ),
    )
    conn.commit()
    return event_id
