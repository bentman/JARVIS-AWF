"""Idempotent creation of data/awf_db/awf.db (Phase 0 exit condition)."""

from pathlib import Path

from awf.db.connection import get_connection
from awf.db.schema import DDL_STATEMENTS

# Columns added to an existing table after its original CREATE TABLE - a
# real, pre-existing local database predates the column and
# `CREATE TABLE IF NOT EXISTS` alone never adds it. Checked and applied on
# every `init_db` call; a no-op once the column is already there.
_COLUMN_MIGRATIONS = [
    ("approvals", "risk_class", "TEXT CHECK (risk_class IS NULL OR risk_class IN ('R0', 'R1', 'R2', 'R3'))"),
]


def _apply_column_migrations(conn) -> None:
    for table, column, ddl_type in _COLUMN_MIGRATIONS:
        existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}")


def init_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = get_connection(db_path)
    try:
        for statement in DDL_STATEMENTS:
            conn.execute(statement)
        _apply_column_migrations(conn)
        conn.commit()
    finally:
        conn.close()
