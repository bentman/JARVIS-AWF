from pathlib import Path

import onnx
import pytest
from onnx import TensorProto, helper

from awf.hardware.profiler import HardwareInventory
from awf.hardware.readiness import (
    derive_stt_readiness,
    derive_tts_readiness,
    derive_vad_readiness,
    derive_wake_readiness,
)


def _inventory(**overrides) -> HardwareInventory:
    return HardwareInventory(**overrides)


# --- STT -----------------------------------------------------------------


def test_stt_resolves_cuda_when_hardware_fact_and_token_agree():
    inventory = _inventory(gpu_vendor="nvidia", cuda_available=True)
    tokens = ["import:faster_whisper", "ct2:cuda:1"]
    result = derive_stt_readiness(inventory, tokens)
    assert result.device == "cuda"
    assert result.ready is True


def test_stt_floors_to_cpu_when_ct2_reports_zero_devices():
    inventory = _inventory(gpu_vendor="nvidia", cuda_available=True)
    tokens = ["import:faster_whisper", "ct2:cuda:0"]
    result = derive_stt_readiness(inventory, tokens)
    assert result.device == "cpu"


def test_stt_floors_to_cpu_when_hardware_fact_absent():
    inventory = _inventory(gpu_vendor=None, cuda_available=False)
    tokens = ["import:faster_whisper", "ct2:cuda:1"]
    result = derive_stt_readiness(inventory, tokens)
    assert result.device == "cpu"


def test_stt_not_ready_when_faster_whisper_missing():
    inventory = _inventory(gpu_vendor="nvidia", cuda_available=True)
    tokens = ["import:faster_whisper:MISSING", "ct2:cuda:1"]
    result = derive_stt_readiness(inventory, tokens)
    assert result.ready is False
    assert "faster_whisper" in result.reason


# --- TTS -------------------------------------------------------------------


@pytest.mark.parametrize("arch", ["x64", "arm64"])
def test_tts_resolves_cuda_for_nvidia(arch):
    inventory = _inventory(arch=arch, gpu_vendor="nvidia", cuda_available=True)
    tokens = ["import:kokoro_onnx", "ep:CUDAExecutionProvider"]
    result = derive_tts_readiness(inventory, tokens)
    assert result.device == "cuda"
    assert result.ready is True


@pytest.mark.parametrize("gpu_vendor", ["amd", "intel"])
def test_tts_resolves_directml_on_windows(gpu_vendor):
    inventory = _inventory(os_name="windows", gpu_available=True, gpu_vendor=gpu_vendor)
    tokens = ["import:kokoro_onnx", "ep:DmlExecutionProvider"]
    result = derive_tts_readiness(inventory, tokens)
    assert result.device == "directml"
    assert result.ready is True


def test_tts_resolves_qnn_for_qualcomm():
    inventory = _inventory(arch="arm64", npu_vendor="qualcomm", npu_available=True)
    tokens = ["import:kokoro_onnx", "ep:QNNExecutionProvider", "dll:QnnHtp"]
    result = derive_tts_readiness(inventory, tokens)
    assert result.device == "qnn"
    assert result.ready is True


def test_tts_floors_to_cpu_with_no_accelerator():
    inventory = _inventory()
    tokens = ["import:kokoro_onnx"]
    result = derive_tts_readiness(inventory, tokens)
    assert result.device == "cpu"
    assert result.ready is True


def test_tts_floors_to_cpu_when_hardware_fact_present_but_token_missing():
    # gpu_vendor=nvidia but the installed onnxruntime wheel never loaded
    # CUDAExecutionProvider - exactly the case ADR-0008 exists to separate.
    inventory = _inventory(gpu_vendor="nvidia", cuda_available=True)
    tokens = ["import:kokoro_onnx"]
    result = derive_tts_readiness(inventory, tokens)
    assert result.device == "cpu"


def test_tts_floors_to_cpu_when_token_present_but_hardware_fact_missing():
    # ep:CUDAExecutionProvider with no real nvidia GPU never happens in
    # practice, but the rule must still require both sides.
    inventory = _inventory(gpu_vendor=None, cuda_available=False)
    tokens = ["import:kokoro_onnx", "ep:CUDAExecutionProvider"]
    result = derive_tts_readiness(inventory, tokens)
    assert result.device == "cpu"


def test_tts_not_ready_when_kokoro_onnx_missing():
    inventory = _inventory(gpu_vendor="nvidia", cuda_available=True)
    tokens = ["import:kokoro_onnx:MISSING", "ep:CUDAExecutionProvider"]
    result = derive_tts_readiness(inventory, tokens)
    assert result.ready is False
    assert "kokoro_onnx" in result.reason


# --- VAD ---------------------------------------------------------------


def _write_onnx_with_inputs(path: Path, names: list[str]) -> None:
    inputs = [helper.make_tensor_value_info(name, TensorProto.FLOAT, [1]) for name in names]
    node = helper.make_node("Identity", [names[0]], ["y"])
    graph = helper.make_graph(
        [node], "test", inputs, [helper.make_tensor_value_info("y", TensorProto.FLOAT, [1])]
    )
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 17)])
    onnx.save(model, str(path))


def test_vad_ready_when_artifact_input_names_cover_required_set(tmp_path):
    artifact_path = tmp_path / "vad.onnx"
    _write_onnx_with_inputs(artifact_path, ["input", "sr", "h", "c"])
    inventory = _inventory()
    result = derive_vad_readiness(inventory, ["import:onnxruntime"], artifact_path)
    assert result.device == "cpu"
    assert result.ready is True


def test_vad_not_ready_when_input_names_do_not_cover_required_set(tmp_path):
    artifact_path = tmp_path / "vad.onnx"
    _write_onnx_with_inputs(artifact_path, ["wrong_input"])
    inventory = _inventory()
    result = derive_vad_readiness(inventory, ["import:onnxruntime"], artifact_path)
    assert result.ready is False
    assert "wrong_input" in result.reason


def test_vad_not_ready_when_artifact_missing(tmp_path):
    inventory = _inventory()
    result = derive_vad_readiness(inventory, ["import:onnxruntime"], tmp_path / "missing.onnx")
    assert result.ready is False
    assert "missing" in result.reason


def test_vad_not_ready_when_onnxruntime_not_importable(tmp_path):
    inventory = _inventory()
    result = derive_vad_readiness(inventory, ["import:onnxruntime:MISSING"], tmp_path / "missing.onnx")
    assert result.ready is False
    assert "onnxruntime" in result.reason


# --- Wake --------------------------------------------------------------


def test_wake_ready_when_all_artifacts_present(tmp_path):
    paths = {}
    for name in ("hey_jarvis_v0.1.onnx", "melspectrogram.onnx", "embedding_model.onnx"):
        path = tmp_path / name
        path.write_bytes(b"stub")
        paths[name] = path
    inventory = _inventory()
    result = derive_wake_readiness(inventory, ["import:openwakeword"], paths)
    assert result.device == "cpu"
    assert result.ready is True


def test_wake_not_ready_when_an_artifact_is_missing(tmp_path):
    present = tmp_path / "hey_jarvis_v0.1.onnx"
    present.write_bytes(b"stub")
    paths = {
        "hey_jarvis_v0.1.onnx": present,
        "melspectrogram.onnx": tmp_path / "melspectrogram.onnx",
        "embedding_model.onnx": tmp_path / "embedding_model.onnx",
    }
    inventory = _inventory()
    result = derive_wake_readiness(inventory, ["import:openwakeword"], paths)
    assert result.ready is False
    assert "melspectrogram.onnx" in result.reason


def test_wake_not_ready_when_openwakeword_not_importable(tmp_path):
    inventory = _inventory()
    result = derive_wake_readiness(inventory, ["import:openwakeword:MISSING"], {})
    assert result.ready is False
    assert "openwakeword" in result.reason
