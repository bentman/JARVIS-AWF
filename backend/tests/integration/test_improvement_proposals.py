import json
from pathlib import Path

import pytest
from backend.tests.support import run_git

from awf.db.bootstrap import init_db
from awf.db.connection import get_connection
from awf.engine.run import create_run, create_step
from awf.gates.artifacts import write_verdict_artifact
from awf.gates.schema import Verdict
from awf.isolation.worktree import branch_name, commit_all_changes, create_worktree, worktree_path
from awf.ops.improvement import (
    op_improvement_mark_ready,
    op_improvement_merge,
    op_improvement_prepare,
    op_improvement_reject,
    op_improvement_request_merge,
)
from awf.ops.shared import CoreOpError
from awf.paths import artifacts_dir


@pytest.fixture
def repo_conn(tmp_path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    run_git(["init", "-q"], cwd=repo_root)
    run_git(["config", "user.email", "test@example.com"], cwd=repo_root)
    run_git(["config", "user.name", "Test"], cwd=repo_root)
    (repo_root / ".gitignore").write_text("data/\ncache/\n")
    (repo_root / "README.md").write_text("hello\n")
    run_git(["add", "-A"], cwd=repo_root)
    run_git(["commit", "-q", "-m", "init"], cwd=repo_root)
    db_path = repo_root / "data" / "awf_db" / "awf.db"
    init_db(db_path)
    conn = get_connection(db_path)
    try:
        yield repo_root, conn
    finally:
        conn.close()


def _seed_successful_candidate(repo_root: Path, conn, run_id: str = "run-1") -> str:
    create_run(
        conn,
        run_id=run_id,
        workflow_ref="self-improvement@1.0.0",
        input_json=json.dumps({"retainWorktreeForImprovement": True}),
    )
    create_step(conn, step_id=f"{run_id}:agent#1", run_id=run_id, node_id="agent")
    worktree = create_worktree(repo_root, run_id)
    (worktree / "feature.txt").write_text("candidate\n")
    commit_all_changes(worktree, "candidate change")
    conn.execute("UPDATE runs SET status = 'SUCCEEDED' WHERE run_id = ?", (run_id,))
    conn.execute("UPDATE steps SET status = 'SUCCEEDED' WHERE step_id = ?", (f"{run_id}:agent#1",))
    conn.commit()
    return run_id


def _write_verdict(repo_root: Path, conn, run_id: str, *, passed: bool = True) -> str:
    return write_verdict_artifact(
        conn,
        artifacts_root=artifacts_dir(repo_root),
        run_id=run_id,
        step_id=f"{run_id}:agent#1",
        verdict=Verdict(passed=passed, tier="default", findings=(), reason="ok" if passed else "failed"),
    )


def test_prepare_records_diff_identity_and_patch_artifact(repo_conn):
    repo_root, conn = repo_conn
    run_id = _seed_successful_candidate(repo_root, conn)

    proposal = op_improvement_prepare(repo_root, conn, run_id=run_id, summary="Focused fix")

    assert proposal["status"] == "draft"
    assert proposal["summary"] == "Focused fix"
    assert proposal["candidate_branch"] == branch_name(run_id)
    assert proposal["candidate_commit"]
    assert proposal["base_commit"]
    assert proposal["diff_digest"].startswith("sha256:")
    assert proposal["patch_artifact_id"]
    assert proposal["changed_paths"][0]["path"] == "feature.txt"
    assert proposal["events"][0]["event_type"] == "created"


def test_prepare_after_amend_updates_digest_and_resets_review_state(repo_conn):
    repo_root, conn = repo_conn
    run_id = _seed_successful_candidate(repo_root, conn)
    first = op_improvement_prepare(repo_root, conn, run_id=run_id)
    verdict_id = _write_verdict(repo_root, conn, run_id)
    ready = op_improvement_mark_ready(
        repo_root,
        conn,
        improvement_id=first["improvement_id"],
        verdict_artifact_id=verdict_id,
        validation_artifact_ids=[],
    )
    assert ready["status"] == "ready_for_review"

    worktree = worktree_path(repo_root, run_id)
    (worktree / "feature.txt").write_text("candidate amended\n")
    commit_all_changes(worktree, "candidate amendment")
    second = op_improvement_prepare(repo_root, conn, run_id=run_id)

    assert second["improvement_id"] == first["improvement_id"]
    assert second["diff_digest"] != first["diff_digest"]
    assert second["status"] == "draft"
    assert second["verdict_artifact_id"] is None


def test_mark_ready_requires_passing_verdict(repo_conn):
    repo_root, conn = repo_conn
    run_id = _seed_successful_candidate(repo_root, conn)
    proposal = op_improvement_prepare(repo_root, conn, run_id=run_id)
    failed_verdict = _write_verdict(repo_root, conn, run_id, passed=False)

    with pytest.raises(CoreOpError, match="did not pass"):
        op_improvement_mark_ready(
            repo_root,
            conn,
            improvement_id=proposal["improvement_id"],
            verdict_artifact_id=failed_verdict,
            validation_artifact_ids=[],
        )


def test_request_merge_creates_step_and_exact_approval(repo_conn):
    repo_root, conn = repo_conn
    run_id = _seed_successful_candidate(repo_root, conn)
    proposal = op_improvement_prepare(repo_root, conn, run_id=run_id)
    verdict_id = _write_verdict(repo_root, conn, run_id)
    ready = op_improvement_mark_ready(
        repo_root,
        conn,
        improvement_id=proposal["improvement_id"],
        verdict_artifact_id=verdict_id,
        validation_artifact_ids=[],
    )

    requested = op_improvement_request_merge(repo_root, conn, improvement_id=ready["improvement_id"])

    approval = requested["approval"]
    assert approval["risk_class"] == "R2"
    assert approval["action_digest"] == ready["merge_action_digest"]
    step = conn.execute("SELECT * FROM steps WHERE step_id = ?", (approval["step_id"],)).fetchone()
    assert step["node_id"] == "improvement.merge"
    assert step["status"] == "WAITING_APPROVAL"


def test_merge_requires_approved_matching_digest_and_merges(repo_conn):
    repo_root, conn = repo_conn
    run_id = _seed_successful_candidate(repo_root, conn)
    proposal = op_improvement_prepare(repo_root, conn, run_id=run_id)
    verdict_id = _write_verdict(repo_root, conn, run_id)
    ready = op_improvement_mark_ready(
        repo_root,
        conn,
        improvement_id=proposal["improvement_id"],
        verdict_artifact_id=verdict_id,
        validation_artifact_ids=[],
    )
    requested = op_improvement_request_merge(repo_root, conn, improvement_id=ready["improvement_id"])

    with pytest.raises(CoreOpError, match="not approved"):
        op_improvement_merge(
            repo_root, conn, improvement_id=ready["improvement_id"], approval_id=requested["approval"]["approval_id"]
        )

    conn.execute(
        "UPDATE approvals SET status = 'approved' WHERE approval_id = ?",
        (requested["approval"]["approval_id"],),
    )
    conn.commit()
    merged = op_improvement_merge(
        repo_root, conn, improvement_id=ready["improvement_id"], approval_id=requested["approval"]["approval_id"]
    )

    assert merged["status"] == "merged"
    assert merged["merge_commit"] == run_git(["rev-parse", "HEAD"], cwd=repo_root).stdout.strip()
    assert (repo_root / "feature.txt").read_text() == "candidate\n"
    assert not worktree_path(repo_root, run_id).exists()


def test_changed_candidate_invalidates_merge_approval(repo_conn):
    repo_root, conn = repo_conn
    run_id = _seed_successful_candidate(repo_root, conn)
    proposal = op_improvement_prepare(repo_root, conn, run_id=run_id)
    verdict_id = _write_verdict(repo_root, conn, run_id)
    ready = op_improvement_mark_ready(
        repo_root,
        conn,
        improvement_id=proposal["improvement_id"],
        verdict_artifact_id=verdict_id,
        validation_artifact_ids=[],
    )
    requested = op_improvement_request_merge(repo_root, conn, improvement_id=ready["improvement_id"])
    conn.execute(
        "UPDATE approvals SET status = 'approved' WHERE approval_id = ?",
        (requested["approval"]["approval_id"],),
    )
    conn.commit()

    worktree = worktree_path(repo_root, run_id)
    (worktree / "feature.txt").write_text("changed after approval\n")
    commit_all_changes(worktree, "post approval change")

    with pytest.raises(CoreOpError, match="candidate commit changed"):
        op_improvement_merge(
            repo_root, conn, improvement_id=ready["improvement_id"], approval_id=requested["approval"]["approval_id"]
        )


def test_reject_closes_without_merging(repo_conn):
    repo_root, conn = repo_conn
    run_id = _seed_successful_candidate(repo_root, conn)
    proposal = op_improvement_prepare(repo_root, conn, run_id=run_id)

    rejected = op_improvement_reject(repo_root, conn, improvement_id=proposal["improvement_id"], reason="not now")

    assert rejected["status"] == "rejected"
    assert not (repo_root / "feature.txt").exists()
    assert not worktree_path(repo_root, run_id).exists()
