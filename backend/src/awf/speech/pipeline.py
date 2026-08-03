"""The Section 16.4 voice pipeline, chained: Hardware Profiler -> wake word /
push-to-talk -> Silero VAD (endpointing) -> Whisper STT -> core -> Kokoro TTS.

Chains the four speech adapters in this package (`wake_*`, `vad_*`, `stt_*`,
`tts_*`) into one activation -> command -> response cycle, carrying real
output from each step into the next. Section 16.4: the Hardware Profiler
runs "before any voice model is downloaded or loaded" - it resolves first,
and its result actually selects the STT device/compute_type rather than
just being logged.

"core" here is any callable that takes the recognized command text and
returns a response string - the caller supplies it (a real AWF Run via
`awf.cli.core_ops`, a trivial echo, or anything else) since the pipeline
itself has no opinion on what the core does with the text.
"""

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from awf.hardware.profiler import run_hardware_profiler
from awf.speech.stt_whisper import transcribe
from awf.speech.tts_kokoro import synthesize
from awf.speech.vad_silero import speech_segments
from awf.speech.wake_openwakeword import detect_wake_word

CoreFn = Callable[[str], str]

# Profiles ending in one of these suffixes have a probe-verified accelerator
# faster-whisper/CTranslate2 can actually use; anything else falls back to
# the CPU floor (Section 16.4: "every profile falls back to its arch's
# `*64-cpu` floor").
ACCELERATED_STT_DEVICES = {"cuda": ("cuda", "float16")}


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


def _stt_device_for_profile(profile_id: str) -> tuple[str, str]:
    for suffix, (device, compute_type) in ACCELERATED_STT_DEVICES.items():
        if profile_id.endswith(f"-{suffix}"):
            return device, compute_type
    return "cpu", "int8"


def run_voice_round_trip(
    conn: sqlite3.Connection,
    *,
    wake_audio_path: Path,
    command_audio_path: Path,
    wake_model_path: Path,
    vad_model_path: Path,
    tts_model_path: Path,
    tts_voices_path: Path,
    voice_id: str,
    core_fn: CoreFn,
    stt_model_size: str = "small",
    stt_download_root: Path | None = None,
    wake_threshold: float = 0.5,
) -> VoiceRoundTripResult:
    """Runs one full activation -> command -> response cycle.

    Raises VoicePipelineError if the wake word never fires or if VAD finds no
    speech in the command audio - a real pipeline must not silently proceed
    past either check, mirroring the durability rule's "no silent success."
    """
    hardware_profile_id = run_hardware_profiler(conn)
    stt_device, stt_compute_type = _stt_device_for_profile(hardware_profile_id)

    wake_result = detect_wake_word(wake_audio_path, wake_model_path, threshold=wake_threshold)
    if not wake_result["detected"]:
        raise VoicePipelineError(
            f"wake word did not fire on {wake_audio_path} (score={wake_result['score']:.4f})"
        )

    segments = speech_segments(command_audio_path, vad_model_path)
    if not segments:
        raise VoicePipelineError(f"no speech detected in {command_audio_path}")

    stt_result = transcribe(
        command_audio_path,
        model_size=stt_model_size,
        device=stt_device,
        compute_type=stt_compute_type,
        download_root=stt_download_root,
    )
    command_text = stt_result["text"]
    if not command_text.strip():
        raise VoicePipelineError(f"STT produced empty text for {command_audio_path}")

    response_text = core_fn(command_text)

    samples, sample_rate = synthesize(
        response_text, voice_id, model_path=tts_model_path, voices_path=tts_voices_path
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
