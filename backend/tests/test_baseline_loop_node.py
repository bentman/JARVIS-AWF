import json

import pytest

from awf.clock import utc_now_rfc3339
from awf.db.bootstrap import init_db
from awf.db.connection import get_connection
from awf.engine.run import create_run
from awf.workflow.loop_node import LoopNodeError, make_loop_node_executor


@pytest.fixture
def conn(tmp_path):
    db_path = tmp_path / "awf.db"
    init_db(db_path)
    connection = get_connection(db_path)
    create_run(connection, run_id="run-1", workflow_ref="demo@1.0.0")
    return connection


def _seed_child_run_with_output(conn, child_run_id: str, output: dict) -> None:
    create_run(conn, run_id=child_run_id, workflow_ref="child@1.0.0")
    now = utc_now_rfc3339()
    conn.execute(
        "INSERT INTO steps (step_id, run_id, node_id, attempt, status, input_json, output_json, started_at, ended_at) "
        "VALUES (?, ?, 'last', 1, 'SUCCEEDED', '{}', ?, ?, ?)",
        (f"{child_run_id}:last", child_run_id, json.dumps(output), now, now),
    )
    conn.commit()


def test_loop_stops_when_condition_field_goes_false(conn):
    iterations = []

    def run_child(conn, workflow_ref, input_data):
        i = len(iterations)
        iterations.append(input_data)
        child_run_id = f"child-{i}"
        _seed_child_run_with_output(conn, child_run_id, {"continue": i < 2, "count": i})
        return child_run_id, {"status": "SUCCEEDED"}

    executor = make_loop_node_executor(run_child)
    output = executor(
        conn, "run-1", "unused-step-id",
        {"id": "retry-loop", "type": "loop", "workflowRef": "child@1.0.0", "maxIterations": 10},
    )

    assert output["completed"] is True
    assert output["iterations_used"] == 3  # i=0 (True), i=1 (True), i=2 (False) -> stop
    assert len(iterations) == 3
    assert iterations[1] == {"continue": True, "count": 0}  # previous output feeds next input


def test_loop_reaching_max_iterations_while_still_true_waits_for_input(conn):
    def run_child(conn, workflow_ref, input_data):
        child_run_id = f"child-{workflow_ref}-{len(input_data)}-{id(input_data)}"
        _seed_child_run_with_output(conn, child_run_id, {"continue": True})
        return child_run_id, {"status": "SUCCEEDED"}

    executor = make_loop_node_executor(run_child)
    output = executor(
        conn, "run-1", "unused-step-id",
        {"id": "retry-loop", "type": "loop", "workflowRef": "child@1.0.0", "maxIterations": 3},
    )

    assert output["completed"] is False
    assert output["iterations_used"] == 3
    assert output["waiting_input"] is True
    run_row = conn.execute("SELECT status FROM runs WHERE run_id = 'run-1'").fetchone()
    assert run_row["status"] == "WAITING_INPUT"


def test_loop_raises_when_a_child_iteration_fails(conn):
    def run_child(conn, workflow_ref, input_data):
        return "child-x", {"status": "FAILED"}

    executor = make_loop_node_executor(run_child)

    with pytest.raises(LoopNodeError):
        executor(
            conn, "run-1", "unused-step-id",
            {"id": "retry-loop", "type": "loop", "workflowRef": "child@1.0.0", "maxIterations": 3},
        )
