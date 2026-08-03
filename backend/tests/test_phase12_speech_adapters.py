from pathlib import Path

import numpy as np
import pytest

from awf.speech.stt_whisper import transcribe
from awf.speech.tts_kokoro import synthesize
from awf.speech.vad_silero import speech_segments
from awf.speech.wake_openwakeword import WakeWordAdapterError, detect_wake_word

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


def test_wake_word_fires_on_real_hey_jarvis_audio():
    result = detect_wake_word(FIXTURES / "hey_jarvis.wav", WAKE_MODEL)
    assert result["detected"] is True
    assert result["score"] > 0.5


def test_wake_word_fires_on_reference_hey_jarvis_audio():
    result = detect_wake_word(FIXTURES / "hey_jarvis_ref.wav", WAKE_MODEL)
    assert result["detected"] is True


def test_wake_word_does_not_fire_on_unrelated_speech():
    result = detect_wake_word(FIXTURES / "hello_world.wav", WAKE_MODEL)
    assert result["detected"] is False
    assert result["score"] < 0.1


def test_wake_word_rejects_wrong_sample_rate(tmp_path):
    import wave

    bad = tmp_path / "bad.wav"
    with wave.open(str(bad), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b"\x00\x00" * 8000)

    with pytest.raises(WakeWordAdapterError):
        detect_wake_word(bad, WAKE_MODEL)


def test_vad_detects_speech_segment_in_hey_jarvis_audio():
    segments = speech_segments(FIXTURES / "hey_jarvis.wav", VAD_MODEL)
    assert len(segments) >= 1
    start, end = segments[0]
    assert end > start


def test_vad_detects_speech_segment_in_hello_world_audio():
    segments = speech_segments(FIXTURES / "hello_world.wav", VAD_MODEL)
    assert len(segments) >= 1


def test_stt_transcribes_hello_world_correctly():
    result = transcribe(FIXTURES / "hello_world.wav", model_size="small", download_root=MODELS / "stt")
    assert "hello" in result["text"].lower()
    assert "world" in result["text"].lower()
    assert result["language"] == "en"


def test_tts_synthesizes_real_distinct_audio_for_different_voices():
    samples_a, sr_a = synthesize(
        "The build passed all tests.", "bf_isabella", model_path=TTS_MODEL, voices_path=TTS_VOICES
    )
    samples_b, sr_b = synthesize(
        "The build passed all tests.", "am_michael", model_path=TTS_MODEL, voices_path=TTS_VOICES
    )

    assert sr_a == sr_b
    assert len(samples_a) > 0 and len(samples_b) > 0
    # Different voice_ids for the same text must not produce identical audio.
    assert samples_a.shape != samples_b.shape or not np.allclose(samples_a, samples_b)
