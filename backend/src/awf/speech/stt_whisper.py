"""STT adapter (Section 16.4): Whisper via faster-whisper.

Audio in -> text out. Model files are operator-downloaded into
`models/stt/` (gitignored) at Phase 12 setup, never bundled.
"""

from pathlib import Path


class SttAdapterError(RuntimeError):
    pass


def transcribe(
    audio_path: Path,
    *,
    model_size: str = "small",
    compute_type: str = "int8",
    download_root: Path | None = None,
) -> dict:
    """Returns {"text": str, "language": str, "language_probability": float}."""
    from faster_whisper import WhisperModel

    model = WhisperModel(
        model_size,
        device="cpu",
        compute_type=compute_type,
        download_root=str(download_root) if download_root else None,
    )
    segments, info = model.transcribe(str(audio_path))
    text = " ".join(segment.text.strip() for segment in segments).strip()
    return {
        "text": text,
        "language": info.language,
        "language_probability": info.language_probability,
    }
