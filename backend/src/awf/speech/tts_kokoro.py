"""TTS adapter (Section 16.4, ADR-0008): Kokoro-82M via kokoro-onnx.

Text + voice_id in -> audio out. Model files are operator-downloaded into
`models/tts/` (gitignored) at Phase 12 setup, never bundled.
"""

import wave
from pathlib import Path

import numpy as np

# TTS readiness device -> the ONNX Runtime execution provider it verified.
_DEVICE_TO_PROVIDER = {
    "cuda": "CUDAExecutionProvider",
    "directml": "DmlExecutionProvider",
    "qnn": "QNNExecutionProvider",
}


def synthesize(
    text: str,
    voice_id: str,
    *,
    model_path: Path,
    voices_path: Path,
    device: str = "cpu",
    speed: float = 1.0,
) -> tuple[np.ndarray, int]:
    """Returns (samples: float32 ndarray, sample_rate: int)."""
    import onnxruntime as ort
    from kokoro_onnx import Kokoro

    if device == "cpu":
        session = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
        kokoro = Kokoro.from_session(session, str(voices_path))
    else:
        provider = _DEVICE_TO_PROVIDER[device]
        session = ort.InferenceSession(str(model_path), providers=[provider, "CPUExecutionProvider"])
        kokoro = Kokoro.from_session(session, str(voices_path))

    samples, sample_rate = kokoro.create(text, voice=voice_id, speed=speed)
    return samples, sample_rate


def write_wav(samples: np.ndarray, sample_rate: int, out_path: Path) -> None:
    pcm16 = np.clip(samples * 32767.0, -32768, 32767).astype(np.int16)
    with wave.open(str(out_path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm16.tobytes())
