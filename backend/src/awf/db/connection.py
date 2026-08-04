"""Connection helper for data/awf_db/awf.db (Section 8)."""

import sqlite3
from pathlib import Path


def get_connection(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    # Real concurrent writers now exist (map node items, each with their own
    # connection to the same file) - without a busy timeout, SQLite's
    # default is to fail immediately with "database is locked" rather than
    # wait for the other writer's transaction to finish.
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn
