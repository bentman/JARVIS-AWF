"""Shared content-addressed artifact persistence."""

import hashlib
import sqlite3
from pathlib import Path

from awf.clock import utc_now_rfc3339
from awf.ids import uuid7


def write_content_addressed(artifacts_root: Path, payload: bytes) -> tuple[str, str]:
    sha256 = hashlib.sha256(payload).hexdigest()
    relative_path = f"{sha256[:2]}/{sha256}"
    target = artifacts_root / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)
    return sha256, relative_path


def insert_artifact_row(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    step_id: str,
    sha256: str,
    relative_path: str,
    media_type: str,
    artifact_type: str,
) -> str:
    artifact_id = uuid7()
    conn.execute(
        "INSERT INTO artifacts "
        "(artifact_id, run_id, step_id, sha256, relative_path, media_type, artifact_type, complete, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)",
        (artifact_id, run_id, step_id, sha256, relative_path, media_type, artifact_type, utc_now_rfc3339()),
    )
    conn.commit()
    return artifact_id


def write_artifact(
    conn: sqlite3.Connection,
    *,
    artifacts_root: Path,
    run_id: str,
    step_id: str,
    payload: bytes,
    media_type: str,
    artifact_type: str,
) -> str:
    sha256, relative_path = write_content_addressed(artifacts_root, payload)
    return insert_artifact_row(
        conn,
        run_id=run_id,
        step_id=step_id,
        sha256=sha256,
        relative_path=relative_path,
        media_type=media_type,
        artifact_type=artifact_type,
    )
