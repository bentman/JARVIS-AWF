"""The Section 16.4 voice pipeline, chained: Hardware Profiler -> wake word /
push-to-talk -> Silero VAD (endpointing) -> Whisper STT -> core -> Kokoro TTS.

Chains the four speech adapters in this package (`wake_*`, `vad_*`, `stt_*`,
`tts_*`) into one activation -> command -> response cycle, carrying real
output from each step into the next. Section 16.4: the Hardware Profiler
runs "before any voice model is downloaded or loaded" - it resolves first,
and its result actually selects the STT model/device/compute_type (via
`awf.speech.models.stt_runtime`) rather than just being logged.

"core" here is any callable that takes the recognized command text and
returns a response string - the caller supplies it (a real AWF Run via
`awf.cli.core_ops`, a trivial echo, or anything else) since the pipeline
itself has no opinion on what the core does with the text.

`repo_root` resolves the STT runtime from `config/voice/stt.yaml` and checks
the resolved profile's `config/voice/` manifests against the real model
files already passed in, logging the result to the `events` table.
"""

import json
import sqlite3
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

from awf.events.writer import write_event
from awf.hardware.preflight import collect_preflight_tokens
from awf.hardware.profiler import SYSTEM_RUN_ID, collect_inventory, run_hardware_profiler
from awf.hardware.readiness import (
    derive_stt_readiness,
    derive_tts_readiness,
    derive_vad_readiness,
    derive_wake_readiness,
)
from awf.speech.models import artifact_paths, stt_runtime, verify_models
from awf.speech.stt_onnx import transcribe
from awf.speech.tts_kokoro import synthesize
from awf.speech.vad_silero import speech_segments
from awf.speech.wake_openwakeword import detect_wake_word

CoreFn = Callable[[str], str]


class VoicePipelineError(RuntimeError):
    pass


@dataclass(frozen=True)
class VoiceRoundTripResult:
    hardware_profile_id: str
    wake_detected: bool
    wake_score: float
    speech_segments: tuple[tuple[float, float], ...]
    command_text: str
    command_language: str
    response_text: str
    response_audio: "tuple"  # (samples: np.ndarray, sample_rate: int)


def _verify_and_log_pinned_models(conn: sqlite3.Connection, repo_root: Path, profile_id: str, readiness: dict) -> None:
    """Section 16.4's pinned manifests (`config/voice/*`) exist and are
    checked here, but a missing artifact is logged, not raised - this is an
    audit record of what's actually installed against what's named, the
    same "every probe result and fallback decision is written to the
    events table" contract the Hardware Profiler's own resolution already
    follows, not a hard gate on whether the round trip may proceed."""
    verifications = verify_models(repo_root)
    write_event(
        conn,
        run_id=SYSTEM_RUN_ID,
        new_status="VERIFIED",
        actor="hardware_profiler",
        reason_code="pinned_model_verification",
        payload_json=json.dumps(
            {
                "profile_id": profile_id,
                "verifications": verifications,
                "readiness": {name: asdict(result) for name, result in readiness.items()},
            }
        ),
    )


def run_voice_round_trip(
    conn: sqlite3.Connection,
    *,
    repo_root: Path,
    wake_audio_path: Path,
    command_audio_path: Path,
    wake_model_path: Path,
    wake_melspec_model_path: Path,
    wake_embedding_model_path: Path,
    vad_model_path: Path,
    tts_model_path: Path,
    tts_voices_path: Path,
    voice_id: str,
    core_fn: CoreFn,
    wake_threshold: float = 0.5,
) -> VoiceRoundTripResult:
    """Runs one full activation -> command -> response cycle.

    Raises VoicePipelineError if the wake word never fires or if VAD finds no
    speech in the command audio - a real pipeline must not silently proceed
    past either check, mirroring the durability rule's "no silent success."
    """
    hardware_profile_id = run_hardware_profiler(conn, repo_root=repo_root)

    inventory = collect_inventory()
    tokens = collect_preflight_tokens(inventory)
    vad_paths = artifact_paths(repo_root, "vad")
    wake_paths = artifact_paths(repo_root, "wake")
    readiness = {
        "stt": derive_stt_readiness(inventory, tokens),
        "tts": derive_tts_readiness(inventory, tokens),
        "vad": derive_vad_readiness(inventory, tokens, vad_paths.get("silero_vad.onnx")),
        "wake": derive_wake_readiness(inventory, tokens, wake_paths),
    }

    runtime = stt_runtime(repo_root, readiness["stt"].device)

    _verify_and_log_pinned_models(conn, repo_root, hardware_profile_id, readiness)

    wake_result = detect_wake_word(
        wake_audio_path,
        wake_model_path,
        melspec_model_path=wake_melspec_model_path,
        embedding_model_path=wake_embedding_model_path,
        threshold=wake_threshold,
    )
    if not wake_result["detected"]:
        raise VoicePipelineError(f"wake word did not fire on {wake_audio_path} (score={wake_result['score']:.4f})")

    segments = speech_segments(command_audio_path, vad_model_path)
    if not segments:
        raise VoicePipelineError(f"no speech detected in {command_audio_path}")

    stt_result = transcribe(
        command_audio_path,
        repo_root=repo_root,
        runtime=runtime,
    )
    command_text = stt_result["text"]
    if not command_text.strip():
        raise VoicePipelineError(f"STT produced empty text for {command_audio_path}")

    response_text = core_fn(command_text)

    samples, sample_rate = synthesize(
        response_text, voice_id, model_path=tts_model_path, voices_path=tts_voices_path, device=readiness["tts"].device
    )

    return VoiceRoundTripResult(
        hardware_profile_id=hardware_profile_id,
        wake_detected=True,
        wake_score=wake_result["score"],
        speech_segments=tuple(segments),
        command_text=command_text,
        command_language=stt_result["language"],
        response_text=response_text,
        response_audio=(samples, sample_rate),
    )
