"""Artifact helpers for governed machine actions."""

import sqlite3
from pathlib import Path

from awf.artifacts import write_artifact


def write_report_artifact(
    conn: sqlite3.Connection,
    *,
    artifacts_root: Path,
    run_id: str,
    step_id: str,
    payload: bytes,
    media_type: str,
) -> str:
    return write_artifact(
        conn,
        artifacts_root=artifacts_root,
        run_id=run_id,
        step_id=step_id,
        payload=payload,
        media_type=media_type,
        artifact_type="report",
    )
