import pytest
from backend.tests.support import make_awf_repo, seed_run_step

from awf.events.writer import write_event
from awf.ops.memory import (
    op_episodic_search,
    op_episodic_timeline,
    op_session_append,
    op_session_show,
    op_session_start,
    op_session_summarize,
)
from awf.ops.shared import CoreOpError


def test_active_session_lifecycle(tmp_path):
    _repo_root, conn = make_awf_repo(tmp_path)

    session = op_session_start(conn, title="demo")
    entry = op_session_append(
        conn,
        session_id=session["session_id"],
        role="operator",
        content={"text": "remember targeted tests"},
        summary="targeted tests",
    )
    shown = op_session_show(conn, session_id=session["session_id"])
    summarized = op_session_summarize(conn, session_id=session["session_id"], summary="done")

    assert entry["entries"][0]["role"] == "operator"
    assert shown["entries"][0]["content"] == {"text": "remember targeted tests"}
    assert summarized["status"] == "summarized"
    assert summarized["summary"] == "done"

    reloaded = op_session_show(conn, session_id=session["session_id"])
    assert reloaded["summary"] == "done"


def test_session_ttl_and_expiration(tmp_path):
    _repo_root, conn = make_awf_repo(tmp_path)

    session_with_ttl = op_session_start(conn, title="with_ttl", ttl_hours=24)
    assert session_with_ttl["expires_at"] is not None
    assert session_with_ttl["status"] == "active"

    expired_session = op_session_start(conn, title="expired", expires_at="2020-01-01T00:00:00Z")

    shown = op_session_show(conn, session_id=expired_session["session_id"])
    assert shown["status"] == "expired"

    with pytest.raises(CoreOpError, match="is expired"):
        op_session_append(
            conn,
            session_id=expired_session["session_id"],
            role="operator",
            content={"text": "should fail"},
        )


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
