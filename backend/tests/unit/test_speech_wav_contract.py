"""The audio format contract between the GUI recorder and the STT adapters.

`awf.speech.stt_onnx._read_wav_float32` opens transcription input with
Python's `wave` module and rejects anything that is not mono 16-bit PCM.
The GUI's `frontend/gui/src/renderer/wav.ts` re-encodes its recording to
exactly that before handing it to `awf-speech transcribe`. These tests pin
the receiving half of that contract, which mocked-subprocess tests on
either side cannot reach.
"""

import struct
import wave

import numpy as np
import pytest

from awf.speech.stt_onnx import SttRuntimeError, _read_wav_float32


def _write_pcm16_wav(path, samples, sample_rate=16000, channels=1, sampwidth=2):
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(sampwidth)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(b"".join(struct.pack("<h", value) for value in samples))


def test_reads_mono_16bit_pcm_written_the_way_the_renderer_encodes_it(tmp_path):
    path = tmp_path / "clip.wav"
    _write_pcm16_wav(path, [0, 32767, -32768, 16384])

    samples, sample_rate = _read_wav_float32(path)

    assert sample_rate == 16000
    assert samples.dtype == np.float32
    assert len(samples) == 4
    assert samples[0] == pytest.approx(0.0)
    assert samples[1] == pytest.approx(1.0, abs=1e-4)
    assert samples[2] == pytest.approx(-1.0)
    assert samples[3] == pytest.approx(0.5, abs=1e-4)


def test_rejects_stereo(tmp_path):
    path = tmp_path / "stereo.wav"
    _write_pcm16_wav(path, [0, 0, 1, 1], channels=2)

    with pytest.raises(SttRuntimeError, match="expected mono 16-bit PCM"):
        _read_wav_float32(path)


def test_rejects_non_16bit_sample_width(tmp_path):
    path = tmp_path / "eightbit.wav"
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(1)
        wav_file.setframerate(16000)
        wav_file.writeframes(bytes([128, 129, 130]))

    with pytest.raises(SttRuntimeError, match="expected mono 16-bit PCM"):
        _read_wav_float32(path)


def test_rejects_a_non_wav_container_written_to_a_wav_filename(tmp_path):
    """A MediaRecorder blob written straight to a `.wav` path is still WebM.

    This is the failure the renderer's re-encode exists to prevent: the
    extension does not change the container, and `wave` cannot open it.
    """
    path = tmp_path / "recording.wav"
    path.write_bytes(b"\x1a\x45\xdf\xa3" + b"\x00" * 64)  # EBML/WebM magic

    with pytest.raises(wave.Error):
        _read_wav_float32(path)
