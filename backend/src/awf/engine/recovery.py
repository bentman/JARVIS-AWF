"""Startup recovery scan (Section 13.2).

Triggered by `awf resume` (Phase 10), not a background process: scan `runs`
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
