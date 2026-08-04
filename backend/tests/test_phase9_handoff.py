import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from awf.adapters.base import AgentResult, AgentStatus
from awf.db.bootstrap import init_db
from awf.db.connection import get_connection
from awf.engine.run import create_run
from awf.workflow.definition import parse_workflow
from awf.workflow.engine import run_workflow_definition
from awf.workflow.handoff import make_handoff_node_executor


def run_git(args, cwd):
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    return result


@pytest.fixture
def worktree(tmp_path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    run_git(["init", "-q"], cwd=repo_root)
    run_git(["config", "user.email", "t@e.com"], cwd=repo_root)
    run_git(["config", "user.name", "T"], cwd=repo_root)
    (repo_root / "README.md").write_text("x\n")
    run_git(["add", "-A"], cwd=repo_root)
    run_git(["commit", "-q", "-m", "init"], cwd=repo_root)
    return repo_root


@pytest.fixture
def conn(tmp_path):
    db_path = tmp_path / "awf.db"
    init_db(db_path)
    connection = get_connection(db_path)
    create_run(connection, run_id="run-1", workflow_ref="handoff-demo@1.0.0")
    return connection


def make_handoff_workflow(max_hops=4, payload_schema=None):
    return parse_workflow(
        {
            "apiVersion": "awf/v1",
            "kind": "Workflow",
            "metadata": {"name": "handoff-demo", "version": "1.0.0", "digest": "sha256:abc"},
            "spec": {
                "inputSchema": {}, "outputSchema": {}, "budgets": {},
                "nodes": [
                    {
                        "id": "loop",
                        "type": "handoff",
                        "initiatingAgent": {"adapter": "a", "objective": "draft"},
                        "receivingAgent": {"adapter": "b", "objective": "review"},
                        "payloadSchema": payload_schema or {"type": "object"},
                        "maxHops": max_hops,
                        "next": None,
                    }
                ],
                "outputs": {},
            },
        }
    )


def make_fake_adapter(write_status_each_hop):
    """Returns an adapter fn that writes handoff_status.json before completing."""

    def adapter_fn(invocation):
        write_status_each_hop(invocation.workspace_root)
        return AgentResult(status=AgentStatus.COMPLETED, output={}, termination_reason="success")

    return adapter_fn


def test_handoff_completes_on_success_path_before_max_hops(worktree, conn):
    hops = {"n": 0}

    def write_status(workspace_root):
        hops["n"] += 1
        completed = hops["n"] >= 2  # completes on the 2nd hop
        (workspace_root / f"hop{hops['n']}.txt").write_text("work\n")
        (workspace_root / "handoff_status.json").write_text(
            json.dumps({"handoff_complete": completed, "summary": f"hop {hops['n']}"})
        )

    adapter_registry = {"a": make_fake_adapter(write_status), "b": make_fake_adapter(write_status)}
    executor = make_handoff_node_executor(adapter_registry, worktree)

    workflow = make_handoff_workflow(max_hops=4)
    result = run_workflow_definition(
        conn, run_id="run-1", workflow=workflow, node_executors={"handoff": executor}
    )

    assert result["status"] == "SUCCEEDED"
    assert hops["n"] == 2
    log = run_git(["log", "--oneline"], cwd=worktree).stdout
    assert log.count("handoff: loop hop") == 2


def test_handoff_reaches_max_hops_moves_run_to_waiting_input(worktree, conn):
    hops = {"n": 0}

    def write_status(workspace_root):
        hops["n"] += 1
        (workspace_root / "handoff_status.json").write_text(
            json.dumps({"handoff_complete": False, "summary": f"hop {hops['n']}"})
        )

    adapter_registry = {"a": make_fake_adapter(write_status), "b": make_fake_adapter(write_status)}
    executor = make_handoff_node_executor(adapter_registry, worktree)

    workflow = make_handoff_workflow(max_hops=2)
    result = run_workflow_definition(
        conn, run_id="run-1", workflow=workflow, node_executors={"handoff": executor}
    )

    assert result["status"] == "WAITING_INPUT"
    assert result["hops_used"] == 2
    row = conn.execute("SELECT status FROM runs WHERE run_id = 'run-1'").fetchone()
    assert row["status"] == "WAITING_INPUT"


def test_handoff_alternates_between_the_two_adapters(worktree, conn):
    calls = []

    def make_adapter(name):
        def adapter_fn(invocation):
            calls.append(name)
            completed = len(calls) >= 3
            (invocation.workspace_root / "handoff_status.json").write_text(
                json.dumps({"handoff_complete": completed, "summary": name})
            )
            return AgentResult(status=AgentStatus.COMPLETED, output={}, termination_reason="success")
        return adapter_fn

    adapter_registry = {"a": make_adapter("a"), "b": make_adapter("b")}
    executor = make_handoff_node_executor(adapter_registry, worktree)

    workflow = make_handoff_workflow(max_hops=4)
    run_workflow_definition(conn, run_id="run-1", workflow=workflow, node_executors={"handoff": executor})

    assert calls == ["a", "b", "a"]


def test_handoff_missing_status_file_fails_run_cleanly_with_tool_error(worktree, conn):
    def adapter_fn(invocation):
        return AgentResult(status=AgentStatus.COMPLETED, output={}, termination_reason="success")

    adapter_registry = {"a": adapter_fn, "b": adapter_fn}
    executor = make_handoff_node_executor(adapter_registry, worktree)
    workflow = make_handoff_workflow(max_hops=2)

    # run_workflow_definition catches the raised HandoffError at the Run
    # level and returns a clean result - it does not propagate a raw
    # exception to the caller. The hop's own Step already succeeded (the
    # adapter completed); the missing-file check happens after, at the
    # handoff executor level, so the Run fails even though that one Step
    # did not.
    result = run_workflow_definition(conn, run_id="run-1", workflow=workflow, node_executors={"handoff": executor})

    assert result["status"] == "FAILED"
    row = conn.execute("SELECT status FROM runs WHERE run_id = 'run-1'").fetchone()
    assert row["status"] == "FAILED"
    step_row = conn.execute(
        "SELECT status FROM steps WHERE step_id = 'run-1:loop#1:hop1'"
    ).fetchone()
    assert step_row["status"] == "SUCCEEDED"


def test_handoff_status_file_violating_payloadschema_fails_run_with_invalid_input(worktree, conn):
    # A real, meaningful payloadSchema (not the loose {"type": "object"}
    # every other test in this file uses) - requires a "confidence" field
    # the agent never actually writes.
    strict_schema = {
        "type": "object",
        "required": ["handoff_complete", "summary", "confidence"],
        "properties": {"confidence": {"type": "number"}},
    }

    def adapter_fn(invocation):
        (invocation.workspace_root / "handoff_status.json").write_text(
            json.dumps({"handoff_complete": True, "summary": "done"})  # missing "confidence"
        )
        return AgentResult(status=AgentStatus.COMPLETED, output={}, termination_reason="success")

    adapter_registry = {"a": adapter_fn, "b": adapter_fn}
    executor = make_handoff_node_executor(adapter_registry, worktree)
    workflow = make_handoff_workflow(max_hops=2, payload_schema=strict_schema)

    result = run_workflow_definition(conn, run_id="run-1", workflow=workflow, node_executors={"handoff": executor})

    assert result["status"] == "FAILED"
    assert "payloadSchema" in result["error"]
    row = conn.execute("SELECT status FROM runs WHERE run_id = 'run-1'").fetchone()
    assert row["status"] == "FAILED"


def test_handoff_status_file_conforming_to_strict_payloadschema_succeeds(worktree, conn):
    strict_schema = {
        "type": "object",
        "required": ["handoff_complete", "summary", "confidence"],
        "properties": {"confidence": {"type": "number"}},
    }

    def adapter_fn(invocation):
        (invocation.workspace_root / "handoff_status.json").write_text(
            json.dumps({"handoff_complete": True, "summary": "done", "confidence": 0.9})
        )
        return AgentResult(status=AgentStatus.COMPLETED, output={}, termination_reason="success")

    adapter_registry = {"a": adapter_fn, "b": adapter_fn}
    executor = make_handoff_node_executor(adapter_registry, worktree)
    workflow = make_handoff_workflow(max_hops=2, payload_schema=strict_schema)

    result = run_workflow_definition(conn, run_id="run-1", workflow=workflow, node_executors={"handoff": executor})

    assert result["status"] == "SUCCEEDED"


def test_handoff_adapter_failure_fails_run_cleanly_with_tool_error(worktree, conn):
    def failing_adapter(invocation):
        return AgentResult(status=AgentStatus.FAILED, output={}, termination_reason="tool_error")

    adapter_registry = {"a": failing_adapter, "b": failing_adapter}
    executor = make_handoff_node_executor(adapter_registry, worktree)
    workflow = make_handoff_workflow(max_hops=2)

    result = run_workflow_definition(conn, run_id="run-1", workflow=workflow, node_executors={"handoff": executor})

    assert result["status"] == "FAILED"
    step_row = conn.execute(
        "SELECT status, failure_class FROM steps WHERE step_id = 'run-1:loop#1:hop1'"
    ).fetchone()
    assert step_row["status"] == "FAILED"
    assert step_row["failure_class"] == "TOOL_ERROR"
