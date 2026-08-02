import pytest

from awf.db.bootstrap import init_db
from awf.db.connection import get_connection
from awf.engine.run import create_run
from awf.workflow.definition import parse_workflow
from awf.workflow.engine import WorkflowEngineError, run_workflow_definition


def make_conn(tmp_path):
    db_path = tmp_path / "awf.db"
    init_db(db_path)
    conn = get_connection(db_path)
    create_run(conn, run_id="run-1", workflow_ref="demo@1.0.0")
    return conn


def make_workflow(max_repairs=3):
    return parse_workflow(
        {
            "apiVersion": "awf/v1",
            "kind": "Workflow",
            "metadata": {"name": "demo", "version": "1.0.0", "digest": "sha256:abc"},
            "spec": {
                "inputSchema": {},
                "outputSchema": {},
                "budgets": {"maxRepairIterations": max_repairs},
                "nodes": [
                    {"id": "produce", "type": "agent", "next": "check"},
                    {"id": "check", "type": "gate", "next": None, "onFail": "repair"},
                    {"id": "repair", "type": "agent", "next": "check"},
                ],
                "outputs": {},
            },
        }
    )


def test_straight_pass_no_repair_needed(tmp_path):
    conn = make_conn(tmp_path)
    workflow = make_workflow()
    calls = []

    def agent_executor(conn, run_id, step_id, node):
        calls.append(node["id"])
        return {"ok": True}

    def gate_executor(conn, run_id, step_id, node):
        return {"passed": True}

    result = run_workflow_definition(
        conn, run_id="run-1", workflow=workflow,
        node_executors={"agent": agent_executor, "gate": gate_executor},
    )

    assert result == {"status": "SUCCEEDED", "repairs_used": 0}
    assert calls == ["produce"]
    row = conn.execute("SELECT status FROM runs WHERE run_id = 'run-1'").fetchone()
    assert row["status"] == "SUCCEEDED"


def test_gate_fails_once_then_repair_succeeds(tmp_path):
    conn = make_conn(tmp_path)
    workflow = make_workflow()
    gate_calls = []

    def agent_executor(conn, run_id, step_id, node):
        return {"ok": True}

    def gate_executor(conn, run_id, step_id, node):
        gate_calls.append(node["id"])
        return {"passed": len(gate_calls) > 1}

    result = run_workflow_definition(
        conn, run_id="run-1", workflow=workflow,
        node_executors={"agent": agent_executor, "gate": gate_executor},
    )

    assert result == {"status": "SUCCEEDED", "repairs_used": 1}
    assert len(gate_calls) == 2


def test_budget_exhausted_marks_run_failed(tmp_path):
    conn = make_conn(tmp_path)
    workflow = make_workflow(max_repairs=1)

    def agent_executor(conn, run_id, step_id, node):
        return {"ok": True}

    def gate_executor(conn, run_id, step_id, node):
        return {"passed": False}

    result = run_workflow_definition(
        conn, run_id="run-1", workflow=workflow,
        node_executors={"agent": agent_executor, "gate": gate_executor},
    )

    assert result == {"status": "FAILED", "repairs_used": 1}
    row = conn.execute("SELECT status FROM runs WHERE run_id = 'run-1'").fetchone()
    assert row["status"] == "FAILED"


def test_non_executable_node_type_raises(tmp_path):
    conn = make_conn(tmp_path)
    workflow = parse_workflow(
        {
            "apiVersion": "awf/v1",
            "kind": "Workflow",
            "metadata": {"name": "demo", "version": "1.0.0", "digest": "sha256:abc"},
            "spec": {
                "inputSchema": {}, "outputSchema": {}, "budgets": {},
                "nodes": [{"id": "h", "type": "handoff", "maxHops": 2}],
                "outputs": {},
            },
        }
    )

    with pytest.raises(WorkflowEngineError):
        run_workflow_definition(conn, run_id="run-1", workflow=workflow, node_executors={})
