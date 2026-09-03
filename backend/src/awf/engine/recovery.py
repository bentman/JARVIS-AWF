"""Startup recovery scan (Section 13.2).

Triggered by `awf system resume` (Phase 10, ADR-0029), not a background process: scan `runs`
for any row not in a terminal state so the caller can resume each one.
"""

import sqlite3

TERMINAL_RUN_STATUSES = ("SUCCEEDED", "FAILED", "CANCELED")


def scan_incomplete_runs(conn: sqlite3.Connection) -> list[str]:
    placeholders = ", ".join("?" for _ in TERMINAL_RUN_STATUSES)
    rows = conn.execute(
        f"SELECT run_id FROM runs WHERE status NOT IN ({placeholders})",
        TERMINAL_RUN_STATUSES,
    ).fetchall()
    return [row["run_id"] for row in rows]


def reset_interrupted_node_steps(conn: sqlite3.Connection, run_id: str) -> None:
    """Purge uncompleted or in-flight step attempts for uncompleted nodes on resume (ADR-0030)."""
    succeeded_rows = conn.execute(
        "SELECT DISTINCT node_id FROM steps WHERE run_id = ? AND status = 'SUCCEEDED'",
        (run_id,),
    ).fetchall()
    succeeded_nodes = {row["node_id"] for row in succeeded_rows}

    all_node_rows = conn.execute(
        "SELECT DISTINCT node_id FROM steps WHERE run_id = ?",
        (run_id,),
    ).fetchall()
    for row in all_node_rows:
        node_id = row["node_id"]
        if node_id not in succeeded_nodes:
            conn.execute(
                "DELETE FROM steps WHERE run_id = ? AND node_id = ?",
                (run_id, node_id),
            )
    conn.execute(
        "DELETE FROM steps WHERE run_id = ? AND status IN ('RUNNING', 'RETRY_WAIT')",
        (run_id,),
    )
    conn.commit()
