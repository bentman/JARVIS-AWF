"""Integration tests for intent routing operations."""

import pytest
from backend.tests.support import make_git_awf_repo, publish_workflow, single_gate_workflow

from awf.cognition.router import INTENT_ANSWER, INTENT_DRAFT_WORKFLOW, INTENT_PROPOSE_MEMORY, INTENT_RUN_WORKFLOW
from awf.memory.sessions import show_session, start_session
from awf.ops.intent import op_intent_classify, op_intent_dispatch
from awf.ops.shared import CoreOpError


def test_op_intent_classify_deterministic(tmp_path):
    repo_root, conn = make_git_awf_repo(tmp_path)

    res1 = op_intent_classify(repo_root, conn, text="run demo")
    assert res1["intent"] == INTENT_RUN_WORKFLOW
    assert res1["target_ref"] == "demo"

    res2 = op_intent_classify(repo_root, conn, text="draft workflow backup database")
    assert res2["intent"] == INTENT_DRAFT_WORKFLOW
    assert res2["payload"]["objective"] == "backup database"

    res3 = op_intent_classify(repo_root, conn, text="remember that staging IP is 192.168.1.1")
    assert res3["intent"] == INTENT_PROPOSE_MEMORY
    assert res3["payload"]["fact"] == "staging IP is 192.168.1.1"


def test_op_intent_dispatch_runs_workflow(tmp_path):
    repo_root, conn = make_git_awf_repo(tmp_path)
    publish_workflow(repo_root, single_gate_workflow("demo", "1.0.0", "sha256:v1"))

    dispatched = op_intent_dispatch(repo_root, conn, text="run demo@1.0.0 with objective smoke test")

    assert dispatched["intent"] == INTENT_RUN_WORKFLOW
    assert dispatched["workflow_ref"] == "demo@1.0.0"
    assert dispatched["run_id"] is not None
    assert dispatched["run_result"]["status"] == "SUCCEEDED"
    assert "Started workflow demo@1.0.0" in dispatched["response_text"]


def test_op_intent_dispatch_drafts_workflow(tmp_path, monkeypatch):
    repo_root, conn = make_git_awf_repo(tmp_path)

    monkeypatch.setattr(
        "awf.ops.intent.op_workflow_author_draft",
        lambda repo_root, conn, *, objective, name=None: {
            "proposal_id": "prop-123",
            "status": "draft",
            "objective": objective,
        },
    )

    dispatched = op_intent_dispatch(repo_root, conn, text="draft workflow that monitors cpu usage")

    assert dispatched["intent"] == INTENT_DRAFT_WORKFLOW
    assert dispatched["proposal_id"] == "prop-123"
    assert "Created workflow draft proposal prop-123" in dispatched["response_text"]


def test_op_intent_dispatch_proposes_memory(tmp_path):
    repo_root, conn = make_git_awf_repo(tmp_path)
    session = start_session(conn, title="voice-session")
    sid = session["session_id"]

    dispatched = op_intent_dispatch(
        repo_root,
        conn,
        text="remember that operator timezone is UTC",
        voice_session_id=sid,
    )

    assert dispatched["intent"] == INTENT_PROPOSE_MEMORY
    assert dispatched["fact"] == "operator timezone is UTC"
    assert "Saved fact to memory: operator timezone is UTC" in dispatched["response_text"]

    stored = show_session(conn, session_id=sid)
    assert len(stored["entries"]) == 1
    assert stored["entries"][0]["summary"] == "operator timezone is UTC"


def test_op_intent_dispatch_answers_conversational_query(tmp_path, monkeypatch):
    repo_root, conn = make_git_awf_repo(tmp_path)

    def fake_run_start(repo_root, conn, *, workflow_ref, input_data, async_execution=False):
        return {
            "run_id": "run-assistant-1",
            "status": "SUCCEEDED",
            "outcome": {"response_text": "I am the resident mind. How can I help?"},
        }

    monkeypatch.setattr("awf.ops.intent.op_run_start", fake_run_start)

    dispatched = op_intent_dispatch(repo_root, conn, text="hello, who are you?")

    assert dispatched["intent"] == INTENT_ANSWER
    assert dispatched["workflow_ref"] == "assistant-default@1.0.0"
    assert dispatched["response_text"] == "I am the resident mind. How can I help?"


def test_op_intent_dispatch_missing_workflow_preserves_session(tmp_path):
    repo_root, conn = make_git_awf_repo(tmp_path)
    session = start_session(conn, title="voice-session-error")
    sid = session["session_id"]

    with pytest.raises(CoreOpError, match="unknown workflow"):
        op_intent_dispatch(
            repo_root,
            conn,
            text="run non_existent_workflow_xyz",
            voice_session_id=sid,
        )

    stored = show_session(conn, session_id=sid)
    assert stored["session_id"] == sid
    assert stored["status"] == "active"


def test_op_intent_dispatch_failed_workflow_returns_structured_result(tmp_path):
    repo_root, conn = make_git_awf_repo(tmp_path)
    wf = single_gate_workflow("failing-wf", "1.0.0", "sha256:fail")
    wf["spec"]["nodes"][0]["checkCommand"] = "false"
    publish_workflow(repo_root, wf)

    dispatched = op_intent_dispatch(repo_root, conn, text="run failing-wf@1.0.0")
    assert dispatched["intent"] == INTENT_RUN_WORKFLOW
    assert dispatched["run_result"]["status"] == "FAILED"
    assert dispatched["run_id"] is not None
