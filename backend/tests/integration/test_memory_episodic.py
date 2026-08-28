from backend.tests.support import make_awf_repo, seed_run_step

from awf.events.writer import write_event
from awf.ops.memory import op_episodic_search, op_episodic_timeline


def test_episodic_search_and_timeline_read_events(tmp_path):
    _repo_root, conn = make_awf_repo(tmp_path)
    seed_run_step(conn, run_id="run-1", step_id="s1", node_id="gate")
    write_event(
        conn,
        run_id="run-1",
        step_id="s1",
        new_status="SUCCEEDED",
        actor="engine",
        reason_code="targeted-check-passed",
        payload_json='{"detail": "targeted"}',
    )

    results = op_episodic_search(conn, query="targeted")
    timeline = op_episodic_timeline(conn, run_id="run-1")

    assert results[0]["reason_code"] == "targeted-check-passed"
    assert timeline["run"]["run_id"] == "run-1"
    assert any(event["reason_code"] == "targeted-check-passed" for event in timeline["events"])
