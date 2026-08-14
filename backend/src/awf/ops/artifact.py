"""artifact operation implementations."""

import sqlite3
from pathlib import Path

from awf.ops.shared import CoreOpError


def op_artifact_list(conn: sqlite3.Connection, *, run_id: str) -> list[dict]:
    rows = conn.execute("SELECT * FROM artifacts WHERE run_id = ? ORDER BY created_at", (run_id,)).fetchall()
    return [dict(row) for row in rows]


def op_artifact_read(conn: sqlite3.Connection, *, artifact_id: str, artifacts_root: Path) -> dict:
    row = conn.execute("SELECT * FROM artifacts WHERE artifact_id = ?", (artifact_id,)).fetchone()
    if row is None:
        raise CoreOpError(f"no such artifact: {artifact_id}")
    content = (artifacts_root / row["relative_path"]).read_text()
    return {**dict(row), "content": content}


__all__ = ("op_artifact_list", "op_artifact_read")
