import pytest

from awf.db.bootstrap import init_db
from awf.db.connection import get_connection
from awf.engine.run import create_run, create_step
from awf.workflow.map_node import MapNodeError, make_map_node_executor


@pytest.fixture
def conn(tmp_path):
    db_path = tmp_path / "awf.db"
    init_db(db_path)
    connection = get_connection(db_path)
    create_run(connection, run_id="run-1", workflow_ref="demo@1.0.0")
    create_step(connection, step_id="step-1", run_id="run-1", node_id="fan-out")
    return connection


def test_map_runs_one_child_per_item_in_order(conn):
    seen = []

    def run_child(conn, workflow_ref, input_data):
        seen.append(input_data)
        return f"child-{input_data['index']}", {"status": "SUCCEEDED"}

    executor = make_map_node_executor(run_child)
    output = executor(
        conn, "run-1", "step-1",
        {
            "id": "fan-out", "type": "map", "workflowRef": "child@1.0.0",
            "items": ["a", "b", "c"], "maxItems": 5, "maxConcurrency": 2,
        },
    )

    assert output["item_count"] == 3
    assert output["child_run_ids"] == ["child-0", "child-1", "child-2"]
    assert seen == [{"item": "a", "index": 0}, {"item": "b", "index": 1}, {"item": "c", "index": 2}]


def test_map_rejects_more_items_than_max_items(conn):
    def run_child(conn, workflow_ref, input_data):
        return "child-x", {"status": "SUCCEEDED"}

    executor = make_map_node_executor(run_child)

    with pytest.raises(MapNodeError):
        executor(
            conn, "run-1", "step-1",
            {
                "id": "fan-out", "type": "map", "workflowRef": "child@1.0.0",
                "items": ["a", "b", "c"], "maxItems": 2, "maxConcurrency": 2,
            },
        )


def test_map_raises_when_any_item_fails(conn):
    def run_child(conn, workflow_ref, input_data):
        if input_data["index"] == 1:
            return "child-1", {"status": "FAILED"}
        return f"child-{input_data['index']}", {"status": "SUCCEEDED"}

    executor = make_map_node_executor(run_child)

    with pytest.raises(MapNodeError):
        executor(
            conn, "run-1", "step-1",
            {
                "id": "fan-out", "type": "map", "workflowRef": "child@1.0.0",
                "items": ["a", "b"], "maxItems": 5, "maxConcurrency": 2,
            },
        )

    row = conn.execute("SELECT status FROM steps WHERE step_id = 'step-1'").fetchone()
    assert row["status"] == "FAILED"
