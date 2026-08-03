import subprocess
from pathlib import Path

import pytest

from awf.adapters.base import AgentInvocation, AgentResult, AgentStatus
from awf.db.bootstrap import init_db
from awf.db.connection import get_connection
from awf.engine.agent_step import AgentStepError
from awf.engine.run import create_run, create_step
from awf.workflow.engine import make_agent_node_executor


def run_git(args, cwd):
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    return result


@pytest.fixture
def tmp_path(tmp_path):
    # A real git repo, since a successful agent Step commits the worktree
    # (isolation/worktree.py::commit_all_changes) - this doubles as both
    # `worktree_path` and `repo_root` in these tests, which only exercise
    # agentRef resolution, not the two roots' separate purposes.
    run_git(["init", "-q"], cwd=tmp_path)
    run_git(["config", "user.email", "t@e.com"], cwd=tmp_path)
    run_git(["config", "user.name", "T"], cwd=tmp_path)
    (tmp_path / "README.md").write_text("x\n")
    run_git(["add", "-A"], cwd=tmp_path)
    run_git(["commit", "-q", "-m", "init"], cwd=tmp_path)
    return tmp_path


@pytest.fixture
def conn(tmp_path):
    db_path = tmp_path / "awf.db"
    init_db(db_path)
    connection = get_connection(db_path)
    create_run(connection, run_id="run-1", workflow_ref="demo@1.0.0")
    create_step(connection, step_id="step-1", run_id="run-1", node_id="build")
    return connection


def publish_manifest(repo_root: Path, name: str, frontmatter: str, instructions: str = "Be helpful.") -> None:
    target = repo_root / "config" / "app_registry" / "agents" / name / "1.0.0.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(f"---\n{frontmatter}\n---\n\n{instructions}\n")


def test_agent_ref_supplies_adapter_role_and_instructions(tmp_path, conn):
    publish_manifest(
        tmp_path,
        "demo-builder",
        "name: demo-builder\nversion: 1.0.0\ndescription: x\nadapter: claude-code\nrole: builder\n",
        instructions="You are the demo builder.",
    )
    captured = {}

    def fake_adapter(invocation: AgentInvocation) -> AgentResult:
        captured["objective"] = invocation.objective
        return AgentResult(status=AgentStatus.COMPLETED, output={}, termination_reason="success")

    executor = make_agent_node_executor({"claude-code": fake_adapter}, tmp_path, tmp_path)
    node = {"id": "build", "type": "agent", "agentRef": "demo-builder@1.0.0", "objective": "add a feature"}

    output = executor(conn, "run-1", "step-1", node)

    assert output["status"] == "COMPLETED"
    assert "You are the demo builder." in captured["objective"]
    assert "add a feature" in captured["objective"]


def test_agent_ref_capabilities_becomes_the_real_guard_allowlist(tmp_path, conn):
    # ADR-0002: the manifest's `capabilities` is the ceiling - a node
    # declaring a capability NOT on that list must be denied before the
    # adapter ever runs, not rubber-stamped.
    publish_manifest(
        tmp_path,
        "restricted-verifier",
        "name: restricted-verifier\nversion: 1.0.0\ndescription: x\nadapter: codex\nrole: verifier\n"
        "capabilities: [allowed_action@1.0.0]\n",
    )
    adapter_calls = []

    def fake_adapter(invocation: AgentInvocation) -> AgentResult:
        adapter_calls.append(invocation)
        return AgentResult(status=AgentStatus.COMPLETED, output={}, termination_reason="success")

    executor = make_agent_node_executor({"codex": fake_adapter}, tmp_path, tmp_path)
    node = {"id": "build", "type": "agent", "agentRef": "restricted-verifier@1.0.0", "objective": "review"}
    # The node declares no `capability`, so the engine synthesizes one
    # (ref: agent_node_build@0.0.0) - that ref can never be on the
    # manifest's real allowlist, so it must be denied.
    with pytest.raises(AgentStepError):
        executor(conn, "run-1", "step-1", node)

    assert adapter_calls == []
    row = conn.execute("SELECT status, failure_class FROM steps WHERE step_id = 'step-1'").fetchone()
    assert row["status"] == "FAILED"
    assert row["failure_class"] == "POLICY_DENIED"


def test_agent_ref_voice_is_attached_to_the_step_output(tmp_path, conn):
    publish_manifest(
        tmp_path,
        "voiced-builder",
        "name: voiced-builder\nversion: 1.0.0\ndescription: x\nadapter: claude-code\nvoice: builder@1.0.0\n",
    )

    def fake_adapter(invocation: AgentInvocation) -> AgentResult:
        return AgentResult(status=AgentStatus.COMPLETED, output={}, termination_reason="success")

    executor = make_agent_node_executor({"claude-code": fake_adapter}, tmp_path, tmp_path)
    node = {"id": "build", "type": "agent", "agentRef": "voiced-builder@1.0.0", "objective": "add a feature"}

    output = executor(conn, "run-1", "step-1", node)

    assert output["voice"] == "builder@1.0.0"


def test_node_without_agent_ref_is_unaffected(tmp_path, conn):
    # Additive, not breaking: a node with no agentRef keeps today's
    # behavior exactly - raw `adapter`/`role` fields, self-permitting
    # allowlist fallback.
    def fake_adapter(invocation: AgentInvocation) -> AgentResult:
        return AgentResult(status=AgentStatus.COMPLETED, output={}, termination_reason="success")

    executor = make_agent_node_executor({"claude-code": fake_adapter}, tmp_path, tmp_path)
    node = {"id": "build", "type": "agent", "adapter": "claude-code", "objective": "add a feature"}

    output = executor(conn, "run-1", "step-1", node)

    assert output["status"] == "COMPLETED"
    assert "voice" not in output
