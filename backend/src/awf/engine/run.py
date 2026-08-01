"""Run/Step creation (Section 13.1, 13.2)."""

import sqlite3

from awf.clock import utc_now_rfc3339
from awf.events.writer import write_event


def create_run(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    workflow_ref: str,
    input_json: str = "{}",
    budget_json: str = "{}",
) -> None:
    now = utc_now_rfc3339()
    conn.execute(
        "INSERT INTO runs (run_id, workflow_ref, status, input_json, budget_json, created_at, updated_at) "
        "VALUES (?, ?, 'CREATED', ?, ?, ?, ?)",
        (run_id, workflow_ref, input_json, budget_json, now, now),
    )
    conn.commit()
    write_event(conn, run_id=run_id, new_status="CREATED", actor="engine", reason_code="run_created")


def create_step(
    conn: sqlite3.Connection,
    *,
    step_id: str,
    run_id: str,
    node_id: str,
    attempt: int = 1,
    input_json: str = "{}",
) -> None:
    now = utc_now_rfc3339()
    conn.execute(
        "INSERT INTO steps (step_id, run_id, node_id, attempt, status, input_json, started_at) "
        "VALUES (?, ?, ?, ?, 'PENDING', ?, ?)",
        (step_id, run_id, node_id, attempt, input_json, now),
    )
    conn.commit()
