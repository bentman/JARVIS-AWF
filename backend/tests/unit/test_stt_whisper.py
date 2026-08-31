from types import SimpleNamespace

from awf.speech import stt_whisper


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
