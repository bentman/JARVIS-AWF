import pytest

from awf.db.bootstrap import init_db
from awf.db.connection import get_connection
from awf.engine.executor import StepFailure
from awf.engine.run import create_run, create_step
from awf.memory.sessions import append_entry, start_session
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


def test_assistant_reply_activity_uses_model_gateway(conn, repo_root, monkeypatch):
    create_step(conn, step_id="step-1", run_id="run-1", node_id="reply")
    captured = {}

    def fake_complete(profile, messages, **kwargs):
        captured["profile"] = profile.ref
        captured["messages"] = messages
        captured["kwargs"] = kwargs
        return "Model response."

    monkeypatch.setattr("awf.workflow.activities.complete", fake_complete)
    executor = make_activity_node_executor(repo_root=repo_root)

    output = executor(
        conn,
        "run-1",
        "step-1",
        {"id": "reply", "type": "activity", "function": "assistant_reply", "args": {"objective": "triage runs"}},
    )

    assert output["response_text"] == "Model response."
    assert captured["profile"] == "resident-mind@1.0.0"
    assert captured["kwargs"]["run_id"] == "run-1"
    row = conn.execute("SELECT status, output_json FROM steps WHERE step_id = 'step-1'").fetchone()
    assert row["status"] == "SUCCEEDED"
    assert "Model response" in row["output_json"]


def test_assistant_reply_includes_recent_session_and_memory(conn, repo_root, monkeypatch):
    create_step(conn, step_id="step-1", run_id="run-1", node_id="reply")
    session = start_session(conn, title="chat")
    append_entry(
        conn,
        session_id=session["session_id"],
        role="operator",
        content={"text": "my name is Casey"},
        summary="my name is Casey",
    )
    append_entry(conn, session_id=session["session_id"], role="assistant", content={"text": "Noted."}, summary="Noted.")
    captured = {}

    def fake_complete(profile, messages, **kwargs):
        captured["messages"] = messages
        return "Your name is Casey."

    from awf.cognition.envelope import PromptSegment

    monkeypatch.setattr("awf.workflow.activities.complete", fake_complete)
    monkeypatch.setattr(
        "awf.workflow.activities.retrieve_memory_context",
        lambda repo_root, conn, *, query, profile_ref: (
            PromptSegment("memory", "context", False, "operator prefers brief answers"),
        ),
    )
    executor = make_activity_node_executor(repo_root=repo_root)

    output = executor(
        conn,
        "run-1",
        "step-1",
        {
            "id": "reply",
            "type": "activity",
            "function": "assistant_reply",
            "args": {"objective": "what is my name?", "sessionId": session["session_id"]},
        },
    )

    assert output["response_text"] == "Your name is Casey."
    user_content = captured["messages"][-1]["content"]
    assert "my name is Casey" in user_content
    assert "Noted." in user_content
    assert "operator prefers brief answers" in user_content
    assert user_content.rstrip().endswith("[user/input, untrusted]\nwhat is my name?")


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


def test_activity_node_with_repo_root_authorizes_through_the_published_record(conn, repo_root):
    create_step(conn, step_id="step-1", run_id="run-1", node_id="probe")
    executor = make_activity_node_executor(repo_root=repo_root)

    executor(conn, "run-1", "step-1", {"id": "probe", "type": "activity", "function": "hardware_probe"})

    decision_event = conn.execute("SELECT * FROM events WHERE actor = 'awf' AND new_status = 'allow'").fetchone()
    assert decision_event is not None
    assert '"capability_ref": "hardware_probe@1.0.0"' in decision_event["payload_json"]
    assert '"risk_class": "R0"' in decision_event["payload_json"]


def test_activity_node_denies_when_published_record_is_r3(conn, tmp_path, monkeypatch):
    override_dir = tmp_path / "data" / "registry" / "capabilities" / "hardware_probe"
    override_dir.mkdir(parents=True)
    (override_dir / "1.0.0.yaml").write_text(
        "identity: {type: activity, provider: awf, name: hardware_probe, version: 1.0.0}\n"
        'schema: {input: "", output: ""}\n'
        "effects: {operation: read, reversible: true, idempotent: true, external_side_effect: false}\n"
        "risk_class: R3\n"
        "approval: per-invocation\n"
    )

    calls = []
    monkeypatch.setattr(
        "awf.workflow.activities.run_hardware_profiler",
        lambda conn: calls.append(1) or "should-not-be-called",
    )

    create_step(conn, step_id="step-1", run_id="run-1", node_id="probe")
    executor = make_activity_node_executor(repo_root=tmp_path)

    with pytest.raises(StepFailure):
        executor(conn, "run-1", "step-1", {"id": "probe", "type": "activity", "function": "hardware_probe"})

    assert calls == []  # the Guard denial short-circuited before the activity ran

    row = conn.execute("SELECT status, failure_class FROM steps WHERE step_id = 'step-1'").fetchone()
    assert row["status"] == "FAILED"
    assert row["failure_class"] == "POLICY_DENIED"
