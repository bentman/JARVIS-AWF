import hashlib
import json

from awf.db.bootstrap import init_db
from awf.db.connection import get_connection
from awf.engine.run import create_run, create_step
from awf.gates.artifacts import write_finding_artifact, write_verdict_artifact
from awf.gates.schema import Finding, Verdict


def make_conn(tmp_path):
    db_path = tmp_path / "awf.db"
    init_db(db_path)
    conn = get_connection(db_path)
    create_run(conn, run_id="run-1", workflow_ref="demo@1.0.0")
    create_step(conn, step_id="step-1", run_id="run-1", node_id="check")
    return conn


def test_write_finding_artifact_persists_row_and_content_addressed_file(tmp_path):
    conn = make_conn(tmp_path)
    artifacts_root = tmp_path / "artifacts"
    finding = Finding(role="verifier", category="correctness", severity="high", summary="broken")

    artifact_id = write_finding_artifact(
        conn, artifacts_root=artifacts_root, run_id="run-1", step_id="step-1", finding=finding
    )

    row = conn.execute("SELECT * FROM artifacts WHERE artifact_id = ?", (artifact_id,)).fetchone()
    assert row["artifact_type"] == "finding"
    assert row["complete"] == 1
    target = artifacts_root / row["relative_path"]
    assert target.is_file()

    content = target.read_bytes()
    assert hashlib.sha256(content).hexdigest() == row["sha256"]
    decoded = json.loads(content)
    assert decoded == finding.to_dict()


def test_write_verdict_artifact_persists_row(tmp_path):
    conn = make_conn(tmp_path)
    artifacts_root = tmp_path / "artifacts"
    verdict = Verdict(passed=True, tier="default", findings=(), reason="no findings")

    artifact_id = write_verdict_artifact(
        conn, artifacts_root=artifacts_root, run_id="run-1", step_id="step-1", verdict=verdict
    )

    row = conn.execute("SELECT * FROM artifacts WHERE artifact_id = ?", (artifact_id,)).fetchone()
    assert row["artifact_type"] == "verdict"
    target = artifacts_root / row["relative_path"]
    assert target.is_file()

    content = target.read_bytes()
    assert hashlib.sha256(content).hexdigest() == row["sha256"]
    assert json.loads(content) == verdict.to_dict()


def test_identical_findings_produce_identical_content_hash(tmp_path):
    conn = make_conn(tmp_path)
    artifacts_root = tmp_path / "artifacts"
    finding = Finding(role="verifier", category="correctness", severity="low", summary="ok")

    id1 = write_finding_artifact(conn, artifacts_root=artifacts_root, run_id="run-1", step_id="step-1", finding=finding)
    id2 = write_finding_artifact(conn, artifacts_root=artifacts_root, run_id="run-1", step_id="step-1", finding=finding)

    assert id1 != id2  # independently generated rows, not the same insert

    row1 = conn.execute("SELECT sha256, relative_path FROM artifacts WHERE artifact_id = ?", (id1,)).fetchone()
    row2 = conn.execute("SELECT sha256, relative_path FROM artifacts WHERE artifact_id = ?", (id2,)).fetchone()
    assert row1["sha256"] == row2["sha256"]
    assert row1["relative_path"] == row2["relative_path"]  # same content-addressed path
