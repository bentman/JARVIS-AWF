import pytest

from awf.db.bootstrap import init_db
from awf.db.connection import get_connection
from awf.speech.pipeline import (
    VoicePipelineError,
    _stt_device_for_profile,
    run_voice_round_trip,
)

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


def test_stt_device_selection_uses_cuda_only_when_profile_says_cuda():
    assert _stt_device_for_profile("linux-x64-cuda") == ("cuda", "float16")
    assert _stt_device_for_profile("windows-x64-cuda") == ("cuda", "float16")
    assert _stt_device_for_profile("linux-x64-cpu") == ("cpu", "int8")
    assert _stt_device_for_profile("linux-x64-gpu") == ("cpu", "int8")
    assert _stt_device_for_profile("windows-arm64-qnn") == ("cpu", "int8")


def make_conn(tmp_path):
    db_path = tmp_path / "awf.db"
    init_db(db_path)
    return get_connection(db_path)


def test_full_round_trip_wake_stt_response_tts(tmp_path, fixtures_dir, voice_models):
    """Exercises the full chain: the Hardware Profiler, wake-word detection
    on hey_jarvis.wav, VAD + STT on hello_world.wav, a trivial core
    response, and Kokoro synthesis."""
    conn = make_conn(tmp_path)

    def core_fn(command_text: str) -> str:
        return f"Acknowledged: {command_text.strip()}"

    result = run_voice_round_trip(
        conn,
        wake_audio_path=fixtures_dir / "hey_jarvis.wav",
        command_audio_path=fixtures_dir / "hello_world.wav",
        wake_model_path=voice_models["wake"],
        vad_model_path=voice_models["vad"],
        tts_model_path=voice_models["tts_model"],
        tts_voices_path=voice_models["tts_voices"],
        voice_id="bf_isabella",
        core_fn=core_fn,
        stt_download_root=voice_models["stt_download_root"],
    )

    assert result.hardware_profile_id  # e.g. linux-x64-cpu, resolved by the hardware profiler, not stubbed
    resolved_event = conn.execute(
        "SELECT * FROM events WHERE actor = 'hardware_profiler' AND reason_code = 'hardware_profile_resolved'"
    ).fetchone()
    assert resolved_event is not None
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


def test_round_trip_with_repo_root_verifies_real_pinned_models_and_logs_it(
    tmp_path, repo_root, fixtures_dir, voice_models
):
    # A round trip against the already-downloaded models on this host,
    # checked against the shipped config/voice/*/linux-x64-*.yaml pins.
    conn = make_conn(tmp_path)

    run_voice_round_trip(
        conn,
        wake_audio_path=fixtures_dir / "hey_jarvis.wav",
        command_audio_path=fixtures_dir / "hello_world.wav",
        wake_model_path=voice_models["wake"],
        vad_model_path=voice_models["vad"],
        tts_model_path=voice_models["tts_model"],
        tts_voices_path=voice_models["tts_voices"],
        voice_id="bf_isabella",
        core_fn=lambda text: "ok",
        stt_download_root=voice_models["stt_download_root"],
        repo_root=repo_root,
    )

    event = conn.execute(
        "SELECT payload_json FROM events WHERE actor = 'hardware_profiler' "
        "AND reason_code = 'pinned_model_verification'"
    ).fetchone()
    assert event is not None
    import json

    payload = json.loads(event["payload_json"])
    functions_checked = {v["function"] for v in payload["verifications"]}
    assert functions_checked == {"wake", "vad", "tts", "stt"}
    for verification in payload["verifications"]:
        for result in verification["results"]:
            assert result["status"] == "OK", verification


def test_round_trip_raises_when_wake_word_does_not_fire(tmp_path, fixtures_dir, voice_models):
    conn = make_conn(tmp_path)

    def core_fn(command_text: str) -> str:
        return "unreachable"

    with pytest.raises(VoicePipelineError, match="wake word did not fire"):
        run_voice_round_trip(
            conn,
            wake_audio_path=fixtures_dir / "hello_world.wav",  # not a wake-word utterance
            command_audio_path=fixtures_dir / "hello_world.wav",
            wake_model_path=voice_models["wake"],
            vad_model_path=voice_models["vad"],
            tts_model_path=voice_models["tts_model"],
            tts_voices_path=voice_models["tts_voices"],
            voice_id="bf_isabella",
            core_fn=core_fn,
            stt_download_root=voice_models["stt_download_root"],
        )


def test_round_trip_carries_core_fn_response_verbatim_into_tts_input(
    tmp_path, monkeypatch, fixtures_dir, voice_models
):
    # The full chain (wake -> VAD -> STT -> TTS) is exercised by
    # test_full_round_trip_wake_stt_response_tts above - this test only
    # checks that core_fn's response is what reaches synthesize, so the
    # four heavy model calls are faked rather than loaded a second time.
    conn = make_conn(tmp_path)
    seen_text = {}
    synthesize_args = {}

    monkeypatch.setattr(
        "awf.speech.pipeline.detect_wake_word", lambda *a, **k: {"detected": True, "score": 0.99}
    )
    monkeypatch.setattr("awf.speech.pipeline.speech_segments", lambda *a, **k: [(0.0, 1.0)])
    monkeypatch.setattr(
        "awf.speech.pipeline.transcribe",
        lambda *a, **k: {"text": "hello world", "language": "en"},
    )

    def fake_synthesize(text, voice_id, **kwargs):
        synthesize_args["text"] = text
        return ([0.0, 0.0], 16000)

    monkeypatch.setattr("awf.speech.pipeline.synthesize", fake_synthesize)

    def core_fn(command_text: str) -> str:
        seen_text["value"] = command_text
        return "A distinctive, checkable response string."

    result = run_voice_round_trip(
        conn,
        wake_audio_path=fixtures_dir / "hey_jarvis.wav",
        command_audio_path=fixtures_dir / "hello_world.wav",
        wake_model_path=voice_models["wake"],
        vad_model_path=voice_models["vad"],
        tts_model_path=voice_models["tts_model"],
        tts_voices_path=voice_models["tts_voices"],
        voice_id="am_michael",
        core_fn=core_fn,
        stt_download_root=voice_models["stt_download_root"],
    )

    assert "hello" in seen_text["value"].lower()
    assert result.response_text == "A distinctive, checkable response string."
    assert synthesize_args["text"] == "A distinctive, checkable response string."
