import pytest

from awf.hardware.profiler import HardwareInventory
from awf.hardware.provisioning import ORT_EXTRAS, explain_ort_extra, resolve_ort_extra, resolve_required_extras


def _inventory(**overrides) -> HardwareInventory:
    return HardwareInventory(**overrides)


def test_nvidia_x64_selects_cuda():
    inventory = _inventory(arch="x64", gpu_vendor="nvidia", cuda_available=True)
    assert resolve_ort_extra(inventory) == "hw-ort-cuda"


def test_nvidia_without_cuda_available_does_not_select_cuda():
    inventory = _inventory(arch="x64", gpu_vendor="nvidia", cuda_available=False)
    assert resolve_ort_extra(inventory) == "hw-ort-cpu"


def test_nvidia_on_arm64_does_not_select_cuda():
    inventory = _inventory(arch="arm64", gpu_vendor="nvidia", cuda_available=True)
    assert resolve_ort_extra(inventory) == "hw-ort-cpu"


def test_windows_arm64_qualcomm_npu_selects_qnn():
    inventory = _inventory(os_name="windows", arch="arm64", npu_vendor="qualcomm")
    assert resolve_ort_extra(inventory) == "hw-ort-qnn"


def test_linux_arm64_qualcomm_npu_selects_qnn():
    inventory = _inventory(os_name="linux", arch="arm64", npu_vendor="qualcomm")
    assert resolve_ort_extra(inventory) == "hw-ort-qnn"


def test_linux_arm64_without_visible_npu_installs_qnn_candidate():
    inventory = _inventory(os_name="linux", arch="arm64")
    extra, reason = explain_ort_extra(inventory)

    assert extra == "hw-ort-qnn"
    assert reason == "os_name=linux, arch=arm64, qnn_candidate=true"


def test_linux_x64_qualcomm_npu_does_not_select_qnn():
    inventory = _inventory(os_name="linux", arch="x64", npu_vendor="qualcomm")
    assert resolve_ort_extra(inventory) == "hw-ort-cpu"


@pytest.mark.parametrize("gpu_vendor", ["amd", "intel"])
def test_windows_amd_or_intel_gpu_selects_directml(gpu_vendor):
    inventory = _inventory(os_name="windows", gpu_available=True, gpu_vendor=gpu_vendor)
    assert resolve_ort_extra(inventory) == "hw-ort-directml"


def test_linux_amd_gpu_does_not_select_directml():
    inventory = _inventory(os_name="linux", gpu_available=True, gpu_vendor="amd")
    assert resolve_ort_extra(inventory) == "hw-ort-cpu"


def test_no_accelerator_selects_cpu():
    inventory = _inventory()
    assert resolve_ort_extra(inventory) == "hw-ort-cpu"


def test_cuda_condition_wins_over_directml_when_both_present():
    # first-match-wins: a host improbably reporting both an nvidia x64 GPU
    # and a windows/amd fact would still resolve to cuda, not directml.
    inventory = _inventory(os_name="windows", arch="x64", gpu_available=True, gpu_vendor="nvidia", cuda_available=True)
    assert resolve_ort_extra(inventory) == "hw-ort-cuda"


def test_resolve_ort_extra_is_deterministic_for_the_same_inventory():
    inventory = _inventory(arch="x64", gpu_vendor="nvidia", cuda_available=True)
    assert resolve_ort_extra(inventory) == resolve_ort_extra(inventory)


def test_explain_ort_extra_returns_a_nonempty_reason():
    for inventory in (
        _inventory(arch="x64", gpu_vendor="nvidia", cuda_available=True),
        _inventory(os_name="windows", arch="arm64", npu_vendor="qualcomm"),
        _inventory(os_name="linux", arch="arm64", npu_vendor="qualcomm"),
        _inventory(os_name="windows", gpu_available=True, gpu_vendor="amd"),
        _inventory(),
    ):
        extra, reason = explain_ort_extra(inventory)
        assert extra in ORT_EXTRAS
        assert reason


def test_required_extras_add_speech_and_dev_symmetrically():
    inventory = _inventory(os_name="windows", arch="arm64", npu_vendor="qualcomm")

    assert resolve_required_extras(inventory) == ["hw-ort-qnn", "speech", "wake-word", "dev"]


def test_required_extras_add_qnn_speech_and_dev_for_linux_arm64_qualcomm():
    inventory = _inventory(os_name="linux", arch="arm64", npu_vendor="qualcomm")

    assert resolve_required_extras(inventory) == ["hw-ort-qnn", "speech", "wake-word", "dev"]


def test_required_extras_add_qnn_speech_and_dev_for_linux_arm64_candidate():
    inventory = _inventory(os_name="linux", arch="arm64")

    assert resolve_required_extras(inventory) == ["hw-ort-qnn", "speech", "wake-word", "dev"]
