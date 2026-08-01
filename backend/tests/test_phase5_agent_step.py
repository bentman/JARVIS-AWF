import subprocess
from pathlib import Path

import pytest

from awf.adapters.base import AgentInvocation, AgentResult, AgentStatus
from awf.db.bootstrap import init_db
from awf.db.connection import get_connection
from awf.engine.agent_step import AgentStepError, run_agent_step
from awf.engine.run import create_run, create_step
from awf.isolation.worktree import create_worktree


def run_git(args, cwd):
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    return result


@pytest.fixture
def repo_and_worktree(tmp_path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    run_git(["init", "-q"], cwd=repo_root)
    run_git(["config", "user.email", "test@example.com"], cwd=repo_root)
    run_git(["config", "user.name", "Test"], cwd=repo_root)
    (repo_root / "README.md").write_text("hello\n")
    run_git(["add", "-A"], cwd=repo_root)
    run_git(["commit", "-q", "-m", "init"], cwd=repo_root)

    worktree = create_worktree(repo_root, "run-1")
    return repo_root, worktree


@pytest.fixture
def conn(tmp_path):
    db_path = tmp_path / "awf.db"
    init_db(db_path)
    connection = get_connection(db_path)
    create_run(connection, run_id="run-1", workflow_ref="agent-node@1.0.0")
    create_step(connection, step_id="step-1", run_id="run-1", node_id="agent-node")
    return connection


def test_commit_happens_only_after_step_marked_succeeded(repo_and_worktree, conn, monkeypatch):
    _repo_root, worktree = repo_and_worktree
    step_status_at_commit_time = {}

    def fake_adapter(invocation: AgentInvocation) -> AgentResult:
        (worktree / "new_file.txt").write_text("from the agent\n")
        return AgentResult(status=AgentStatus.COMPLETED, output={}, termination_reason="success")

    import awf.engine.agent_step as agent_step_module

    real_commit = agent_step_module.commit_all_changes

    def spying_commit(worktree_path, message):
        row = conn.execute("SELECT status FROM steps WHERE step_id = 'step-1'").fetchone()
        step_status_at_commit_time["status"] = row["status"]
        return real_commit(worktree_path, message)

    monkeypatch.setattr(agent_step_module, "commit_all_changes", spying_commit)

    invocation = AgentInvocation(objective="add a file", inputs={}, workspace_root=worktree)
    output = run_agent_step(
        conn,
        step_id="step-1",
        run_id="run-1",
        worktree_path=worktree,
        invocation=invocation,
        adapter_fn=fake_adapter,
        commit_message="agent: add new_file.txt",
    )

    assert step_status_at_commit_time["status"] == "SUCCEEDED"
    assert output["commit_sha"]
    log = run_git(["log", "--oneline", "-1"], cwd=worktree).stdout
    assert "agent: add new_file.txt" in log


def test_no_commit_when_adapter_does_not_complete(repo_and_worktree, conn, monkeypatch):
    _repo_root, worktree = repo_and_worktree

    def failing_adapter(invocation: AgentInvocation) -> AgentResult:
        (worktree / "partial.txt").write_text("uncommitted work\n")
        return AgentResult(status=AgentStatus.FAILED, output={}, termination_reason="tool_error")

    import awf.engine.agent_step as agent_step_module
    commit_calls = []
    monkeypatch.setattr(
        agent_step_module, "commit_all_changes",
        lambda *a, **k: commit_calls.append((a, k)),
    )

    invocation = AgentInvocation(objective="do something risky", inputs={}, workspace_root=worktree)
    with pytest.raises(AgentStepError):
        run_agent_step(
            conn,
            step_id="step-1",
            run_id="run-1",
            worktree_path=worktree,
            invocation=invocation,
            adapter_fn=failing_adapter,
            commit_message="should never be used",
        )

    assert commit_calls == []
    row = conn.execute("SELECT status FROM steps WHERE step_id = 'step-1'").fetchone()
    assert row["status"] == "RUNNING"
    status = run_git(["status", "--porcelain"], cwd=worktree).stdout
    assert "partial.txt" in status  # written by the adapter, left uncommitted
