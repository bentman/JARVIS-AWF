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
    device: str = "cpu",
    compute_type: str = "int8",
    download_root: Path | None = None,
) -> dict:
    """Returns {"text": str, "language": str, "language_probability": float}.

    `device`/`compute_type` are normally selected by the caller from the
    Hardware Profiler's resolved profile (Section 16.4) rather than hardcoded
    - `cpu`/`int8` remain safe, always-available defaults.
    """
    from faster_whisper import WhisperModel

    model = WhisperModel(
        model_size,
        device=device,
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
