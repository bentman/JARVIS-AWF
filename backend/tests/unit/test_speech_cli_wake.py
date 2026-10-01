import json
from unittest.mock import MagicMock

import awf.speech.cli as speech_cli


def test_wake_resolves_readiness_and_prints_json(tmp_path, repo_root, monkeypatch, capsys):
    import awf.hardware.preflight as preflight
    import awf.hardware.profiler as profiler
    import awf.hardware.readiness as readiness
    import awf.speech.wake_openwakeword as wake_adapter

    fake_readiness = MagicMock()
    fake_readiness.ready = True

    monkeypatch.setattr(profiler, "collect_inventory", lambda: MagicMock())
    monkeypatch.setattr(preflight, "collect_preflight_tokens", lambda inv: [])
    monkeypatch.setattr(readiness, "derive_wake_readiness", lambda inv, tok, paths: fake_readiness)
    monkeypatch.setattr(
        wake_adapter,
        "detect_wake_word",
        lambda path, **kwargs: {"detected": True, "score": 0.94},
    )

    audio_path = tmp_path / "wake.wav"
    audio_path.write_bytes(b"RIFF")

    exit_code = speech_cli.run(["wake", str(audio_path)], repo_root)

    assert exit_code == 0
    out = capsys.readouterr().out
    result = json.loads(out)
    assert result == {"detected": True, "score": 0.94}


def test_wake_returns_error_when_not_ready(tmp_path, repo_root, monkeypatch, capsys):
    import awf.hardware.preflight as preflight
    import awf.hardware.profiler as profiler
    import awf.hardware.readiness as readiness

    fake_readiness = MagicMock()
    fake_readiness.ready = False
    fake_readiness.reason = "openwakeword not importable"

    monkeypatch.setattr(profiler, "collect_inventory", lambda: MagicMock())
    monkeypatch.setattr(preflight, "collect_preflight_tokens", lambda inv: [])
    monkeypatch.setattr(readiness, "derive_wake_readiness", lambda inv, tok, paths: fake_readiness)

    audio_path = tmp_path / "wake.wav"
    audio_path.write_bytes(b"RIFF")

    exit_code = speech_cli.run(["wake", str(audio_path)], repo_root)

    assert exit_code == 1
    out = capsys.readouterr().out
    result = json.loads(out)
    assert "openwakeword not importable" in result["error"]
