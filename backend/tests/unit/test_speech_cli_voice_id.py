import awf.speech.cli as speech_cli


def _stub_db_path(tmp_path):
    def fake_db_path(_repo_root):
        return tmp_path / "awf.db"

    return fake_db_path


def test_round_trip_resolves_default_voice_id_when_unset(tmp_path, repo_root, monkeypatch):
    captured = {}

    def fake_run_voice_round_trip(_conn, **kwargs):
        captured["voice_id"] = kwargs["voice_id"]
        raise speech_cli.VoicePipelineError("stop before real synthesis")

    monkeypatch.setattr(speech_cli, "run_voice_round_trip", fake_run_voice_round_trip)
    monkeypatch.setattr(speech_cli, "db_path", _stub_db_path(tmp_path))

    exit_code = speech_cli.run(
        [
            "round-trip",
            "wake.wav",
            "command.wav",
            "--response-audio-out",
            str(tmp_path / "out.wav"),
        ],
        repo_root,
    )

    assert exit_code == 1
    assert captured["voice_id"] == "bf_isabella"


def test_round_trip_passes_through_explicit_voice_id(tmp_path, repo_root, monkeypatch):
    captured = {}

    def fake_run_voice_round_trip(_conn, **kwargs):
        captured["voice_id"] = kwargs["voice_id"]
        raise speech_cli.VoicePipelineError("stop before real synthesis")

    monkeypatch.setattr(speech_cli, "run_voice_round_trip", fake_run_voice_round_trip)
    monkeypatch.setattr(speech_cli, "db_path", _stub_db_path(tmp_path))

    exit_code = speech_cli.run(
        [
            "round-trip",
            "wake.wav",
            "command.wav",
            "--voice-id",
            "am_michael",
            "--response-audio-out",
            str(tmp_path / "out.wav"),
        ],
        repo_root,
    )

    assert exit_code == 1
    assert captured["voice_id"] == "am_michael"


def test_synthesize_passes_text_and_voice_id_to_tts(tmp_path, repo_root, monkeypatch, capsys):
    import awf.speech.tts_kokoro as tts_kokoro

    captured = {}

    def fake_synthesize(text, voice_id, **kwargs):
        captured.update({"text": text, "voice_id": voice_id, **kwargs})
        return [0.0], 24000

    def fake_write_wav(samples, sample_rate, out_path):
        captured.update({"samples": samples, "sample_rate": sample_rate, "out_path": out_path})

    monkeypatch.setattr(tts_kokoro, "synthesize", fake_synthesize)
    monkeypatch.setattr(tts_kokoro, "write_wav", fake_write_wav)

    exit_code = speech_cli.run(
        [
            "synthesize",
            "hello",
            "--voice-id",
            "am_michael",
            "--response-audio-out",
            str(tmp_path / "out.wav"),
        ],
        repo_root,
    )

    assert exit_code == 0
    assert captured["text"] == "hello"
    assert captured["voice_id"] == "am_michael"
    assert captured["sample_rate"] == 24000
    assert '"response_audio_path"' in capsys.readouterr().out
