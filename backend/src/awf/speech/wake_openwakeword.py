"""Wake-word adapter (Section 16.4): openWakeWord's prebuilt "hey jarvis"
ONNX model. Code is Apache-2.0; the prebuilt model weights are CC-BY-NC-SA
and MUST be fetched by the operator at setup into `models/wake/`, gitignored,
and MUST NOT be redistributed with AWF (Section 16.5's License isolation
rule).

Detection runs entirely locally; the audio never leaves the process.
"""

import wave
from pathlib import Path

import numpy as np

DEFAULT_THRESHOLD = 0.5
CHUNK_SIZE = 1280  # 80ms at 16kHz - openWakeWord's expected frame size


class WakeWordAdapterError(RuntimeError):
    pass


def _read_wav_int16(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as wav_file:
        if wav_file.getframerate() != 16000 or wav_file.getnchannels() != 1 or wav_file.getsampwidth() != 2:
            raise WakeWordAdapterError(
                f"{path}: expected 16kHz mono 16-bit PCM, "
                f"got {wav_file.getframerate()}Hz {wav_file.getnchannels()}ch {wav_file.getsampwidth() * 8}bit"
            )
        raw = wav_file.readframes(wav_file.getnframes())
    return np.frombuffer(raw, dtype=np.int16)


def detect_wake_word(
    audio_path: Path,
    model_path: Path,
    *,
    melspec_model_path: Path,
    embedding_model_path: Path,
    threshold: float = DEFAULT_THRESHOLD,
) -> dict:
    """Returns {"detected": bool, "score": float, "model_key": str}.

    Loads every artifact the wake hardware voice manifest names explicitly, rather
    than falling back to openWakeWord's own bundled package defaults, so
    `awf-speech models sync`/`verify` govern what's actually loaded."""
    from openwakeword.model import Model

    try:
        model = Model(
            wakeword_models=[str(model_path)],
            melspec_model_path=str(melspec_model_path),
            embedding_model_path=str(embedding_model_path),
        )
    except TypeError:
        model = Model(
            wakeword_model_paths=[str(model_path)],
            melspec_onnx_model_path=str(melspec_model_path),
            embedding_onnx_model_path=str(embedding_model_path),
        )
    audio = _read_wav_int16(audio_path)

    max_score = 0.0
    model_key = model_path.stem
    for start in range(0, len(audio) - CHUNK_SIZE + 1, CHUNK_SIZE):
        chunk = audio[start : start + CHUNK_SIZE]
        scores = model.predict(chunk)
        for key, value in scores.items():
            model_key = key
            max_score = max(max_score, float(value))

    return {"detected": max_score >= threshold, "score": max_score, "model_key": model_key}
