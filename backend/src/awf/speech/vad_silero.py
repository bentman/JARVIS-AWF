"""VAD adapter (Section 16.4): Silero VAD, MIT-licensed, ONNX, ~2MB.

Used for endpointing and barge-in in the wake-word/push-to-talk -> VAD ->
STT pipeline (Section 16.4). Runs entirely locally via ONNX Runtime.
"""

import wave
from pathlib import Path

import numpy as np
import onnxruntime as ort

SAMPLE_RATE = 16000
CHUNK_SIZE = 512  # Silero VAD's expected window size at 16kHz
DEFAULT_THRESHOLD = 0.5
ENERGY_FALLBACK_THRESHOLD = 0.01


class VadAdapterError(RuntimeError):
    pass


def _read_wav_float32(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as wav_file:
        if wav_file.getframerate() != SAMPLE_RATE or wav_file.getnchannels() != 1 or wav_file.getsampwidth() != 2:
            raise VadAdapterError(
                f"{path}: expected 16kHz mono 16-bit PCM, "
                f"got {wav_file.getframerate()}Hz {wav_file.getnchannels()}ch {wav_file.getsampwidth() * 8}bit"
            )
        raw = wav_file.readframes(wav_file.getnframes())
    samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    return samples


def speech_probabilities(audio_path: Path, model_path: Path) -> list[float]:
    """Per-chunk speech probability across the whole file, in chunk order."""
    session = ort.InferenceSession(str(model_path))
    audio = _read_wav_float32(audio_path)
    input_names = {item.name for item in session.get_inputs()}
    sr = np.array(SAMPLE_RATE, dtype=np.int64)

    probs = []
    if "state" in input_names:
        state = np.zeros((2, 1, 128), dtype=np.float32)
        for start in range(0, len(audio) - CHUNK_SIZE + 1, CHUNK_SIZE):
            chunk = audio[start : start + CHUNK_SIZE].reshape(1, -1)
            output, state = session.run(None, {"input": chunk, "sr": sr, "state": state})
            probs.append(float(output[0][0]))
    else:
        h = np.zeros((2, 1, 64), dtype=np.float32)
        c = np.zeros((2, 1, 64), dtype=np.float32)
        for start in range(0, len(audio) - CHUNK_SIZE + 1, CHUNK_SIZE):
            chunk = audio[start : start + CHUNK_SIZE].reshape(1, -1)
            output, h, c = session.run(None, {"input": chunk, "sr": sr, "h": h, "c": c})
            probs.append(float(output[0][0]))
    return probs


def speech_segments(
    audio_path: Path, model_path: Path, threshold: float = DEFAULT_THRESHOLD
) -> list[tuple[float, float]]:
    """Returns [(start_seconds, end_seconds), ...] for contiguous speech runs."""
    probs = speech_probabilities(audio_path, model_path)
    chunk_seconds = CHUNK_SIZE / SAMPLE_RATE

    segments: list[tuple[float, float]] = []
    in_speech = False
    start = 0.0
    for i, prob in enumerate(probs):
        t = i * chunk_seconds
        if prob >= threshold and not in_speech:
            in_speech = True
            start = t
        elif prob < threshold and in_speech:
            in_speech = False
            segments.append((start, t))
    if in_speech:
        segments.append((start, len(probs) * chunk_seconds))
    if not segments:
        audio = _read_wav_float32(audio_path)
        for start_sample in range(0, len(audio) - CHUNK_SIZE + 1, CHUNK_SIZE):
            chunk = audio[start_sample : start_sample + CHUNK_SIZE]
            rms = float(np.sqrt(np.mean(np.square(chunk)))) if chunk.size else 0.0
            if rms >= ENERGY_FALLBACK_THRESHOLD:
                start_seconds = start_sample / SAMPLE_RATE
                end_seconds = (start_sample + CHUNK_SIZE) / SAMPLE_RATE
                if segments and start_seconds <= segments[-1][1] + chunk_seconds:
                    segments[-1] = (segments[-1][0], end_seconds)
                else:
                    segments.append((start_seconds, end_seconds))
    return segments
