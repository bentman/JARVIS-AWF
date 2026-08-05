import pytest

from awf.db.bootstrap import init_db
from awf.db.connection import get_connection
from awf.engine.run import create_run, create_step
from awf.workflow.subworkflow import SubworkflowError, make_subworkflow_node_executor


@pytest.fixture
def conn(tmp_path):
    db_path = tmp_path / "awf.db"
    init_db(db_path)
    connection = get_connection(db_path)
    create_run(connection, run_id="run-1", workflow_ref="demo@1.0.0")
    create_step(connection, step_id="step-1", run_id="run-1", node_id="run-child")
    return connection


def test_subworkflow_runs_the_child_and_completes_on_success(conn):
    calls = []

    def run_child(conn, workflow_ref, input_data):
        calls.append((workflow_ref, input_data))
        return "child-run-1", {"status": "SUCCEEDED"}

    executor = make_subworkflow_node_executor(run_child)
    output = executor(
        conn, "run-1", "step-1",
        {"id": "run-child", "type": "subworkflow", "workflowRef": "child@1.0.0", "input": {"x": 1}},
    )

    assert output["child_run_id"] == "child-run-1"
    assert output["child_status"] == "SUCCEEDED"
    assert calls == [("child@1.0.0", {"x": 1})]
    row = conn.execute("SELECT status FROM steps WHERE step_id = 'step-1'").fetchone()
    assert row["status"] == "SUCCEEDED"


def test_subworkflow_raises_when_child_does_not_succeed(conn):
    def run_child(conn, workflow_ref, input_data):
        return "child-run-1", {"status": "FAILED", "error": "boom"}

    executor = make_subworkflow_node_executor(run_child)

    with pytest.raises(SubworkflowError):
        executor(conn, "run-1", "step-1", {"id": "run-child", "type": "subworkflow", "workflowRef": "child@1.0.0"})

    row = conn.execute("SELECT status, failure_class FROM steps WHERE step_id = 'step-1'").fetchone()
    assert row["status"] == "FAILED"
    assert row["failure_class"] == "TOOL_ERROR"
