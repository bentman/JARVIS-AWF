import json
from unittest.mock import MagicMock

import awf.speech.cli as speech_cli


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
