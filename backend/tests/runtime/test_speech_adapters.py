import numpy as np
import pytest

from awf.speech.models import _stt_cache_name as stt_cache_name
from awf.speech.models import artifact_paths
from awf.speech.stt_whisper import transcribe
from awf.speech.tts_kokoro import synthesize
from awf.speech.vad_silero import speech_segments
from awf.speech.wake_openwakeword import WakeWordAdapterError, detect_wake_word

pytestmark = pytest.mark.live

_MODEL_RELATIVE_PATHS = (
    "wake/hey_jarvis_v0.1.onnx",
    "wake/melspectrogram.onnx",
    "wake/embedding_model.onnx",
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
    wake_paths = artifact_paths(repo_root, "wake")
    vad_paths = artifact_paths(repo_root, "vad")
    tts_paths = artifact_paths(repo_root, "tts")
    return {
        "wake": wake_paths["hey_jarvis_v0.1.onnx"],
        "wake_melspec": wake_paths["melspectrogram.onnx"],
        "wake_embedding": wake_paths["embedding_model.onnx"],
        "vad": vad_paths["silero_vad.onnx"],
        "tts_model": tts_paths["kokoro-v1.0.onnx"],
        "tts_voices": tts_paths["voices-v1.0.bin"],
        "stt_download_root": repo_root / "models" / "stt",
        "faster_whisper_stt_model": repo_root / "models" / "stt" / stt_cache_name("small"),
    }


def _require_local_stt_model(path):
    if not path.is_dir():
        pytest.skip(f"local faster-whisper STT model is incomplete at {path} - run Phase 12 setup first")


def test_wake_word_fires_on_real_hey_jarvis_audio(fixtures_dir, voice_models):
    result = detect_wake_word(
        fixtures_dir / "hey_jarvis.wav",
        voice_models["wake"],
        melspec_model_path=voice_models["wake_melspec"],
        embedding_model_path=voice_models["wake_embedding"],
    )
    assert result["detected"] is True
    assert result["score"] > 0.5


def test_wake_word_fires_on_reference_hey_jarvis_audio(fixtures_dir, voice_models):
    result = detect_wake_word(
        fixtures_dir / "hey_jarvis_ref.wav",
        voice_models["wake"],
        melspec_model_path=voice_models["wake_melspec"],
        embedding_model_path=voice_models["wake_embedding"],
    )
    assert result["detected"] is True


def test_wake_word_does_not_fire_on_unrelated_speech(fixtures_dir, voice_models):
    result = detect_wake_word(
        fixtures_dir / "hello_world.wav",
        voice_models["wake"],
        melspec_model_path=voice_models["wake_melspec"],
        embedding_model_path=voice_models["wake_embedding"],
    )
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
        detect_wake_word(
            bad,
            voice_models["wake"],
            melspec_model_path=voice_models["wake_melspec"],
            embedding_model_path=voice_models["wake_embedding"],
        )


def test_vad_detects_speech_segment_in_hey_jarvis_audio(fixtures_dir, voice_models):
    segments = speech_segments(fixtures_dir / "hey_jarvis.wav", voice_models["vad"])
    assert len(segments) >= 1
    start, end = segments[0]
    assert end > start


def test_vad_detects_speech_segment_in_hello_world_audio(fixtures_dir, voice_models):
    segments = speech_segments(fixtures_dir / "hello_world.wav", voice_models["vad"])
    assert len(segments) >= 1


def test_stt_transcribes_hello_world_correctly(fixtures_dir, voice_models):
    _require_local_stt_model(voice_models["faster_whisper_stt_model"])
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
