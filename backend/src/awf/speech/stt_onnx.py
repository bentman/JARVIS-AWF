"""ONNX-backed STT adapters for the host-symmetric voice runtime path."""

import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from awf.hardware.preflight import activate_qnn_execution_provider, resolve_qnn_backend_path
from awf.speech.models import SttRuntime, qnn_whisper_available, stt_model_path, stt_runtime
from awf.speech.stt_whisper import transcribe as transcribe_faster_whisper

SAMPLE_RATE = 16000
QNN_PROVIDER = "QNNExecutionProvider"


class SttRuntimeError(RuntimeError):
    pass


@dataclass(frozen=True)
class SttResult:
    text: str
    language: str
    language_probability: float


def _read_wav_float32(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as wav_file:
        if wav_file.getnchannels() != 1 or wav_file.getsampwidth() != 2:
            raise SttRuntimeError(
                f"{path}: expected mono 16-bit PCM, got {wav_file.getnchannels()}ch {wav_file.getsampwidth() * 8}bit"
            )
        sample_rate = wav_file.getframerate()
        raw = wav_file.readframes(wav_file.getnframes())
    samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    return samples, sample_rate


def _providers_for_device(device: str) -> list[str]:
    if device == "cpu":
        return ["CPUExecutionProvider"]
    if device == "cuda":
        return ["CUDAExecutionProvider", "CPUExecutionProvider"]
    if device == "directml":
        return ["DmlExecutionProvider", "CPUExecutionProvider"]
    raise SttRuntimeError(f"unsupported ONNX Whisper STT device '{device}'")


def _create_qnn_session(model_path: Path):
    import onnxruntime as ort

    activation = activate_qnn_execution_provider()
    if not activation.provider_registered:
        raise SttRuntimeError(activation.error or "QNNExecutionProvider is not registered")

    backend_path = resolve_qnn_backend_path()
    provider_options = {}
    if backend_path is not None:
        provider_options["backend_path"] = str(backend_path)
    failures = []

    get_ep_devices = getattr(ort, "get_ep_devices", None)
    if callable(get_ep_devices):
        for ep_device in get_ep_devices():
            if getattr(ep_device, "ep_name", None) != QNN_PROVIDER:
                continue
            try:
                session_options = ort.SessionOptions()
                session_options.add_session_config_entry("session.disable_cpu_ep_fallback", "1")
                session_options.add_provider_for_devices([ep_device], provider_options)
                return ort.InferenceSession(str(model_path), sess_options=session_options)
            except Exception as exc:
                failures.append(f"ep_device failure={exc!r}")

    session_options = ort.SessionOptions()
    session_options.add_session_config_entry("session.disable_cpu_ep_fallback", "1")
    try:
        return ort.InferenceSession(
            str(model_path),
            sess_options=session_options,
            providers=[QNN_PROVIDER],
            provider_options=[provider_options],
        )
    except Exception as exc:
        failures.append(f"provider_list failure={exc!r}")
        raise SttRuntimeError(f"QNN session creation failed for {model_path}: {'; '.join(failures)}") from exc


class OnnxWhisperRuntime:
    def __init__(self, repo_root: Path, runtime: SttRuntime) -> None:
        self.repo_root = repo_root
        self.runtime = runtime
        self.model_path = stt_model_path(repo_root, runtime)
        self._model: Any | None = None

    def _load_model(self):
        if self._model is None:
            import onnx_asr

            self._model = onnx_asr.load_model(
                self.runtime.model,
                path=self.model_path,
                providers=_providers_for_device(self.runtime.device),
            )
        return self._model

    def transcribe(self, audio_path: Path) -> SttResult:
        waveform, sample_rate = _read_wav_float32(audio_path)
        recognized = self._load_model().recognize(waveform, sample_rate=sample_rate)
        text = recognized if isinstance(recognized, str) else str(recognized)
        return SttResult(text=text.strip(), language="en", language_probability=1.0)


class QnnWhisperRuntime:
    def __init__(self, repo_root: Path, runtime: SttRuntime) -> None:
        if runtime.device != "qnn":
            raise SttRuntimeError(f"QNN Whisper requires device='qnn', got '{runtime.device}'")
        self.repo_root = repo_root
        self.runtime = runtime
        self.model_path = stt_model_path(repo_root, runtime)
        self._encoder_session: Any | None = None
        self._decoder_session: Any | None = None
        self._feature_extractor: Any | None = None
        self._tokenizer: Any | None = None
        self._whisper_config: Any | None = None

    def is_available(self) -> bool:
        return qnn_whisper_available(self.repo_root, self.runtime)

    def _ensure_preprocessors(self) -> None:
        if self._feature_extractor is None or self._tokenizer is None or self._whisper_config is None:
            from transformers import WhisperConfig, WhisperFeatureExtractor, WhisperTokenizer

            self._feature_extractor = WhisperFeatureExtractor.from_pretrained("openai/whisper-base")
            self._tokenizer = WhisperTokenizer.from_pretrained("openai/whisper-base")
            self._whisper_config = WhisperConfig.from_pretrained("openai/whisper-base")
            self._whisper_config.return_dict = False
            self._whisper_config.tie_word_embeddings = False
            self._whisper_config.mask_neg = -100.0

    def _load_encoder_session(self):
        if self._encoder_session is None:
            self._encoder_session = _create_qnn_session(self.model_path / "encoder" / "model.onnx")
        return self._encoder_session

    def _load_decoder_session(self):
        if self._decoder_session is None:
            self._decoder_session = _create_qnn_session(self.model_path / "decoder" / "model.onnx")
        return self._decoder_session

    def transcribe(self, audio_path: Path) -> SttResult:
        if not self.is_available():
            raise SttRuntimeError(f"QNN STT model files are unavailable at {self.model_path}")
        self._ensure_preprocessors()
        encoder = self._load_encoder_session()
        decoder = self._load_decoder_session()
        if encoder.get_providers()[0] != QNN_PROVIDER or decoder.get_providers()[0] != QNN_PROVIDER:
            raise SttRuntimeError("QNNExecutionProvider not primary; CPU fallback detected")

        waveform, sample_rate = _read_wav_float32(audio_path)
        audio_rms = float(np.sqrt(np.mean(np.square(waveform)))) if waveform.size else 0.0
        audio_peak = float(np.max(np.abs(waveform))) if waveform.size else 0.0
        features = self._feature_extractor(waveform, sampling_rate=sample_rate, return_tensors="np").input_features
        features = np.asarray(features, dtype=np.float16)

        encoder_outputs = encoder.get_outputs()
        encoder_values = encoder.run(None, {encoder.get_inputs()[0].name: features})
        encoder_map = {output.name: value for output, value in zip(encoder_outputs, encoder_values, strict=False)}
        decoder_inputs = {item.name: item for item in decoder.get_inputs()}
        decoder_outputs = {item.name: item for item in decoder.get_outputs()}
        if "attention_mask" not in decoder_inputs:
            raise SttRuntimeError("QNN Whisper decoder is missing required attention_mask input")

        attention_shape = [
            1 if dim is None or isinstance(dim, str) else int(dim) for dim in decoder_inputs["attention_mask"].shape
        ]
        if len(attention_shape) != 4 or attention_shape[-1] < 2:
            raise SttRuntimeError(f"unsupported QNN Whisper attention_mask shape {attention_shape}")

        mean_decode_len = int(attention_shape[-1])
        max_decode_steps = mean_decode_len - 1
        mask_neg = float(getattr(self._whisper_config, "mask_neg", -100.0))
        token_ids = [int(self._whisper_config.decoder_start_token_id)]
        eot_token = int(self._whisper_config.eos_token_id)
        cache_state: dict[str, np.ndarray] = {}

        def _norm_tokens(name: str) -> list[str]:
            return [part for part in name.replace("_in", "").replace("_out", "").split("_") if part]

        self_cache_inputs = [name for name in decoder_inputs if "cache_self" in name]
        self_cache_outputs = [name for name in decoder_outputs if "cache_self" in name]
        output_token_sets = {name: set(_norm_tokens(name)) for name in self_cache_outputs}
        self_cache_pairs = {}
        for input_name in self_cache_inputs:
            input_tokens = set(_norm_tokens(input_name))
            candidates = [name for name in self_cache_outputs if input_tokens.issubset(output_token_sets[name])]
            if not candidates:
                raise SttRuntimeError(f"unable to map decoder self-cache input '{input_name}' to output")
            candidates.sort(key=lambda name: len(output_token_sets[name]))
            self_cache_pairs[input_name] = candidates[0]

        def _layer_idx(name: str) -> str | None:
            parts = name.split("_")
            for index, part in enumerate(parts):
                if part == "cross" and index + 1 < len(parts):
                    return parts[index + 1]
            return None

        def _kv_kind(name: str) -> str:
            tokens = set(_norm_tokens(name))
            if "key" in tokens or ("k" in tokens and "cache" in tokens):
                return "k"
            if "value" in tokens or "v" in tokens:
                return "v"
            return ""

        cross_inputs = [name for name in decoder_inputs if "cross" in name]
        cross_outputs = [name for name in encoder_map if "cross" in name]
        cross_cache_pairs = {}
        for input_name in cross_inputs:
            candidates = [
                name
                for name in cross_outputs
                if _layer_idx(name) == _layer_idx(input_name) and _kv_kind(name) == _kv_kind(input_name)
            ]
            if not candidates:
                raise SttRuntimeError(f"unmatched decoder cross-cache input '{input_name}'")
            cross_cache_pairs[input_name] = sorted(candidates)[0]

        attention_dtype = np.float32 if decoder_inputs["attention_mask"].type == "tensor(float)" else np.float16
        attention_mask = np.full(attention_shape, mask_neg, dtype=attention_dtype)
        position_id = 0
        for step_idx in range(max_decode_steps):
            attention_mask[:, :, :, mean_decode_len - step_idx - 1] = 0.0
            feed: dict[str, np.ndarray] = {}
            for name, input_def in decoder_inputs.items():
                if name == "input_ids":
                    feed[name] = np.array([[token_ids[step_idx]]], dtype=np.int32)
                elif name == "attention_mask":
                    dtype = np.int32 if input_def.type == "tensor(int32)" else attention_dtype
                    feed[name] = attention_mask.astype(dtype, copy=False)
                elif name == "position_ids":
                    feed[name] = np.array([position_id], dtype=np.int32)
                elif name in cache_state:
                    feed[name] = cache_state[name]
                elif name in cross_cache_pairs:
                    feed[name] = np.asarray(encoder_map[cross_cache_pairs[name]], dtype=np.float16)
                elif "cross" in name:
                    raise SttRuntimeError(f"unmapped decoder cross-cache input '{name}'")
                else:
                    shape = [1 if dim is None or isinstance(dim, str) else int(dim) for dim in (input_def.shape or [])]
                    dtype = np.int32 if input_def.type == "tensor(int32)" else np.float16
                    feed[name] = np.zeros(shape, dtype=dtype)

            decoder_values = decoder.run(None, feed)
            decoder_map = {name: value for name, value in zip(decoder_outputs.keys(), decoder_values, strict=False)}
            logits_name = next(name for name in decoder_map if "logits" in name)
            logits = np.asarray(decoder_map[logits_name])
            next_token = int(np.argmax(logits[:, :, 0, 0], axis=1)[0])
            token_ids.append(next_token)
            for input_name, output_name in self_cache_pairs.items():
                cache_state[input_name] = np.asarray(decoder_map[output_name])
            if next_token == eot_token:
                break
            position_id += 1

        text = self._tokenizer.decode(token_ids, skip_special_tokens=True).strip()
        if not text and audio_peak > 1e-4 and audio_rms > 1e-5:
            raise SttRuntimeError("QNN STT returned empty transcript for non-silent audio")
        return SttResult(text=text, language="en", language_probability=1.0)


def transcribe(audio_path: Path, *, repo_root: Path, runtime: SttRuntime) -> dict:
    if runtime.runtime == "faster_whisper":
        return transcribe_faster_whisper(
            audio_path,
            model_size=runtime.model,
            device=runtime.device,
            compute_type=runtime.compute_type,
            download_root=stt_model_path(repo_root, runtime).parent,
        )
    if runtime.runtime == "qnn_whisper":
        qnn_runtime = QnnWhisperRuntime(repo_root, runtime)
        if qnn_runtime.is_available():
            result = qnn_runtime.transcribe(audio_path)
        else:
            result = OnnxWhisperRuntime(repo_root, stt_runtime(repo_root, "cpu")).transcribe(audio_path)
    elif runtime.runtime == "onnx_whisper":
        result = OnnxWhisperRuntime(repo_root, runtime).transcribe(audio_path)
    else:
        raise SttRuntimeError(f"unsupported STT runtime '{runtime.runtime}'")
    return {
        "text": result.text,
        "language": result.language,
        "language_probability": result.language_probability,
    }
