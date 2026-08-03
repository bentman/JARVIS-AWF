from pathlib import Path

import pytest

from awf.speech.pipeline import (
    VoicePipelineError,
    run_voice_round_trip,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
MODELS = REPO_ROOT / "models"

WAKE_MODEL = MODELS / "wake" / "hey_jarvis_v0.1.onnx"
VAD_MODEL = MODELS / "vad" / "silero_vad.onnx"
TTS_MODEL = MODELS / "tts" / "kokoro-v1.0.onnx"
TTS_VOICES = MODELS / "tts" / "voices-v1.0.bin"

pytestmark = pytest.mark.skipif(
    not (WAKE_MODEL.is_file() and VAD_MODEL.is_file() and TTS_MODEL.is_file() and TTS_VOICES.is_file()),
    reason="voice models not present under models/ - run Phase 12 setup first",
)


def test_full_round_trip_wake_stt_response_tts():
    """Exercises the full chain: wake-word detection on hey_jarvis.wav,
    VAD + STT on hello_world.wav, a trivial core response, and Kokoro
    synthesis."""

    def core_fn(command_text: str) -> str:
        return f"Acknowledged: {command_text.strip()}"

    result = run_voice_round_trip(
        wake_audio_path=FIXTURES / "hey_jarvis.wav",
        command_audio_path=FIXTURES / "hello_world.wav",
        wake_model_path=WAKE_MODEL,
        vad_model_path=VAD_MODEL,
        tts_model_path=TTS_MODEL,
        tts_voices_path=TTS_VOICES,
        voice_id="bf_isabella",
        core_fn=core_fn,
        stt_download_root=MODELS / "stt",
    )

    assert result.wake_detected is True
    assert result.wake_score > 0.5
    assert len(result.speech_segments) >= 1
    assert "hello" in result.command_text.lower()
    assert "world" in result.command_text.lower()
    assert result.command_language == "en"
    assert result.response_text == "Acknowledged: Hello world."

    samples, sample_rate = result.response_audio
    assert sample_rate > 0
    assert len(samples) > 0


def test_round_trip_raises_when_wake_word_does_not_fire():
    def core_fn(command_text: str) -> str:
        return "unreachable"

    with pytest.raises(VoicePipelineError, match="wake word did not fire"):
        run_voice_round_trip(
            wake_audio_path=FIXTURES / "hello_world.wav",  # not a wake-word utterance
            command_audio_path=FIXTURES / "hello_world.wav",
            wake_model_path=WAKE_MODEL,
            vad_model_path=VAD_MODEL,
            tts_model_path=TTS_MODEL,
            tts_voices_path=TTS_VOICES,
            voice_id="bf_isabella",
            core_fn=core_fn,
            stt_download_root=MODELS / "stt",
        )


def test_round_trip_carries_core_fn_response_verbatim_into_tts_input():
    seen_text = {}

    def core_fn(command_text: str) -> str:
        seen_text["value"] = command_text
        return "A distinctive, checkable response string."

    result = run_voice_round_trip(
        wake_audio_path=FIXTURES / "hey_jarvis.wav",
        command_audio_path=FIXTURES / "hello_world.wav",
        wake_model_path=WAKE_MODEL,
        vad_model_path=VAD_MODEL,
        tts_model_path=TTS_MODEL,
        tts_voices_path=TTS_VOICES,
        voice_id="am_michael",
        core_fn=core_fn,
        stt_download_root=MODELS / "stt",
    )

    assert "hello" in seen_text["value"].lower()
    assert result.response_text == "A distinctive, checkable response string."
