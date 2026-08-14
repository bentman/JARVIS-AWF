"""Episodic retrieval over AWF evidence tables (ADR-0020)."""

import sqlite3


def _matches(query: str, *values: object) -> bool:
    lowered = query.lower()
    return any(lowered in str(value or "").lower() for value in values)


def search_events(
    conn: sqlite3.Connection,
    *,
    query: str,
    run_id: str | None = None,
    limit: int = 20,
) -> list[dict]:
    rows = conn.execute(
        """
        SELECT e.*, r.workflow_ref, s.node_id
        FROM events e
        LEFT JOIN runs r ON r.run_id = e.run_id
        LEFT JOIN steps s ON s.step_id = e.step_id
        WHERE (? IS NULL OR e.run_id = ?)
        ORDER BY e.occurred_at DESC, e.event_id DESC
        """,
        (run_id, run_id),
    ).fetchall()
    results = []
    for row in rows:
        data = dict(row)
        if query and not _matches(
            query, data["reason_code"], data["actor"], data["payload_json"], data["workflow_ref"], data["node_id"]
        ):
            continue
        data["source"] = "events"
        data["score"] = 1.0
        results.append(data)
        if len(results) >= limit:
            break
    return results


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
