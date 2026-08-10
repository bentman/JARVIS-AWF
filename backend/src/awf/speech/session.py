"""Voice session state machine for ADR-0023.

The v1 voice session is anchored to an ADR-0020 active session: the
`voice_session_id` is the active `session_id`. State transitions are stored as
compact session entries and mirrored to the append-only `events` table. Raw
audio bytes are never persisted.
"""

import json
import sqlite3
from dataclasses import dataclass, field
from typing import Literal

from awf.events.writer import write_event
from awf.hardware.profiler import SYSTEM_RUN_ID, _ensure_system_run
from awf.memory.sessions import append_entry, start_session

VoiceSessionState = Literal["idle", "armed", "listening", "transcribing", "submitting", "speaking", "recovering", "closed"]
VoiceFrameType = Literal[
    "session.started",
    "session.idle",
    "session.closed",
    "wake.detected",
    "vad.speech_started",
    "vad.speech_stopped",
    "stt.partial",
    "stt.final",
    "core.submitted",
    "core.output_text",
    "tts.audio_chunk",
    "tts.done",
    "interruption",
    "error",
]

INITIAL_STATES: tuple[VoiceSessionState, ...] = ("idle", "armed")

_TRANSITIONS: dict[tuple[VoiceSessionState, VoiceFrameType], VoiceSessionState] = {
    ("idle", "session.started"): "idle",
    ("armed", "session.started"): "armed",
    ("idle", "session.idle"): "idle",
    ("armed", "session.idle"): "armed",
    ("listening", "session.idle"): "idle",
    ("recovering", "session.idle"): "idle",
    ("idle", "wake.detected"): "listening",
    ("armed", "wake.detected"): "listening",
    ("idle", "vad.speech_started"): "listening",
    ("armed", "vad.speech_started"): "listening",
    ("listening", "stt.partial"): "listening",
    ("listening", "vad.speech_stopped"): "transcribing",
    ("transcribing", "stt.partial"): "transcribing",
    ("transcribing", "stt.final"): "submitting",
    ("submitting", "core.submitted"): "submitting",
    ("submitting", "core.output_text"): "speaking",
    ("speaking", "tts.audio_chunk"): "speaking",
    ("speaking", "tts.done"): "idle",
    ("speaking", "vad.speech_started"): "listening",
    ("speaking", "interruption"): "listening",
    ("listening", "interruption"): "listening",
    ("idle", "error"): "recovering",
    ("armed", "error"): "recovering",
    ("listening", "error"): "recovering",
    ("transcribing", "error"): "recovering",
    ("submitting", "error"): "recovering",
    ("speaking", "error"): "recovering",
    ("recovering", "error"): "recovering",
}


class VoiceSessionError(RuntimeError):
    pass


@dataclass(frozen=True)
class VoiceFrame:
    frame_type: VoiceFrameType
    payload: dict = field(default_factory=dict)
    turn_id: str | None = None


@dataclass(frozen=True)
class VoiceSession:
    voice_session_id: str
    memory_session_id: str
    state: VoiceSessionState


def start_voice_session(
    conn: sqlite3.Connection, *, title: str | None = None, wake_enabled: bool = False
) -> VoiceSession:
    session = start_session(conn, title=title or "Voice session")
    state: VoiceSessionState = "armed" if wake_enabled else "idle"
    voice_session = VoiceSession(
        voice_session_id=session["session_id"],
        memory_session_id=session["session_id"],
        state=state,
    )
    _record_transition(
        conn,
        voice_session=voice_session,
        prior_state=None,
        frame=VoiceFrame("session.started", {"wake_enabled": wake_enabled}),
    )
    return voice_session


def current_voice_session(conn: sqlite3.Connection, *, voice_session_id: str) -> VoiceSession:
    rows = conn.execute(
        "SELECT content_json FROM active_session_entries WHERE session_id = ? ORDER BY rowid DESC",
        (voice_session_id,),
    ).fetchall()
    for row in rows:
        content = json.loads(row["content_json"])
        if content.get("kind") == "voice_state":
            return VoiceSession(
                voice_session_id=voice_session_id,
                memory_session_id=voice_session_id,
                state=content["state"],
            )
    raise VoiceSessionError(f"voice session {voice_session_id} has no state entry")


def accept_frame(conn: sqlite3.Connection, *, voice_session_id: str, frame: VoiceFrame) -> VoiceSession:
    voice_session = current_voice_session(conn, voice_session_id=voice_session_id)
    if voice_session.state == "closed":
        raise VoiceSessionError(f"voice session {voice_session_id} is closed")
    if frame.frame_type == "session.closed":
        next_state: VoiceSessionState = "closed"
    else:
        next_state = _TRANSITIONS.get((voice_session.state, frame.frame_type))
    if next_state is None:
        raise VoiceSessionError(f"cannot accept {frame.frame_type!r} while voice session is {voice_session.state!r}")
    next_session = VoiceSession(
        voice_session_id=voice_session.voice_session_id,
        memory_session_id=voice_session.memory_session_id,
        state=next_state,
    )
    _record_transition(conn, voice_session=next_session, prior_state=voice_session.state, frame=frame)
    if frame.frame_type == "interruption":
        append_entry(
            conn,
            session_id=voice_session.memory_session_id,
            role="system",
            content={"kind": "voice_interruption", "turn_id": frame.turn_id, **frame.payload},
            summary="voice interruption",
        )
    return next_session


def append_operator_utterance(conn: sqlite3.Connection, *, voice_session_id: str, text: str, turn_id: str | None) -> dict:
    return append_entry(
        conn,
        session_id=voice_session_id,
        role="operator",
        content={"kind": "voice_utterance", "text": text, "turn_id": turn_id},
        summary=text,
    )


def append_assistant_response(
    conn: sqlite3.Connection,
    *,
    voice_session_id: str,
    text: str,
    voice_profile_ref: str,
    voice_id: str,
    turn_id: str | None,
    run_id: str | None = None,
) -> dict:
    return append_entry(
        conn,
        session_id=voice_session_id,
        role="assistant",
        content={
            "kind": "voice_response",
            "text": text,
            "voice_profile_ref": voice_profile_ref,
            "voice_id": voice_id,
            "turn_id": turn_id,
            "run_id": run_id,
        },
        summary=text,
    )


def _record_transition(
    conn: sqlite3.Connection,
    *,
    voice_session: VoiceSession,
    prior_state: VoiceSessionState | None,
    frame: VoiceFrame,
) -> None:
    payload = {
        "voice_session_id": voice_session.voice_session_id,
        "memory_session_id": voice_session.memory_session_id,
        "frame_type": frame.frame_type,
        "prior_state": prior_state,
        "state": voice_session.state,
        "turn_id": frame.turn_id,
        "payload": _redact_audio(frame.payload),
    }
    append_entry(
        conn,
        session_id=voice_session.memory_session_id,
        role="system",
        content={"kind": "voice_state", **payload},
        summary=f"{frame.frame_type}: {prior_state or 'none'} -> {voice_session.state}",
    )
    _ensure_system_run(conn)
    write_event(
        conn,
        run_id=SYSTEM_RUN_ID,
        new_status=voice_session.state,
        prior_status=prior_state,
        actor="voice_session",
        reason_code="voice_session_frame",
        payload_json=json.dumps(payload, sort_keys=True),
    )


def _redact_audio(payload: dict) -> dict:
    redacted = dict(payload)
    for key in ("audio", "audio_bytes", "pcm", "samples"):
        if key in redacted:
            redacted[key] = "<redacted>"
    return redacted
