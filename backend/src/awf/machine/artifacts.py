"""Artifact helpers for governed machine actions."""

import hashlib
import sqlite3
from pathlib import Path

from awf.clock import utc_now_rfc3339
from awf.ids import uuid7


def write_report_artifact(
    conn: sqlite3.Connection,
    *,
    artifacts_root: Path,
    run_id: str,
    step_id: str,
    payload: bytes,
    media_type: str,
) -> str:
    sha256 = hashlib.sha256(payload).hexdigest()
    relative_path = f"{sha256[:2]}/{sha256}"
    target = artifacts_root / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)
    artifact_id = uuid7()
    conn.execute(
        "INSERT INTO artifacts "
        "(artifact_id, run_id, step_id, sha256, relative_path, media_type, artifact_type, complete, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, 'report', 1, ?)",
        (artifact_id, run_id, step_id, sha256, relative_path, media_type, utc_now_rfc3339()),
    )
    conn.commit()
    return artifact_id
