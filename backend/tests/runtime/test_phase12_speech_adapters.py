import numpy as np
import pytest

from awf.speech.stt_whisper import transcribe
from awf.speech.tts_kokoro import synthesize
from awf.speech.vad_silero import speech_segments
from awf.speech.wake_openwakeword import WakeWordAdapterError, detect_wake_word

pytestmark = pytest.mark.live

_MODEL_RELATIVE_PATHS = (
    "wake/hey_jarvis_v0.1.onnx",
    "vad/silero_vad.onnx",
    "tts/kokoro-v1.0.onnx",
    "tts/voices-v1.0.bin",
)


@pytest.fixture(autouse=True)
def _require_voice_models(models_present):
    if not models_present(*_MODEL_RELATIVE_PATHS):
        pytest.skip("voice models not present under models/ - run Phase 12 setup first")


@pytest.fixture
def voice_models(repo_root):
    models = repo_root / "models"
    return {
        "wake": models / "wake" / "hey_jarvis_v0.1.onnx",
        "vad": models / "vad" / "silero_vad.onnx",
        "tts_model": models / "tts" / "kokoro-v1.0.onnx",
        "tts_voices": models / "tts" / "voices-v1.0.bin",
        "stt_download_root": models / "stt",
    }


def test_wake_word_fires_on_real_hey_jarvis_audio(fixtures_dir, voice_models):
    result = detect_wake_word(fixtures_dir / "hey_jarvis.wav", voice_models["wake"])
    assert result["detected"] is True
    assert result["score"] > 0.5


def test_wake_word_fires_on_reference_hey_jarvis_audio(fixtures_dir, voice_models):
    result = detect_wake_word(fixtures_dir / "hey_jarvis_ref.wav", voice_models["wake"])
    assert result["detected"] is True


def test_wake_word_does_not_fire_on_unrelated_speech(fixtures_dir, voice_models):
    result = detect_wake_word(fixtures_dir / "hello_world.wav", voice_models["wake"])
    assert result["detected"] is False
    assert result["score"] < 0.1


def test_wake_word_rejects_wrong_sample_rate(tmp_path, voice_models):
    import wave

    bad = tmp_path / "bad.wav"
    with wave.open(str(bad), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b"\x00\x00" * 8000)

    with pytest.raises(WakeWordAdapterError):
        detect_wake_word(bad, voice_models["wake"])


def test_vad_detects_speech_segment_in_hey_jarvis_audio(fixtures_dir, voice_models):
    segments = speech_segments(fixtures_dir / "hey_jarvis.wav", voice_models["vad"])
    assert len(segments) >= 1
    start, end = segments[0]
    assert end > start


def test_vad_detects_speech_segment_in_hello_world_audio(fixtures_dir, voice_models):
    segments = speech_segments(fixtures_dir / "hello_world.wav", voice_models["vad"])
    assert len(segments) >= 1


def test_stt_transcribes_hello_world_correctly(fixtures_dir, voice_models):
    result = transcribe(
        fixtures_dir / "hello_world.wav", model_size="small", download_root=voice_models["stt_download_root"]
    )
    assert "hello" in result["text"].lower()
    assert "world" in result["text"].lower()
    assert result["language"] == "en"


def test_tts_synthesizes_real_distinct_audio_for_different_voices(voice_models):
    samples_a, sr_a = synthesize(
        "The build passed all tests.",
        "bf_isabella",
        model_path=voice_models["tts_model"],
        voices_path=voice_models["tts_voices"],
    )
    samples_b, sr_b = synthesize(
        "The build passed all tests.",
        "am_michael",
        model_path=voice_models["tts_model"],
        voices_path=voice_models["tts_voices"],
    )

    assert sr_a == sr_b
    assert len(samples_a) > 0 and len(samples_b) > 0
    # Different voice_ids for the same text must not produce identical audio.
    assert samples_a.shape != samples_b.shape or not np.allclose(samples_a, samples_b)
