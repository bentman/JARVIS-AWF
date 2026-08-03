"""Step execution: the durability rule (Section 13.2).

A Step's input/output persist to the `steps` table before workflow logic
proceeds past it. A Step already `SUCCEEDED` is never re-invoked - resuming a
Run re-walks the same ordered Step list and skips anything already done.

When `fn` raises, the Step is recorded `FAILED` with a Section 13.3 failure
class before the exception propagates - a Step MUST NOT be left `RUNNING`
forever just because nothing above this function caught the error.
"""

import json
import sqlite3
from typing import Callable

from awf.clock import utc_now_rfc3339
from awf.events.writer import write_event

StepFn = Callable[[dict], dict]

DEFAULT_FAILURE_CLASS = "INTERNAL"


class StepFailure(RuntimeError):
    """Raise with `failure_class` set to record a specific Section 13.3
    class; any other exception is recorded as INTERNAL."""

    def __init__(self, message: str, *, failure_class: str = DEFAULT_FAILURE_CLASS):
        super().__init__(message)
        self.failure_class = failure_class


def run_step(
    conn: sqlite3.Connection,
    *,
    step_id: str,
    run_id: str,
    fn: StepFn,
    input_payload: dict,
) -> dict:
    row = conn.execute(
        "SELECT status, output_json FROM steps WHERE step_id = ?", (step_id,)
    ).fetchone()
    if row["status"] == "SUCCEEDED":
        return json.loads(row["output_json"])

    conn.execute(
        "UPDATE steps SET status = 'RUNNING', started_at = ? WHERE step_id = ?",
        (utc_now_rfc3339(), step_id),
    )
    conn.commit()
    write_event(
        conn, run_id=run_id, step_id=step_id, new_status="RUNNING",
        actor="engine", reason_code="step_started",
    )

    try:
        output = fn(input_payload)
    except Exception as exc:
        failure_class = getattr(exc, "failure_class", DEFAULT_FAILURE_CLASS)
        conn.execute(
            "UPDATE steps SET status = 'FAILED', failure_class = ?, ended_at = ? WHERE step_id = ?",
            (failure_class, utc_now_rfc3339(), step_id),
        )
        conn.commit()
        write_event(
            conn, run_id=run_id, step_id=step_id, new_status="FAILED",
            actor="engine", reason_code=failure_class.lower(),
            payload_json=json.dumps({"error": str(exc)}),
        )
        raise

    conn.execute(
        "UPDATE steps SET status = 'SUCCEEDED', output_json = ?, ended_at = ? WHERE step_id = ?",
        (json.dumps(output), utc_now_rfc3339(), step_id),
    )
    conn.commit()
    write_event(
        conn, run_id=run_id, step_id=step_id, new_status="SUCCEEDED",
        actor="engine", reason_code="step_completed", payload_json=json.dumps(output),
    )
    return output


def run_workflow(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    steps: list[tuple[str, StepFn, dict]],
) -> None:
    """steps: ordered (step_id, fn, input_payload) triples for this Run."""
    conn.execute(
        "UPDATE runs SET status = 'RUNNING', updated_at = ? WHERE run_id = ?",
        (utc_now_rfc3339(), run_id),
    )
    conn.commit()

    for step_id, fn, input_payload in steps:
        run_step(conn, step_id=step_id, run_id=run_id, fn=fn, input_payload=input_payload)

    conn.execute(
        "UPDATE runs SET status = 'SUCCEEDED', updated_at = ? WHERE run_id = ?",
        (utc_now_rfc3339(), run_id),
    )
    conn.commit()
    write_event(conn, run_id=run_id, new_status="SUCCEEDED", actor="engine", reason_code="run_completed")
