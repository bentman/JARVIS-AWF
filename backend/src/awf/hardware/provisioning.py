"""Selects exactly one mutually-exclusive ONNX Runtime distribution to
install, from hardware facts alone (ADR-0008). `onnxruntime`,
`onnxruntime-gpu`, and `onnxruntime-directml` all provide the same
`onnxruntime` import name, so only one may ever be installed; `onnxruntime-qnn`
provides a distinct import name and installs alongside the base package.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from awf.hardware.profiler import HardwareInventory

ORT_EXTRAS = ("hw-ort-cpu", "hw-ort-cuda", "hw-ort-directml", "hw-ort-qnn")


def explain_ort_extra(inventory: "HardwareInventory") -> tuple[str, str]:
    """Returns `(extra, reason)`. First matching condition wins."""
    if inventory.arch == "x64" and inventory.gpu_vendor == "nvidia" and inventory.cuda_available:
        return "hw-ort-cuda", "arch=x64, gpu_vendor=nvidia, cuda_available=true"
    if inventory.os_name == "windows" and inventory.arch == "arm64" and inventory.npu_vendor == "qualcomm":
        return "hw-ort-qnn", "os_name=windows, arch=arm64, npu_vendor=qualcomm"
    if inventory.os_name == "windows" and inventory.gpu_available and inventory.gpu_vendor in ("amd", "intel"):
        return "hw-ort-directml", f"os_name=windows, gpu_available=true, gpu_vendor={inventory.gpu_vendor}"
    return "hw-ort-cpu", "no accelerator condition matched - cpu floor"


def resolve_ort_extra(inventory: "HardwareInventory") -> str:
    extra, _reason = explain_ort_extra(inventory)
    return extra
