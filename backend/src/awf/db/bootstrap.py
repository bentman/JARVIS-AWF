"""Idempotent creation of data/awf_db/awf.db (Phase 0 exit condition)."""

from pathlib import Path

from awf.db.connection import get_connection
from awf.db.schema import DDL_STATEMENTS


def init_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = get_connection(db_path)
    try:
        for statement in DDL_STATEMENTS:
            conn.execute(statement)
        conn.commit()
    finally:
        conn.close()
