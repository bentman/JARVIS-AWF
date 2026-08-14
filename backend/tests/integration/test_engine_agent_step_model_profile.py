import subprocess

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


def _write_profile(repo_root, name="local-model", candidates_yaml=None):
    profile_dir = repo_root / "data" / "registry" / "model-profiles" / name
    profile_dir.mkdir(parents=True)
    candidates_yaml = candidates_yaml or (
        "candidates:\n"
        "  - {provider: ollama, model: qwen3-vl:8b, priority: 1, enabled: true}\n"
        "  - {provider: openai, model: gpt-4o, priority: 2, enabled: false}\n"
    )
    (profile_dir / "1.0.0.yaml").write_text(
        f"name: {name}\nversion: 1.0.0\n"
        "purpose: general-reasoning\n"
        "privacy: {maximum_data_class: internal, local_only: true}\n"
        f"{candidates_yaml}"
        "fallback: {mode: ordered, allow_quality_degrade: true}\n"
        "limits: {max_input_tokens_per_call: 8192, max_output_tokens_per_call: 2048, max_cost_usd_per_call: 0.0}\n"
    )


def _run(conn, worktree, repo_root, adapter_fn, *, model_profile_ref=None):
    invocation = AgentInvocation(objective="the real task", inputs={}, workspace_root=worktree)
    return run_agent_step(
        conn,
        step_id="step-1",
        run_id="run-1",
        worktree_path=worktree,
        invocation=invocation,
        adapter_fn=adapter_fn,
        commit_message="agent: model profile test",
        actor="claude-code",
        model_profile_ref=model_profile_ref,
        repo_root=repo_root,
    )


def test_winning_candidate_reaches_the_adapter_via_constraints(repo_and_worktree, conn):
    repo_root, worktree = repo_and_worktree
    _write_profile(repo_root)
    seen = {}

    def adapter_fn(invocation: AgentInvocation) -> AgentResult:
        seen["invocation"] = invocation
        return AgentResult(status=AgentStatus.COMPLETED, output={}, termination_reason="success")

    _run(conn, worktree, repo_root, adapter_fn, model_profile_ref="local-model@1.0.0")

    assert seen["invocation"].constraints["model_override"] == "qwen3-vl:8b"
    assert seen["invocation"].constraints["model_override_provider"] == "ollama"


def test_disabled_candidate_is_never_picked(repo_and_worktree, conn):
    repo_root, worktree = repo_and_worktree
    _write_profile(
        repo_root,
        candidates_yaml=(
            "candidates:\n"
            "  - {provider: ollama, model: winner, priority: 1, enabled: true}\n"
            "  - {provider: openai, model: should-not-win, priority: 0, enabled: false}\n"
        ),
    )
    seen = {}

    def adapter_fn(invocation: AgentInvocation) -> AgentResult:
        seen["invocation"] = invocation
        return AgentResult(status=AgentStatus.COMPLETED, output={}, termination_reason="success")

    _run(conn, worktree, repo_root, adapter_fn, model_profile_ref="local-model@1.0.0")

    assert seen["invocation"].constraints["model_override"] == "winner"


def test_no_enabled_candidates_fails_the_step_before_the_adapter_runs(repo_and_worktree, conn):
    repo_root, worktree = repo_and_worktree
    _write_profile(
        repo_root,
        candidates_yaml="candidates:\n  - {provider: openai, model: x, priority: 1, enabled: false}\n",
    )
    adapter_calls = []

    def adapter_fn(invocation: AgentInvocation) -> AgentResult:
        adapter_calls.append(invocation)
        return AgentResult(status=AgentStatus.COMPLETED, output={}, termination_reason="success")

    with pytest.raises(AgentStepError):
        _run(conn, worktree, repo_root, adapter_fn, model_profile_ref="local-model@1.0.0")

    assert adapter_calls == []
    row = conn.execute("SELECT status, failure_class FROM steps WHERE step_id = 'step-1'").fetchone()
    assert row["status"] == "FAILED"
    assert row["failure_class"] == "INVALID_INPUT"


def test_no_model_profile_ref_leaves_invocation_unmodified(repo_and_worktree, conn):
    repo_root, worktree = repo_and_worktree
    seen = {}

    def adapter_fn(invocation: AgentInvocation) -> AgentResult:
        seen["invocation"] = invocation
        return AgentResult(status=AgentStatus.COMPLETED, output={}, termination_reason="success")

    _run(conn, worktree, repo_root, adapter_fn)

    assert "model_override" not in seen["invocation"].constraints
