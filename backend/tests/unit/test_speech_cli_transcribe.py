import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import awf.speech.cli as speech_cli
from awf.speech import stt_whisper


def test_transcribe_resolves_readiness_and_prints_json(tmp_path, repo_root, monkeypatch, capsys):
    import awf.hardware.preflight as preflight
    import awf.hardware.profiler as profiler
    import awf.hardware.readiness as readiness
    import awf.speech.models as models
    import awf.speech.stt_onnx as stt_onnx

    fake_readiness = MagicMock()
    fake_readiness.ready = True
    fake_readiness.device = "cpu"
    fake_runtime = MagicMock()

    monkeypatch.setattr(profiler, "collect_inventory", lambda: MagicMock())
    monkeypatch.setattr(preflight, "collect_preflight_tokens", lambda inv: [])
    monkeypatch.setattr(readiness, "derive_stt_readiness", lambda inv, tok: fake_readiness)
    monkeypatch.setattr(models, "stt_runtime", lambda repo, device: fake_runtime)
    monkeypatch.setattr(
        stt_onnx,
        "transcribe",
        lambda path, *, repo_root, runtime: {"text": "Hello world.", "language": "en", "language_probability": 0.99},
    )

    audio_path = tmp_path / "clip.wav"
    audio_path.write_bytes(b"RIFF")

    exit_code = speech_cli.run(["transcribe", str(audio_path)], repo_root)

    assert exit_code == 0
    out = capsys.readouterr().out
    result = json.loads(out)
    assert result == {"text": "Hello world.", "language": "en"}


def test_transcribe_returns_error_when_stt_not_ready(tmp_path, repo_root, monkeypatch, capsys):
    import awf.hardware.preflight as preflight
    import awf.hardware.profiler as profiler
    import awf.hardware.readiness as readiness

    fake_readiness = MagicMock()
    fake_readiness.ready = False
    fake_readiness.reason = "no STT runtime importable"

    monkeypatch.setattr(profiler, "collect_inventory", lambda: MagicMock())
    monkeypatch.setattr(preflight, "collect_preflight_tokens", lambda inv: [])
    monkeypatch.setattr(readiness, "derive_stt_readiness", lambda inv, tok: fake_readiness)

    audio_path = tmp_path / "clip.wav"
    audio_path.write_bytes(b"RIFF")

    exit_code = speech_cli.run(["transcribe", str(audio_path)], repo_root)

    assert exit_code == 1
    out = capsys.readouterr().out
    result = json.loads(out)
    assert "error" in result
    assert "no STT runtime importable" in result["error"]


def test_transcribe_returns_error_when_runtime_fails(tmp_path, repo_root, monkeypatch, capsys):
    import awf.hardware.preflight as preflight
    import awf.hardware.profiler as profiler
    import awf.hardware.readiness as readiness
    import awf.speech.models as models
    import awf.speech.stt_onnx as stt_onnx

    fake_readiness = MagicMock()
    fake_readiness.ready = True
    fake_readiness.device = "cpu"

    monkeypatch.setattr(profiler, "collect_inventory", lambda: MagicMock())
    monkeypatch.setattr(preflight, "collect_preflight_tokens", lambda inv: [])
    monkeypatch.setattr(readiness, "derive_stt_readiness", lambda inv, tok: fake_readiness)
    monkeypatch.setattr(models, "stt_runtime", lambda repo, device: MagicMock())
    monkeypatch.setattr(
        stt_onnx, "transcribe", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("missing model"))
    )

    audio_path = tmp_path / "clip.wav"
    audio_path.write_bytes(b"RIFF")

    exit_code = speech_cli.run(["transcribe", str(audio_path)], repo_root)

    assert exit_code == 1
    result = json.loads(capsys.readouterr().out)
    assert result == {"error": "STT failed: missing model"}


def test_faster_whisper_transcribe_uses_local_files_only(tmp_path, monkeypatch):
    seen = {}

    class FakeWhisperModel:
        def __init__(self, *args, **kwargs):
            seen["init"] = {"args": args, "kwargs": kwargs}

        def transcribe(self, audio_path):
            seen["audio_path"] = audio_path
            info = SimpleNamespace(language="en", language_probability=1.0)
            segment = SimpleNamespace(text="Hello world.")
            return [segment], info

    monkeypatch.setitem(__import__("sys").modules, "faster_whisper", SimpleNamespace(WhisperModel=FakeWhisperModel))

    result = stt_whisper.transcribe(tmp_path / "clip.wav", download_root=tmp_path / "models")

    assert result["text"] == "Hello world."
    assert seen["init"]["kwargs"]["local_files_only"] is True
