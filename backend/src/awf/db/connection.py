"""Connection helper for data/awf_db/awf.db (Section 8)."""

import sqlite3
from pathlib import Path


def get_connection(db_path: Path, *, enable_wal: bool = True) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    # Real concurrent writers now exist (map node items, each with their own
    # connection to the same file) - without a busy timeout, SQLite's
    # default is to fail immediately with "database is locked" rather than
    # wait for the other writer's transaction to finish.
    conn.execute("PRAGMA busy_timeout = 5000")
    if enable_wal:
        try:
            journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            if str(journal_mode).lower() != "wal":
                conn.execute("PRAGMA journal_mode = WAL").fetchone()
        except sqlite3.OperationalError as exc:
            if "database is locked" not in str(exc).lower():
                raise
    conn.commit()
    return conn
