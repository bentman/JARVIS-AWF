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
