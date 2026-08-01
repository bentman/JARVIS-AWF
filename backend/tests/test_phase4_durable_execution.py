import subprocess
import sys
from pathlib import Path

from awf.db.bootstrap import init_db
from awf.db.connection import get_connection
from awf.engine.executor import run_step, run_workflow
from awf.engine.recovery import scan_incomplete_runs
from awf.engine.run import create_run, create_step

CRASH_RUNNER = Path(__file__).resolve().parent / "fixtures" / "engine" / "crash_runner.py"


def make_db(tmp_path):
    db_path = tmp_path / "awf.db"
    init_db(db_path)
    return get_connection(db_path)


def test_run_workflow_executes_steps_in_order_and_marks_run_succeeded(tmp_path):
    conn = make_db(tmp_path)
    create_run(conn, run_id="run-1", workflow_ref="noop-2step@1.0.0")
    create_step(conn, step_id="s1", run_id="run-1", node_id="n1")
    create_step(conn, step_id="s2", run_id="run-1", node_id="n2")

    calls = []
    steps = [
        ("s1", lambda payload: (calls.append("s1"), {"ok": True})[1], {}),
        ("s2", lambda payload: (calls.append("s2"), {"ok": True})[1], {}),
    ]
    run_workflow(conn, run_id="run-1", steps=steps)

    assert calls == ["s1", "s2"]
    run_row = conn.execute("SELECT status FROM runs WHERE run_id = 'run-1'").fetchone()
    assert run_row["status"] == "SUCCEEDED"


def test_run_step_skips_already_succeeded_step(tmp_path):
    conn = make_db(tmp_path)
    create_run(conn, run_id="run-1", workflow_ref="noop-2step@1.0.0")
    create_step(conn, step_id="s1", run_id="run-1", node_id="n1")

    calls = []
    fn = lambda payload: (calls.append("ran"), {"n": len(calls)})[1]

    first = run_step(conn, step_id="s1", run_id="run-1", fn=fn, input_payload={})
    second = run_step(conn, step_id="s1", run_id="run-1", fn=fn, input_payload={})

    assert calls == ["ran"]  # fn only invoked once
    assert first == second == {"n": 1}


def test_scan_incomplete_runs_excludes_terminal_statuses(tmp_path):
    conn = make_db(tmp_path)
    create_run(conn, run_id="run-running", workflow_ref="wf@1.0.0")
    create_run(conn, run_id="run-done", workflow_ref="wf@1.0.0")
    conn.execute("UPDATE runs SET status = 'RUNNING' WHERE run_id = 'run-running'")
    conn.execute("UPDATE runs SET status = 'SUCCEEDED' WHERE run_id = 'run-done'")
    conn.commit()

    assert scan_incomplete_runs(conn) == ["run-running"]


def test_mid_run_crash_and_resume_no_duplicate_side_effects(tmp_path):
    db_path = tmp_path / "awf.db"
    counter_path = tmp_path / "counter.txt"

    start = subprocess.run(
        [sys.executable, str(CRASH_RUNNER), "start", str(db_path), str(counter_path)],
        capture_output=True,
        text=True,
    )
    assert start.returncode == 137  # process was genuinely killed, not returned normally

    conn = get_connection(db_path)
    run_row = conn.execute("SELECT status FROM runs WHERE run_id = 'run-crash-1'").fetchone()
    step_status = {
        row["step_id"]: row["status"]
        for row in conn.execute("SELECT step_id, status FROM steps").fetchall()
    }
    conn.close()

    assert run_row["status"] == "RUNNING"
    assert step_status == {"step-1": "SUCCEEDED", "step-2": "RUNNING"}
    assert counter_path.read_text() == "1"

    resume = subprocess.run(
        [sys.executable, str(CRASH_RUNNER), "resume", str(db_path), str(counter_path)],
        capture_output=True,
        text=True,
    )
    assert resume.returncode == 0, resume.stderr
    assert "RESUME_OK" in resume.stdout

    conn = get_connection(db_path)
    run_row = conn.execute("SELECT status FROM runs WHERE run_id = 'run-crash-1'").fetchone()
    step_status = {
        row["step_id"]: row["status"]
        for row in conn.execute("SELECT step_id, status FROM steps").fetchall()
    }
    conn.close()

    assert run_row["status"] == "SUCCEEDED"
    assert step_status == {"step-1": "SUCCEEDED", "step-2": "SUCCEEDED"}
    # step-1's side effect (the counter bump) must not re-run on resume
    assert counter_path.read_text() == "1"
