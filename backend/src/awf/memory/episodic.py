"""Episodic retrieval over AWF evidence tables (ADR-0020)."""

import sqlite3


def search_events(
    conn: sqlite3.Connection,
    *,
    query: str,
    run_id: str | None = None,
    limit: int = 20,
) -> list[dict]:
    cleaned = query.strip()
    if not cleaned:
        rows = conn.execute(
            """
            SELECT e.*, r.workflow_ref, s.node_id
            FROM events e
            LEFT JOIN runs r ON r.run_id = e.run_id
            LEFT JOIN steps s ON s.step_id = e.step_id
            WHERE (? IS NULL OR e.run_id = ?)
            ORDER BY e.occurred_at DESC, e.event_id DESC
            LIMIT ?
            """,
            (run_id, run_id, limit),
        ).fetchall()
        return [{**dict(row), "source": "events", "score": 1.0} for row in rows]

    like_pat = f"%{cleaned}%"
    rows = conn.execute(
        """
        SELECT e.*, r.workflow_ref, s.node_id
        FROM events e
        LEFT JOIN runs r ON r.run_id = e.run_id
        LEFT JOIN steps s ON s.step_id = e.step_id
        WHERE (? IS NULL OR e.run_id = ?)
          AND (
              e.reason_code LIKE ?
              OR e.actor LIKE ?
              OR e.payload_json LIKE ?
              OR r.workflow_ref LIKE ?
              OR s.node_id LIKE ?
          )
        ORDER BY e.occurred_at DESC, e.event_id DESC
        LIMIT ?
        """,
        (run_id, run_id, like_pat, like_pat, like_pat, like_pat, like_pat, limit),
    ).fetchall()
    return [{**dict(row), "source": "events", "score": 1.0} for row in rows]


def run_timeline(conn: sqlite3.Connection, *, run_id: str) -> dict:
    run = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    if run is None:
        raise ValueError(f"no such run: {run_id}")
    steps = [
        dict(row)
        for row in conn.execute("SELECT * FROM steps WHERE run_id = ? ORDER BY started_at", (run_id,)).fetchall()
    ]
    approvals = [
        dict(row)
        for row in conn.execute("SELECT * FROM approvals WHERE run_id = ? ORDER BY requested_at", (run_id,)).fetchall()
    ]
    artifacts = [
        dict(row)
        for row in conn.execute("SELECT * FROM artifacts WHERE run_id = ? ORDER BY created_at", (run_id,)).fetchall()
    ]
    events = [
        dict(row)
        for row in conn.execute("SELECT * FROM events WHERE run_id = ? ORDER BY occurred_at", (run_id,)).fetchall()
    ]
    return {"run": dict(run), "steps": steps, "approvals": approvals, "artifacts": artifacts, "events": events}
