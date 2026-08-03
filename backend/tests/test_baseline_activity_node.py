import pytest

from awf.db.bootstrap import init_db
from awf.db.connection import get_connection
from awf.engine.run import create_run, create_step
from awf.workflow.activities import UnknownActivityError
from awf.workflow.engine import make_activity_node_executor


@pytest.fixture
def conn(tmp_path):
    db_path = tmp_path / "awf.db"
    init_db(db_path)
    connection = get_connection(db_path)
    create_run(connection, run_id="run-1", workflow_ref="demo@1.0.0")
    return connection


def test_hardware_probe_activity_runs_for_real_and_persists_the_step(conn):
    create_step(conn, step_id="step-1", run_id="run-1", node_id="probe")
    executor = make_activity_node_executor()

    output = executor(conn, "run-1", "step-1", {"id": "probe", "type": "activity", "function": "hardware_probe"})

    assert output["profile_id"]  # a real canonical profile id, e.g. linux-x64-cpu
    row = conn.execute("SELECT status, output_json FROM steps WHERE step_id = 'step-1'").fetchone()
    assert row["status"] == "SUCCEEDED"
    assert output["profile_id"] in row["output_json"]

    resolved_event = conn.execute(
        "SELECT * FROM events WHERE actor = 'hardware_profiler' AND reason_code = 'hardware_profile_resolved'"
    ).fetchone()
    assert resolved_event is not None


def test_unknown_activity_name_raises_with_invalid_input_failure_class(conn):
    create_step(conn, step_id="step-1", run_id="run-1", node_id="bad")
    executor = make_activity_node_executor()

    with pytest.raises(UnknownActivityError):
        executor(conn, "run-1", "step-1", {"id": "bad", "type": "activity", "function": "not_registered"})

    row = conn.execute("SELECT status, failure_class FROM steps WHERE step_id = 'step-1'").fetchone()
    assert row["status"] == "FAILED"
    assert row["failure_class"] == "INVALID_INPUT"


def test_activity_replay_after_succeeded_returns_cached_output_without_reprobing(conn, monkeypatch):
    create_step(conn, step_id="step-1", run_id="run-1", node_id="probe")
    executor = make_activity_node_executor()

    first = executor(conn, "run-1", "step-1", {"id": "probe", "type": "activity", "function": "hardware_probe"})

    calls = []
    monkeypatch.setattr(
        "awf.workflow.activities.run_hardware_profiler",
        lambda conn: calls.append(1) or "should-not-be-called",
    )
    second = executor(conn, "run-1", "step-1", {"id": "probe", "type": "activity", "function": "hardware_probe"})

    assert second == first
    assert calls == []  # run_step's SUCCEEDED cache short-circuited before the activity re-ran
