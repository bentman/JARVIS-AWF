"""Persists Finding/Verdict records as content-addressed Artifacts (Section 7, 8).

Layout matches the registry convention: `data/artifacts/<sha256[0:2]>/<sha256>`.
"""

import hashlib
import json
import sqlite3
from pathlib import Path

from awf.clock import utc_now_rfc3339
from awf.gates.schema import Finding, Verdict
from awf.ids import uuid7


def _write_content_addressed(artifacts_root: Path, payload: bytes) -> tuple[str, str]:
    sha256 = hashlib.sha256(payload).hexdigest()
    relative_path = f"{sha256[:2]}/{sha256}"
    target = artifacts_root / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)
    return sha256, relative_path


def _insert_artifact_row(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    step_id: str,
    sha256: str,
    relative_path: str,
    artifact_type: str,
) -> str:
    artifact_id = uuid7()
    conn.execute(
        "INSERT INTO artifacts "
        "(artifact_id, run_id, step_id, sha256, relative_path, media_type, artifact_type, complete, created_at) "
        "VALUES (?, ?, ?, ?, ?, 'application/json', ?, 1, ?)",
        (artifact_id, run_id, step_id, sha256, relative_path, artifact_type, utc_now_rfc3339()),
    )
    conn.commit()
    return artifact_id


def write_finding_artifact(
    conn: sqlite3.Connection, *, artifacts_root: Path, run_id: str, step_id: str, finding: Finding
) -> str:
    payload = json.dumps(finding.to_dict(), sort_keys=True).encode()
    sha256, relative_path = _write_content_addressed(artifacts_root, payload)
    return _insert_artifact_row(
        conn, run_id=run_id, step_id=step_id, sha256=sha256, relative_path=relative_path, artifact_type="finding"
    )


def write_verdict_artifact(
    conn: sqlite3.Connection, *, artifacts_root: Path, run_id: str, step_id: str, verdict: Verdict
) -> str:
    payload = json.dumps(verdict.to_dict(), sort_keys=True).encode()
    sha256, relative_path = _write_content_addressed(artifacts_root, payload)
    return _insert_artifact_row(
        conn, run_id=run_id, step_id=step_id, sha256=sha256, relative_path=relative_path, artifact_type="verdict"
    )
