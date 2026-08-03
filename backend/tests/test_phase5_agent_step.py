import subprocess
from pathlib import Path

import pytest

from awf.adapters.base import AgentInvocation, AgentResult, AgentStatus
from awf.db.bootstrap import init_db
from awf.db.connection import get_connection
from awf.engine.agent_step import AgentStepError, run_agent_step
from awf.engine.run import create_run, create_step
from awf.isolation.worktree import create_worktree
from awf.registry.capability_record import CapabilityRecord, Effects, Identity


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
    row = conn.execute("SELECT status, failure_class FROM steps WHERE step_id = 'step-1'").fetchone()
    assert row["status"] == "FAILED"
    assert row["failure_class"] == "TOOL_ERROR"
    status = run_git(["status", "--porcelain"], cwd=worktree).stdout
    assert "partial.txt" in status  # written by the adapter, left uncommitted


def _capability(risk_class: str, approval: str) -> CapabilityRecord:
    return CapabilityRecord(
        identity=Identity(type="cli-adapter-action", provider="claude-code", name="demo_action", version="1.0.0"),
        schema_input="", schema_output="",
        effects=Effects(operation="update", reversible=True, idempotent=False, external_side_effect=True),
        risk_class=risk_class,
        approval=approval,
    )


def test_capability_guard_denies_r3_capability_before_adapter_runs(repo_and_worktree, conn):
    _repo_root, worktree = repo_and_worktree
    adapter_calls = []

    def adapter_fn(invocation: AgentInvocation) -> AgentResult:
        adapter_calls.append(invocation)
        return AgentResult(status=AgentStatus.COMPLETED, output={}, termination_reason="success")

    invocation = AgentInvocation(objective="do something forbidden", inputs={}, workspace_root=worktree)
    with pytest.raises(AgentStepError):
        run_agent_step(
            conn,
            step_id="step-1",
            run_id="run-1",
            worktree_path=worktree,
            invocation=invocation,
            adapter_fn=adapter_fn,
            commit_message="should never be used",
            capability=_capability("R3", "never"),
        )

    assert adapter_calls == []  # the Guard blocked it before the adapter ever ran
    row = conn.execute("SELECT status, failure_class FROM steps WHERE step_id = 'step-1'").fetchone()
    assert row["status"] == "FAILED"
    assert row["failure_class"] == "POLICY_DENIED"


def test_capability_guard_allows_r1_capability_and_adapter_runs(repo_and_worktree, conn):
    _repo_root, worktree = repo_and_worktree

    def adapter_fn(invocation: AgentInvocation) -> AgentResult:
        return AgentResult(status=AgentStatus.COMPLETED, output={}, termination_reason="success")

    invocation = AgentInvocation(objective="do something safe", inputs={}, workspace_root=worktree)
    output = run_agent_step(
        conn,
        step_id="step-1",
        run_id="run-1",
        worktree_path=worktree,
        invocation=invocation,
        adapter_fn=adapter_fn,
        commit_message="agent: safe action",
        capability=_capability("R1", "never"),
    )

    assert output["status"] == "COMPLETED"
    row = conn.execute("SELECT status FROM steps WHERE step_id = 'step-1'").fetchone()
    assert row["status"] == "SUCCEEDED"


def test_real_agent_allowlist_denies_a_capability_not_listed(repo_and_worktree, conn):
    # ADR-0002: a real (non-singleton) allowlist must actually be able to
    # fail - the pre-ADR-0002 default (agent_allowlist=None) fell back to a
    # self-permitting singleton that could never deny anything.
    _repo_root, worktree = repo_and_worktree
    adapter_calls = []

    def adapter_fn(invocation: AgentInvocation) -> AgentResult:
        adapter_calls.append(invocation)
        return AgentResult(status=AgentStatus.COMPLETED, output={}, termination_reason="success")

    invocation = AgentInvocation(objective="do something not on the list", inputs={}, workspace_root=worktree)
    with pytest.raises(AgentStepError):
        run_agent_step(
            conn,
            step_id="step-1",
            run_id="run-1",
            worktree_path=worktree,
            invocation=invocation,
            adapter_fn=adapter_fn,
            commit_message="should never be used",
            capability=_capability("R1", "never"),
            agent_allowlist=["some_other_capability@1.0.0"],
        )

    assert adapter_calls == []
    row = conn.execute("SELECT status, failure_class FROM steps WHERE step_id = 'step-1'").fetchone()
    assert row["status"] == "FAILED"
    assert row["failure_class"] == "POLICY_DENIED"


def test_real_agent_allowlist_allows_a_listed_capability(repo_and_worktree, conn):
    _repo_root, worktree = repo_and_worktree

    def adapter_fn(invocation: AgentInvocation) -> AgentResult:
        return AgentResult(status=AgentStatus.COMPLETED, output={}, termination_reason="success")

    capability = _capability("R1", "never")
    invocation = AgentInvocation(objective="do something on the list", inputs={}, workspace_root=worktree)
    output = run_agent_step(
        conn,
        step_id="step-1",
        run_id="run-1",
        worktree_path=worktree,
        invocation=invocation,
        adapter_fn=adapter_fn,
        commit_message="agent: listed action",
        capability=capability,
        agent_allowlist=[capability.ref],
    )

    assert output["status"] == "COMPLETED"
    row = conn.execute("SELECT status FROM steps WHERE step_id = 'step-1'").fetchone()
    assert row["status"] == "SUCCEEDED"
