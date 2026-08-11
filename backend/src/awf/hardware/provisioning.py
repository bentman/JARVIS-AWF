"""Select host-symmetric dependency extras from hardware facts (ADR-0008).

`onnxruntime`, `onnxruntime-gpu`, and `onnxruntime-directml` all provide the
same `onnxruntime` import name, so only one may ever be installed;
`onnxruntime-qnn` provides a distinct import name and installs alongside the
base package. Speech/runtime extras are selected through the same mechanism on
every host class so ARM64 does not need a one-off bootstrap path.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from awf.hardware.profiler import HardwareInventory

ORT_EXTRAS = ("hw-ort-cpu", "hw-ort-cuda", "hw-ort-directml", "hw-ort-qnn")


def resolve_required_extras(inventory: "HardwareInventory", *, include_speech: bool = True, include_dev: bool = True) -> list[str]:
    extras = [resolve_ort_extra(inventory)]
    if include_speech:
        extras.append("speech")
        extras.append("wake-word")
    if include_dev:
        extras.append("dev")
    return extras


def explain_ort_extra(inventory: "HardwareInventory") -> tuple[str, str]:
    """Returns `(extra, reason)`. First matching condition wins."""
    if inventory.arch == "x64" and inventory.gpu_vendor == "nvidia" and inventory.cuda_available:
        return "hw-ort-cuda", "arch=x64, gpu_vendor=nvidia, cuda_available=true"
    if inventory.os_name in ("windows", "linux") and inventory.arch == "arm64" and inventory.npu_vendor == "qualcomm":
        return "hw-ort-qnn", f"os_name={inventory.os_name}, arch=arm64, npu_vendor=qualcomm"
    if inventory.os_name == "windows" and inventory.gpu_available and inventory.gpu_vendor in ("amd", "intel"):
        return "hw-ort-directml", f"os_name=windows, gpu_available=true, gpu_vendor={inventory.gpu_vendor}"
    return "hw-ort-cpu", "no accelerator condition matched - cpu floor"


def resolve_ort_extra(inventory: "HardwareInventory") -> str:
    extra, _reason = explain_ort_extra(inventory)
    return extra
