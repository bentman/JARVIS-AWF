from pathlib import Path

import pytest
import yaml
from cryptography.fernet import Fernet

from awf.cli.core_ops import (
    CoreOpError,
    op_approval_approve,
    op_approval_list,
    op_approval_reject,
    op_artifact_list,
    op_artifact_read,
    op_registry_get,
    op_registry_list,
    op_registry_publish,
    op_registry_validate,
    op_run_list,
    op_run_start,
    op_run_status,
    op_secret_list_names,
    op_secret_set,
)
from awf.db.bootstrap import init_db
from awf.db.connection import get_connection
from awf.engine.run import create_run, create_step
from awf.gates.artifacts import write_finding_artifact
from awf.gates.schema import Finding
from awf.ids import uuid7

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def make_repo(tmp_path):
    repo_root = tmp_path / "repo"
    (repo_root / "data" / "awf_db").mkdir(parents=True)
    (repo_root / "data" / "registry").mkdir(parents=True)
    (repo_root / "config" / "app_registry").mkdir(parents=True)
    db_path = repo_root / "data" / "awf_db" / "awf.db"
    init_db(db_path)
    conn = get_connection(db_path)
    return repo_root, conn


def test_run_status_raises_for_unknown_run(tmp_path):
    _repo_root, conn = make_repo(tmp_path)
    with pytest.raises(CoreOpError):
        op_run_status(conn, run_id="does-not-exist")


def test_run_status_and_list_reflect_real_rows(tmp_path):
    _repo_root, conn = make_repo(tmp_path)
    create_run(conn, run_id="run-1", workflow_ref="demo@1.0.0")
    create_step(conn, step_id="s1", run_id="run-1", node_id="n1")

    status = op_run_status(conn, run_id="run-1")
    assert status["run_id"] == "run-1"
    assert len(status["steps"]) == 1

    listed = op_run_list(conn)
    assert [r["run_id"] for r in listed] == ["run-1"]


def make_approval(conn, approval_id="ap-1", run_id="run-1", status="pending"):
    conn.execute(
        "INSERT INTO approvals (approval_id, run_id, step_id, action_digest, status, requested_at) "
        "VALUES (?, ?, 's1', 'sha256:deadbeef', ?, '2026-01-01T00:00:00Z')",
        (approval_id, run_id, status),
    )
    conn.commit()


def test_approval_list_shows_only_pending(tmp_path):
    _repo_root, conn = make_repo(tmp_path)
    create_run(conn, run_id="run-1", workflow_ref="demo@1.0.0")
    create_step(conn, step_id="s1", run_id="run-1", node_id="n1")
    make_approval(conn, "ap-1", status="pending")
    make_approval(conn, "ap-2", status="approved")

    pending = op_approval_list(conn)
    assert [a["approval_id"] for a in pending] == ["ap-1"]


def test_approve_then_reject_raises_already_decided(tmp_path):
    _repo_root, conn = make_repo(tmp_path)
    create_run(conn, run_id="run-1", workflow_ref="demo@1.0.0")
    create_step(conn, step_id="s1", run_id="run-1", node_id="n1")
    make_approval(conn, "ap-1")

    result = op_approval_approve(conn, approval_id="ap-1")
    assert result["status"] == "approved"

    with pytest.raises(CoreOpError):
        op_approval_reject(conn, approval_id="ap-1", reason="too late")


def test_reject_records_reason(tmp_path):
    _repo_root, conn = make_repo(tmp_path)
    create_run(conn, run_id="run-1", workflow_ref="demo@1.0.0")
    create_step(conn, step_id="s1", run_id="run-1", node_id="n1")
    make_approval(conn, "ap-1")

    result = op_approval_reject(conn, approval_id="ap-1", reason="not safe")
    assert result == {"approval_id": "ap-1", "status": "rejected", "reason": "not safe"}


def test_approval_actions_raise_for_unknown_id(tmp_path):
    _repo_root, conn = make_repo(tmp_path)
    with pytest.raises(CoreOpError):
        op_approval_approve(conn, approval_id="does-not-exist")


def test_artifact_list_and_read(tmp_path):
    repo_root, conn = make_repo(tmp_path)
    create_run(conn, run_id="run-1", workflow_ref="demo@1.0.0")
    create_step(conn, step_id="s1", run_id="run-1", node_id="check")
    artifacts_root = repo_root / "data" / "artifacts"
    finding = Finding(role="verifier", category="correctness", severity="low", summary="ok")
    artifact_id = write_finding_artifact(
        conn, artifacts_root=artifacts_root, run_id="run-1", step_id="s1", finding=finding
    )

    listed = op_artifact_list(conn, run_id="run-1")
    assert [a["artifact_id"] for a in listed] == [artifact_id]

    read = op_artifact_read(conn, artifact_id=artifact_id, artifacts_root=artifacts_root)
    assert '"summary": "ok"' in read["content"]


def test_registry_validate_recognizes_capability_record():
    result = op_registry_validate(FIXTURES / "capabilities" / "read_file_r0.yaml")
    assert result["kind"] == "CapabilityRecord"
    assert result["valid"] is True


def test_registry_validate_rejects_garbage(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("just: a random mapping\n")
    with pytest.raises(CoreOpError):
        op_registry_validate(bad)


def test_registry_publish_capability_record_writes_data_registry_and_index(tmp_path):
    repo_root, conn = make_repo(tmp_path)
    source = FIXTURES / "capabilities" / "read_file_r0.yaml"

    result = op_registry_publish(repo_root, conn, path=source)

    assert result["kind"] == "capabilities"
    published_path = Path(result["path"])
    assert published_path.is_file()
    assert published_path.read_bytes() == source.read_bytes()

    row = conn.execute(
        "SELECT * FROM registry_index WHERE kind = ? AND name = ? AND version = ?",
        (result["kind"], result["name"], result["version"]),
    ).fetchone()
    assert row["source"] == "data"
    assert row["trust_status"] == "local"
    assert row["digest"] == result["digest"]


def test_registry_publish_then_list_and_get_find_it(tmp_path):
    repo_root, conn = make_repo(tmp_path)
    source = FIXTURES / "capabilities" / "read_file_r0.yaml"
    published = op_registry_publish(repo_root, conn, path=source)

    listed = op_registry_list(repo_root, kind="capabilities")
    assert {"source": "data", "kind": "capabilities", "name": published["name"], "version": published["version"]} in listed

    fetched = op_registry_get(repo_root, kind="capabilities", name=published["name"], version=published["version"])
    assert fetched["source"] == "data"


def test_secret_set_and_list_names_roundtrip(tmp_path):
    repo_root, conn = make_repo(tmp_path)
    key = Fernet.generate_key().decode("ascii")
    (repo_root / ".env").write_text(f"AWF_SECRET_KEY={key}\n")

    op_secret_set(repo_root, conn, name="api-key", value="sekret")

    assert op_secret_list_names(conn) == ["api-key"]


def make_git_repo(tmp_path):
    import subprocess

    repo_root, conn = make_repo(tmp_path)
    subprocess.run(["git", "init", "-q"], cwd=repo_root, check=True)
    subprocess.run(["git", "config", "user.email", "t@e.com"], cwd=repo_root, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=repo_root, check=True)
    (repo_root / "README.md").write_text("x\n")
    subprocess.run(["git", "add", "-A"], cwd=repo_root, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=repo_root, check=True)
    return repo_root, conn


def publish_workflow(repo_root, raw: dict) -> None:
    target = repo_root / "config" / "app_registry" / "workflows" / raw["metadata"]["name"] / f"{raw['metadata']['version']}.yaml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(yaml.safe_dump(raw))


def test_op_run_start_fails_cleanly_for_an_unbuilt_node_type(tmp_path):
    # `subworkflow` validates as a real Section 12.2 node type but has no
    # executor built - op_run_start MUST NOT let that raise a raw exception;
    # the Run is marked FAILED and a clean result is returned instead.
    repo_root, conn = make_git_repo(tmp_path)
    publish_workflow(
        repo_root,
        {
            "apiVersion": "awf/v1",
            "kind": "Workflow",
            "metadata": {"name": "unbuilt-node-demo", "version": "1.0.0", "digest": "sha256:demo"},
            "spec": {
                "inputSchema": {}, "outputSchema": {}, "budgets": {},
                "nodes": [{"id": "a", "type": "subworkflow", "next": None}],
                "outputs": {},
            },
        },
    )

    result = op_run_start(repo_root, conn, workflow_ref="unbuilt-node-demo@1.0.0", input_data={})

    assert result["status"] == "FAILED"
    assert "error" in result
    row = conn.execute("SELECT status FROM runs WHERE run_id = ?", (result["run_id"],)).fetchone()
    assert row["status"] == "FAILED"
