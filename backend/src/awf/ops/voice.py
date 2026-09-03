"""voice operation implementations."""

import sqlite3
from pathlib import Path

from awf.ops.run import DEFAULT_ASSISTANT_WORKFLOW_REF, op_run_start
from awf.ops.shared import CoreOpError
from awf.registry.resolve import resolve_registry_object
from awf.registry.voice_profile import DEFAULT_VOICE_PROFILE_REF, load_voice_profile
from awf.speech.session import (
    VoiceFrame,
    VoiceSessionError,
    accept_frame,
    append_assistant_response,
    append_operator_utterance,
    current_voice_session,
    start_voice_session,
)


def _resolve_voice_profile(
    repo_root: Path, voice_profile_ref: str | None = None, conn: sqlite3.Connection | None = None
) -> dict:
    ref = voice_profile_ref or DEFAULT_VOICE_PROFILE_REF
    name, sep, version = ref.partition("@")
    if not sep or not name or not version:
        raise CoreOpError(f"voice profile ref must be '<name>@<version>', got {ref!r}")
    path, _source = resolve_registry_object(repo_root, "voice-profiles", name, version, conn=conn)
    profile = load_voice_profile(repo_root, path, conn=conn)
    candidates = profile.enabled_candidates_by_priority()
    if not candidates:
        raise CoreOpError(f"voice profile '{profile.ref}' has no enabled TTS candidates")
    candidate = candidates[0]
    return {
        "voice_profile_ref": profile.ref,
        "voice_id": candidate.voice_id,
        "engine": candidate.engine,
        "model": candidate.model,
        "speed": candidate.speed,
        "privacy": {"local_only": profile.privacy.local_only},
        "limits": {"max_seconds_per_utterance": profile.limits.max_seconds_per_utterance},
    }


def _voice_response_text(workflow_ref: str, run_result: dict) -> str:
    outputs = run_result.get("outputs")
    if isinstance(outputs, dict) and isinstance(outputs.get("response_text"), str):
        return outputs["response_text"]
    return f"Workflow {workflow_ref} finished with status {run_result.get('status')} (run {run_result.get('run_id')})."


def op_voice_session_start(conn: sqlite3.Connection, *, title: str | None = None, wake_enabled: bool = False) -> dict:
    session = start_voice_session(conn, title=title, wake_enabled=wake_enabled)
    return {
        "voice_session_id": session.voice_session_id,
        "memory_session_id": session.memory_session_id,
        "state": session.state,
    }


def op_voice_session_event(
    conn: sqlite3.Connection,
    *,
    voice_session_id: str,
    frame_type: str,
    payload: dict | None = None,
    turn_id: str | None = None,
) -> dict:
    try:
        session = accept_frame(
            conn,
            voice_session_id=voice_session_id,
            frame=VoiceFrame(frame_type, payload or {}, turn_id=turn_id),
        )
    except VoiceSessionError as exc:
        raise CoreOpError(str(exc)) from exc
    return {
        "voice_session_id": session.voice_session_id,
        "memory_session_id": session.memory_session_id,
        "state": session.state,
    }


def op_voice_session_close(conn: sqlite3.Connection, *, voice_session_id: str, reason: str | None = None) -> dict:
    return op_voice_session_event(
        conn,
        voice_session_id=voice_session_id,
        frame_type="session.closed",
        payload={"reason": reason} if reason else {},
    )


def op_voice_submit_text(
    repo_root: Path,
    conn: sqlite3.Connection,
    *,
    voice_session_id: str,
    text: str,
    workflow_ref: str | None,
    voice_profile_ref: str | None = None,
    turn_id: str | None = None,
) -> dict:
    workflow_ref = workflow_ref or DEFAULT_ASSISTANT_WORKFLOW_REF
    if not text.strip():
        raise CoreOpError("voice.submitText requires non-empty text")

    voice_profile = _resolve_voice_profile(repo_root, voice_profile_ref, conn=conn)
    session = current_voice_session(conn, voice_session_id=voice_session_id)
    if session.state in {"idle", "armed"}:
        op_voice_session_event(
            conn,
            voice_session_id=voice_session_id,
            frame_type="vad.speech_started",
            turn_id=turn_id,
        )
        session = op_voice_session_event(
            conn,
            voice_session_id=voice_session_id,
            frame_type="vad.speech_stopped",
            turn_id=turn_id,
        )
    elif session.state == "listening":
        session = op_voice_session_event(
            conn,
            voice_session_id=voice_session_id,
            frame_type="vad.speech_stopped",
            turn_id=turn_id,
        )
    session_state = session["state"] if isinstance(session, dict) else session.state
    if session_state == "transcribing":
        op_voice_session_event(
            conn,
            voice_session_id=voice_session_id,
            frame_type="stt.final",
            payload={"text": text},
            turn_id=turn_id,
        )
    op_voice_session_event(
        conn,
        voice_session_id=voice_session_id,
        frame_type="core.submitted",
        payload={"workflow_ref": workflow_ref},
        turn_id=turn_id,
    )
    append_operator_utterance(conn, voice_session_id=voice_session_id, text=text, turn_id=turn_id)
    run_result = op_run_start(
        repo_root,
        conn,
        workflow_ref=workflow_ref,
        input_data={"objective": text, "voiceSessionId": voice_session_id, "turnId": turn_id},
    )
    response_text = _voice_response_text(workflow_ref, run_result)
    op_voice_session_event(
        conn,
        voice_session_id=voice_session_id,
        frame_type="core.output_text",
        payload={"run_id": run_result["run_id"], "response_text": response_text},
        turn_id=turn_id,
    )
    append_assistant_response(
        conn,
        voice_session_id=voice_session_id,
        text=response_text,
        voice_profile_ref=voice_profile["voice_profile_ref"],
        voice_id=voice_profile["voice_id"],
        turn_id=turn_id,
        run_id=run_result["run_id"],
    )
    return {
        "voice_session_id": voice_session_id,
        "state": "speaking",
        "recognized_text": text,
        "response_text": response_text,
        "run": run_result,
        "voice": voice_profile,
    }


__all__ = ("op_voice_session_close", "op_voice_session_event", "op_voice_session_start", "op_voice_submit_text")
