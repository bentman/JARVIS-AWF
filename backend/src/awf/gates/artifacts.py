"""Persists Finding/Verdict records as content-addressed Artifacts (Section 7, 8).

Layout matches the registry convention: `data/artifacts/<sha256[0:2]>/<sha256>`.
"""

import json
import sqlite3
from pathlib import Path

from awf.artifacts import write_artifact
from awf.gates.schema import Finding, Verdict


def write_finding_artifact(
    conn: sqlite3.Connection, *, artifacts_root: Path, run_id: str, step_id: str, finding: Finding
) -> str:
    payload = json.dumps(finding.to_dict(), sort_keys=True).encode()
    return write_artifact(
        conn,
        artifacts_root=artifacts_root,
        run_id=run_id,
        step_id=step_id,
        payload=payload,
        media_type="application/json",
        artifact_type="finding",
    )


def write_verdict_artifact(
    conn: sqlite3.Connection, *, artifacts_root: Path, run_id: str, step_id: str, verdict: Verdict
) -> str:
    payload = json.dumps(verdict.to_dict(), sort_keys=True).encode()
    return write_artifact(
        conn,
        artifacts_root=artifacts_root,
        run_id=run_id,
        step_id=step_id,
        payload=payload,
        media_type="application/json",
        artifact_type="verdict",
    )
