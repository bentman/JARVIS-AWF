import json

import pytest
from backend.tests.support import make_git_awf_repo, publish_workflow

from awf.ops.memory import op_session_show
from awf.ops.shared import CoreOpError
from awf.ops.voice import op_voice_session_event, op_voice_session_start, op_voice_submit_text
from awf.server.stdio import dispatch


def _publish_persona_and_voice(repo_root):
    persona = repo_root / "config" / "app_registry" / "personas" / "narrator" / "1.0.0.yaml"
    persona.parent.mkdir(parents=True, exist_ok=True)
    persona.write_text(
        "name: narrator\n"
        "version: 1.0.0\n"
        "display_name: Narrator\n"
        "description: Default voice\n"
        "locale: en\n"
        "system: Speak plainly.\n"
        "style: {max_words_default: 120, structure: Direct., do: [Be clear.], avoid: [Guessing.]}\n"
        "traits: {warmth: medium, assertiveness: medium, detail: medium, humor: none}\n"
        "examples: [{user: hello, assistant: hello}]\n"
        "generation: {temperature: 0.5, max_tokens: 120}\n"
    )
    voice = repo_root / "config" / "app_registry" / "voice-profiles" / "narrator" / "1.0.0.yaml"
    voice.parent.mkdir(parents=True, exist_ok=True)
    voice.write_text(
        "name: narrator\n"
        "version: 1.0.0\n"
        "persona_ref: narrator@1.0.0\n"
        "tts:\n"
        "  candidates:\n"
        "    - {engine: kokoro, model: kokoro-v1.0, voice_id: bf_isabella, speed: 1.0, style: {}, priority: 1, enabled: true}\n"
        "  fallback: {mode: none, allow_quality_degrade: false}\n"
        "privacy: {local_only: true}\n"
        "limits: {max_seconds_per_utterance: 30}\n"
    )


def _publish_voice_workflow(repo_root):
    publish_workflow(
        repo_root,
        {
            "apiVersion": "awf/v1",
            "kind": "Workflow",
            "metadata": {"name": "voice-demo", "version": "1.0.0", "digest": "sha256:demo"},
            "spec": {
                "inputSchema": {"type": "object", "required": ["objective"]},
                "outputSchema": {},
                "budgets": {},
                "nodes": [{"id": "check", "type": "gate", "checkCommand": "true", "next": None}],
                "outputs": {},
            },
        },
    )


def test_voice_session_accepts_normal_turn_sequence_and_records_events(tmp_path):
    _repo_root, conn = make_git_awf_repo(tmp_path)

    started = op_voice_session_start(conn, title="demo voice")
    voice_session_id = started["voice_session_id"]
    assert started["state"] == "idle"

    assert (
        op_voice_session_event(conn, voice_session_id=voice_session_id, frame_type="vad.speech_started")["state"]
        == "listening"
    )
    assert (
        op_voice_session_event(conn, voice_session_id=voice_session_id, frame_type="vad.speech_stopped")["state"]
        == "transcribing"
    )
    assert (
        op_voice_session_event(
            conn,
            voice_session_id=voice_session_id,
            frame_type="stt.final",
            payload={"text": "run the demo"},
            turn_id="turn-1",
        )["state"]
        == "submitting"
    )

    rows = conn.execute(
        "SELECT payload_json FROM events WHERE reason_code = 'voice_session_frame' ORDER BY occurred_at"
    ).fetchall()
    assert len(rows) == 4
    assert json.loads(rows[-1]["payload_json"])["frame_type"] == "stt.final"
    assert json.loads(rows[-1]["payload_json"])["payload"] == {"text": "run the demo"}


def test_voice_session_rejects_impossible_transition_without_success_event(tmp_path):
    _repo_root, conn = make_git_awf_repo(tmp_path)
    started = op_voice_session_start(conn)

    with pytest.raises(CoreOpError, match="cannot accept"):
        op_voice_session_event(conn, voice_session_id=started["voice_session_id"], frame_type="stt.final")

    state_rows = conn.execute(
        "SELECT COUNT(*) AS n FROM active_session_entries WHERE session_id = ? AND summary LIKE '%stt.final%'",
        (started["voice_session_id"],),
    ).fetchone()
    assert state_rows["n"] == 0


def test_voice_interruption_during_speaking_returns_to_listening(tmp_path):
    _repo_root, conn = make_git_awf_repo(tmp_path)
    started = op_voice_session_start(conn)
    sid = started["voice_session_id"]

    for frame_type in ("vad.speech_started", "vad.speech_stopped", "stt.final", "core.submitted", "core.output_text"):
        op_voice_session_event(conn, voice_session_id=sid, frame_type=frame_type)

    interrupted = op_voice_session_event(conn, voice_session_id=sid, frame_type="interruption", turn_id="turn-1")

    assert interrupted["state"] == "listening"
    session = op_session_show(conn, session_id=sid)
    assert any(entry["content"].get("kind") == "voice_interruption" for entry in session["entries"])


def test_voice_submit_text_starts_default_workflow_and_persists_turn(tmp_path):
    repo_root, conn = make_git_awf_repo(tmp_path)
    _publish_persona_and_voice(repo_root)
    _publish_voice_workflow(repo_root)
    sid = op_voice_session_start(conn)["voice_session_id"]
    for frame_type in ("vad.speech_started", "vad.speech_stopped", "stt.final"):
        op_voice_session_event(conn, voice_session_id=sid, frame_type=frame_type, turn_id="turn-1")

    result = op_voice_submit_text(
        repo_root,
        conn,
        voice_session_id=sid,
        text="check the repo",
        workflow_ref="voice-demo@1.0.0",
        turn_id="turn-1",
    )

    assert result["state"] == "speaking"
    assert result["run"]["status"] == "SUCCEEDED"
    assert result["voice"]["voice_profile_ref"] == "narrator@1.0.0"
    session = op_session_show(conn, session_id=sid)
    kinds = [entry["content"].get("kind") for entry in session["entries"]]
    assert "voice_utterance" in kinds
    assert "voice_response" in kinds


def test_voice_submit_text_defaults_to_assistant_workflow(tmp_path, monkeypatch):
    repo_root, conn = make_git_awf_repo(tmp_path)
    _publish_persona_and_voice(repo_root)
    sid = op_voice_session_start(conn)["voice_session_id"]
    captured = {}

    def fake_run_start(repo_root, conn, *, workflow_ref, input_data):
        captured["workflow_ref"] = workflow_ref
        captured["input_data"] = input_data
        return {
            "run_id": "run-default",
            "status": "SUCCEEDED",
            "outputs": {"response_text": "default response"},
        }

    monkeypatch.setattr("awf.ops.voice.op_run_start", fake_run_start)

    result = op_voice_submit_text(repo_root, conn, voice_session_id=sid, text="hello", workflow_ref=None)

    assert captured["workflow_ref"] == "assistant-default@1.0.0"
    assert captured["input_data"]["objective"] == "hello"
    assert result["response_text"] == "default response"


def test_voice_json_rpc_methods_dispatch(tmp_path):
    repo_root, conn = make_git_awf_repo(tmp_path)
    started = dispatch(repo_root, conn, "awf/voice.sessionStart", {"title": "voice"})

    event = dispatch(
        repo_root,
        conn,
        "awf/voice.event",
        {"voiceSessionId": started["voice_session_id"], "frameType": "vad.speech_started"},
    )
    closed = dispatch(
        repo_root,
        conn,
        "awf/voice.sessionClose",
        {"voiceSessionId": started["voice_session_id"], "reason": "done"},
    )

    assert event["state"] == "listening"
    assert closed["state"] == "closed"
