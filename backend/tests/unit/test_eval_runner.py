import json
import sqlite3
import sys

import pytest

from awf.db.bootstrap import init_db
from awf.eval.runner import EvalRunnerError, run_evaluation
from awf.paths import artifacts_dir


@pytest.fixture
def eval_env(tmp_path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    db_path = repo_root / "data" / "awf_db" / "awf.db"
    init_db(db_path)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    from awf.engine.run import create_run, create_step

    create_run(conn, run_id="run-1", workflow_ref="self-improvement@1.0.0", input_json="{}")
    create_step(conn, step_id="run-1:eval#1", run_id="run-1", node_id="eval")
    conn.commit()

    worktree = repo_root / "cache" / "worktrees" / "run-1"
    worktree.mkdir(parents=True)

    try:
        yield repo_root, conn, worktree
    finally:
        conn.close()


def test_run_evaluation_success(eval_env):
    repo_root, conn, worktree = eval_env
    res = run_evaluation(
        repo_root,
        conn,
        run_id="run-1",
        step_id="run-1:eval#1",
        worktree=worktree,
        candidate_commit="commit-123",
        commands=[[sys.executable, "-c", "print('hello from eval')"]],
    )

    assert res["passed"] is True
    assert res["artifact_id"]

    row = conn.execute("SELECT * FROM artifacts WHERE artifact_id = ?", (res["artifact_id"],)).fetchone()
    assert row is not None
    assert row["artifact_type"] == "test-result"
    assert row["run_id"] == "run-1"
    assert row["step_id"] == "run-1:eval#1"

    data = json.loads((artifacts_dir(repo_root) / row["relative_path"]).read_text(encoding="utf-8"))
    assert data["passed"] is True
    assert data["candidate_commit"] == "commit-123"
    assert len(data["commands"]) == 1
    assert data["commands"][0]["exit_code"] == 0
    assert "hello from eval" in data["commands"][0]["stdout_snippet"]


def test_run_evaluation_failure(eval_env):
    repo_root, conn, worktree = eval_env
    res = run_evaluation(
        repo_root,
        conn,
        run_id="run-1",
        step_id="run-1:eval#1",
        worktree=worktree,
        candidate_commit="commit-456",
        commands=[[sys.executable, "-c", "import sys; sys.exit(2)"]],
    )

    assert res["passed"] is False
    row = conn.execute("SELECT * FROM artifacts WHERE artifact_id = ?", (res["artifact_id"],)).fetchone()
    assert row is not None
    data = json.loads((artifacts_dir(repo_root) / row["relative_path"]).read_text(encoding="utf-8"))
    assert data["passed"] is False
    assert data["commands"][0]["exit_code"] == 2


def test_run_evaluation_timeout(eval_env):
    repo_root, conn, worktree = eval_env
    res = run_evaluation(
        repo_root,
        conn,
        run_id="run-1",
        step_id="run-1:eval#1",
        worktree=worktree,
        candidate_commit="commit-789",
        commands=[[sys.executable, "-c", "import time; time.sleep(2)"]],
        timeout_seconds=0.1,
    )

    assert res["passed"] is False
    data = json.loads(
        (artifacts_dir(repo_root) / f"{res['artifact_id'][:2]}")
        if False
        else (
            artifacts_dir(repo_root)
            / conn.execute(
                "SELECT relative_path FROM artifacts WHERE artifact_id = ?", (res["artifact_id"],)
            ).fetchone()["relative_path"]
        ).read_text(encoding="utf-8")
    )
    assert data["passed"] is False
    assert data["commands"][0]["exit_code"] == -1
    assert "timed out" in data["commands"][0]["stderr_snippet"].lower()


def test_run_evaluation_nonexistent_worktree(eval_env):
    repo_root, conn, _worktree = eval_env
    bad_worktree = repo_root / "does_not_exist"
    with pytest.raises(EvalRunnerError, match="worktree directory does not exist"):
        run_evaluation(
            repo_root,
            conn,
            run_id="run-1",
            step_id="run-1:eval#1",
            worktree=bad_worktree,
        )
