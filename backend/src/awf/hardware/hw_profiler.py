"""Hardware Profiler, evidence-rich variant (Section 16.4).

Resolves the host to exactly one canonical profile ID, with the same public
contract as `awf.hardware.profiler` - `CANONICAL_PROFILES`, `SYSTEM_RUN_ID`,
`_detect_os`, `_detect_arch`, `_probe_evidence(arch)`,
`resolve_hardware_profile_id() -> (profile_id, evidence)`, and
`run_hardware_profiler(conn) -> profile_id` writing one
`hardware_profile_resolved` event whose payload carries `profile_id` - so
this module is a drop-in import swap for existing callers
(`speech/pipeline.py`, `workflow/activities.py`).

What it adds over the existing module, all of it probe-derived, never
assumed:

- A full host **inventory** (OS/device class, CPU, memory, GPU vendor/VRAM,
  CUDA driver, NPU vendor), each detector independently fault-isolated, and
  a content-addressed `inventory_id` over the inventory's own fields so two
  identical hosts hash identically and a changed host is visible as a
  changed digest. The inventory is recorded as event evidence; it never
  decides the profile on its own.
- **QNN provider activation** before the QNN probe. On a real Snapdragon
  host `QNNExecutionProvider` is frequently absent from
  `get_available_providers()` until its provider library is registered and
  its DLL directory is added; probing availability alone reports a false
  negative and silently drops the host to its CPU floor.
- **Per-platform GPU execution-provider candidates** (DirectML on Windows,
  ROCm/MIGraphX/OpenVINO on Linux x64) instead of one fixed provider name,
  plus, on arm64, a direct OpenCL platform probe for the Adreno path that
  Section 16.4 names but that ONNX Runtime exposes no execution provider
  for.
- **Timeouts on every external command**, so a hung `powershell`/`nvidia-smi`
  cannot stall a Run (this module is reachable mid-Run through the
  `hardware_probe` activity, not only at voice setup).
- A **process-lifetime inventory cache**, since the Windows CIM/PnP queries
  cost real seconds and this runs on every voice round trip. Provider
  verification is not cached - it is the part that decides the profile.

Identifier note: `profile_id` here always means the canonical Section 16.4
enum value (e.g. `windows-arm64-qnn`). The reference system's own
content-hash profile identity is carried separately as `inventory_id`
(`inv-<16 hex>`), so the two vocabularies never collide.

Vocabulary note: architecture is normalized to this repo's `x64`/`arm64`
(the canonical profile enum's own spelling), not the reference system's
`amd64`.

Deliberately self-contained: it shares no imports with
`awf.hardware.profiler`, so whichever module ends up superseding the other
can be deleted without leaving a backwards dependency. While both exist the
canonical constants are duplicated - a real DRY cost, and the reason this
duplication should not outlive the choice of which module ships.
"""

import ctypes
import hashlib
import importlib
import json
import os
import platform
import sqlite3
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path

from awf.clock import utc_now_rfc3339
from awf.events.writer import write_event

CANONICAL_PROFILES = (
    "windows-x64-cpu",
    "windows-x64-gpu",
    "windows-x64-cuda",
    "windows-arm64-cpu",
    "windows-arm64-gpu",
    "windows-arm64-qnn",
    "linux-x64-cpu",
    "linux-x64-gpu",
    "linux-x64-cuda",
    "linux-arm64-cpu",
    "linux-arm64-gpu",
    "linux-arm64-qnn",
)

SYSTEM_RUN_ID = "system"
SYSTEM_WORKFLOW_REF = "system@0.0.0"

COMMAND_TIMEOUT_SECONDS = 10

# ONNX Runtime execution providers that count as a probe-verified,
# non-CUDA GPU path per platform (Section 16.4: on x64 `-gpu` is DirectML on
# Windows / the vendor GPU EP on Linux). Ordered - the first that genuinely
# initializes wins and is recorded by name in the evidence.
GPU_PROVIDER_CANDIDATES = {
    ("windows", "x64"): ("DmlExecutionProvider",),
    ("linux", "x64"): ("ROCMExecutionProvider", "MIGraphXExecutionProvider", "OpenVINOExecutionProvider"),
    ("windows", "arm64"): ("DmlExecutionProvider",),
    ("linux", "arm64"): (),
}

# Chassis types the SMBIOS spec assigns to portable enclosures.
_LAPTOP_CHASSIS_TYPES = {8, 9, 10, 11, 12, 14, 18, 21, 30, 31, 32}

_QNN_PROVIDER = "QNNExecutionProvider"
_CUDA_PROVIDER = "CUDAExecutionProvider"

# Registered DLL directory handles must outlive the call that added them.
_DLL_DIRECTORY_HANDLES: list[object] = []
_INVENTORY_CACHE: "HardwareInventory | None" = None


class HardwareProfilerError(RuntimeError):
    pass


@dataclass(frozen=True)
class HardwareInventory:
    """Descriptive host facts. Informational evidence only - the canonical
    profile ID is decided by execution-provider verification, never by these
    fields, so a detector that comes back empty degrades the record's detail
    and nothing else."""

    os_name: str = "unknown"
    os_version: str = "unknown"
    device_class: str = "unknown"
    arch: str = "unknown"
    cpu_name: str = "unknown"
    cpu_physical_cores: int | None = None
    cpu_logical_cores: int | None = None
    cpu_max_freq_mhz: float | None = None
    memory_total_gb: float | None = None
    memory_available_gb: float | None = None
    memory_source: str | None = None
    gpu_available: bool = False
    gpu_name: str | None = None
    gpu_vendor: str | None = None
    gpu_vram_gb: float | None = None
    gpu_vram_source: str | None = None
    cuda_available: bool = False
    cuda_version: str | None = None
    npu_available: bool = False
    npu_vendor: str | None = None
    detector_errors: dict[str, str] = field(default_factory=dict)
    inventory_id: str = "unknown"
    profiled_at: str = "unknown"


@dataclass(frozen=True)
class QnnActivation:
    provider_registered: bool
    provider_library_path: str | None = None
    dll_directory_path: str | None = None
    backend_path: str | None = None
    error: str | None = None


def _run_command(command: list[str], timeout: int = COMMAND_TIMEOUT_SECONDS) -> str:
    """Best-effort command probe: any failure, including a missing binary or
    a hang, is an empty result - never an exception reaching a Run."""
    try:
        completed = subprocess.run(command, capture_output=True, text=True, check=False, timeout=timeout)
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        return ""
    if completed.returncode != 0:
        return ""
    return (completed.stdout or completed.stderr or "").strip()


def _powershell(script: str, timeout: int = COMMAND_TIMEOUT_SECONDS) -> str:
    if platform.system() != "Windows":
        return ""
    return _run_command(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], timeout=timeout)


def _load_optional(module_name: str):
    try:
        return importlib.import_module(module_name)
    except Exception:
        return None


def _normalize_gpu_vendor(text: str) -> str | None:
    lower = text.lower()
    if "nvidia" in lower:
        return "nvidia"
    if "qualcomm" in lower or "adreno" in lower or "snapdragon" in lower:
        return "qualcomm"
    if "amd" in lower or "radeon" in lower or "rocm" in lower:
        return "amd"
    if "intel" in lower or "arc" in lower or "xpu" in lower:
        return "intel"
    return None


def _normalize_arch(machine: str | None) -> str:
    value = (machine or "").strip().lower()
    if value in ("amd64", "x86_64", "x64"):
        return "x64"
    if value in ("arm64", "aarch64"):
        return "arm64"
    return "unknown"


def _detect_os() -> str:
    system = platform.system()
    if system == "Windows":
        return "windows"
    if system == "Linux":
        return "linux"  # WSL2 reports "Linux" here - resolves as Linux, per spec
    raise HardwareProfilerError(f"unsupported OS for the canonical profile enum: {system}")


def _detect_arch() -> str:
    arch = _normalize_arch(platform.machine())
    if arch == "unknown":
        raise HardwareProfilerError(
            f"unsupported architecture for the canonical profile enum: {platform.machine()}"
        )
    return arch


def _detect_device_class(os_name: str) -> str:
    psutil = _load_optional("psutil")
    if psutil is not None:
        try:
            if psutil.sensors_battery() is not None:
                return "laptop"
        except Exception:
            pass

    if os_name == "windows":
        output = _powershell(
            "(Get-CimInstance Win32_SystemEnclosure | "
            "Select-Object -ExpandProperty ChassisTypes) -join ','"
        )
        chassis_types = {
            int(part.strip())
            for part in output.replace("[", "").replace("]", "").split(",")
            if part.strip().isdigit()
        }
        if chassis_types & _LAPTOP_CHASSIS_TYPES:
            return "laptop"
        if chassis_types:
            return "desktop"
        return "unknown"

    try:
        chassis_text = Path("/sys/class/dmi/id/chassis_type").read_text(encoding="utf-8").strip()
    except OSError:
        return "unknown"
    if not chassis_text.isdigit():
        return "unknown"
    return "laptop" if int(chassis_text) in _LAPTOP_CHASSIS_TYPES else "desktop"


def detect_os_info() -> dict:
    system = (platform.system() or "unknown").strip().lower()
    os_name = system if system in ("windows", "linux", "darwin") else "unknown"
    return {
        "os_name": os_name,
        "os_version": (platform.version() or platform.release() or "unknown").strip() or "unknown",
        "device_class": _detect_device_class(os_name),
    }


def detect_cpu_info() -> dict:
    psutil = _load_optional("psutil")
    physical = logical = None
    max_freq = None
    if psutil is not None:
        try:
            physical = psutil.cpu_count(logical=False)
            logical = psutil.cpu_count(logical=True)
            freq = psutil.cpu_freq()
            max_freq = round(freq.max, 2) if freq and freq.max else None
        except Exception:
            physical = logical = None
    if logical is None:
        # Stdlib floor - psutil is optional here, never a hard dependency.
        logical = os.cpu_count()
    return {
        "cpu_name": (platform.processor() or platform.machine() or "unknown").strip() or "unknown",
        "cpu_physical_cores": physical,
        "cpu_logical_cores": logical,
        "cpu_max_freq_mhz": max_freq,
        "arch": _normalize_arch(platform.machine()),
    }


class _MemoryStatusEx(ctypes.Structure):
    _fields_ = [
        ("dwLength", ctypes.c_ulong),
        ("dwMemoryLoad", ctypes.c_ulong),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


def _bytes_to_gb(value: int | float | None) -> float | None:
    if value is None:
        return None
    return round(float(value) / (1024**3), 2)


def _memory_from_proc_meminfo() -> tuple[float | None, float | None]:
    try:
        lines = Path("/proc/meminfo").read_text(encoding="utf-8").splitlines()
    except OSError:
        return None, None
    values: dict[str, int] = {}
    for line in lines:
        key, _, rest = line.partition(":")
        parts = rest.split()
        if parts and parts[0].isdigit():
            values[key.strip()] = int(parts[0]) * 1024  # kB -> bytes
    return _bytes_to_gb(values.get("MemTotal")), _bytes_to_gb(values.get("MemAvailable"))


def _memory_from_win32() -> tuple[float | None, float | None]:
    try:
        status = _MemoryStatusEx()
        status.dwLength = ctypes.sizeof(_MemoryStatusEx)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):  # type: ignore[attr-defined]
            return None, None
    except (AttributeError, OSError):
        return None, None
    return _bytes_to_gb(status.ullTotalPhys), _bytes_to_gb(status.ullAvailPhys)


def detect_memory_info() -> dict:
    psutil = _load_optional("psutil")
    if psutil is not None:
        try:
            memory = psutil.virtual_memory()
            return {
                "memory_total_gb": _bytes_to_gb(getattr(memory, "total", None)),
                "memory_available_gb": _bytes_to_gb(getattr(memory, "available", None)),
                "memory_source": "psutil",
            }
        except Exception:
            pass

    if platform.system() == "Windows":
        total, available = _memory_from_win32()
        source = "kernel32.GlobalMemoryStatusEx"
    else:
        total, available = _memory_from_proc_meminfo()
        source = "/proc/meminfo"
    return {
        "memory_total_gb": total,
        "memory_available_gb": available,
        "memory_source": source if total is not None else None,
    }


def _parse_mebibytes(value: str) -> float | None:
    try:
        return round(float(value.strip()) / 1024.0, 2)
    except ValueError:
        return None


def _gpu_from_cli(command: list[str], vendor_hint: str, source: str) -> dict | None:
    output = _run_command(command)
    if not output:
        return None
    first_line = output.splitlines()[0].strip()
    parts = [part.strip() for part in first_line.split(",") if part.strip()]
    name = parts[0] if parts else vendor_hint.title()
    return {
        "gpu_available": True,
        "gpu_name": name,
        "gpu_vendor": _normalize_gpu_vendor(output) or vendor_hint,
        "gpu_vram_gb": _parse_mebibytes(parts[1]) if len(parts) > 1 else None,
        "gpu_vram_source": source,
    }


def _gpu_from_windows_cim() -> dict | None:
    output = _powershell(
        "Get-CimInstance Win32_VideoController | "
        "Select-Object Name,AdapterRAM | ConvertTo-Json -Compress"
    )
    if not output:
        return None
    try:
        payload = json.loads(output)
    except json.JSONDecodeError:
        return None
    items = [payload] if isinstance(payload, dict) else payload if isinstance(payload, list) else []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("Name") or "").strip()
        if not name:
            continue
        adapter_ram = item.get("AdapterRAM")
        # AdapterRAM is a signed 32-bit field and misreports anything over
        # 4GB - recorded with its source so a consumer can weigh it, never
        # silently trusted as exact.
        vram_gb = _bytes_to_gb(adapter_ram) if isinstance(adapter_ram, (int, float)) else None
        return {
            "gpu_available": True,
            "gpu_name": name,
            "gpu_vendor": _normalize_gpu_vendor(name) or "unknown",
            "gpu_vram_gb": vram_gb,
            "gpu_vram_source": "windows-cim",
        }
    return None


def _gpu_from_linux_sysfs() -> dict | None:
    drm_root = Path("/sys/class/drm")
    try:
        cards = sorted(p for p in drm_root.glob("card[0-9]*") if (p / "device/vendor").is_file())
    except OSError:
        return None
    pci_vendors = {"0x10de": "nvidia", "0x1002": "amd", "0x8086": "intel", "0x5143": "qualcomm"}
    for card in cards:
        try:
            vendor_id = (card / "device/vendor").read_text(encoding="utf-8").strip().lower()
        except OSError:
            continue
        vendor = pci_vendors.get(vendor_id)
        if vendor is None:
            continue
        return {
            "gpu_available": True,
            "gpu_name": f"{vendor} ({vendor_id})",
            "gpu_vendor": vendor,
            "gpu_vram_gb": None,
            "gpu_vram_source": "linux-sysfs-drm",
        }
    return None


def detect_gpu_info() -> dict:
    probes = (
        (["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"], "nvidia", "nvidia-smi"),
        (["rocm-smi", "--showproductname"], "amd", "rocm-smi"),
        (["xpu-smi", "discovery"], "intel", "xpu-smi"),
    )
    for command, vendor_hint, source in probes:
        result = _gpu_from_cli(command, vendor_hint, source)
        if result is not None:
            return result

    result = _gpu_from_windows_cim() if platform.system() == "Windows" else _gpu_from_linux_sysfs()
    if result is not None:
        return result

    return {
        "gpu_available": False,
        "gpu_name": None,
        "gpu_vendor": None,
        "gpu_vram_gb": None,
        "gpu_vram_source": None,
    }


def detect_cuda_info() -> dict:
    driver = _run_command(["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"])
    if driver:
        return {"cuda_available": True, "cuda_version": driver.splitlines()[0].strip() or None}

    nvcc = _run_command(["nvcc", "--version"])
    if nvcc:
        release_line = next((line.strip() for line in nvcc.splitlines() if "release" in line.lower()), None)
        return {"cuda_available": True, "cuda_version": release_line}

    return {"cuda_available": False, "cuda_version": None}


def detect_npu_info() -> dict:
    """NPU presence, descriptive only. A vendor match here never grants a
    `-qnn` profile on its own; only a verified `QNNExecutionProvider` does.

    Matching is deliberately narrow: an unfiltered device-name sweep matches
    'Intel' on every Intel host and would report an NPU that isn't there.
    """
    processor = (platform.processor() or "").strip().lower()
    machine = _normalize_arch(platform.machine())

    npu_names = _powershell(
        "Get-CimInstance Win32_PnPEntity | "
        "Where-Object { $_.Name -match 'Neural|NPU|Hexagon|AI Boost|AI Accelerator' } | "
        "Select-Object -ExpandProperty Name"
    )
    haystack = f"{processor} {npu_names}".lower()

    if any(token in haystack for token in ("qualcomm", "hexagon", "snapdragon", "qcom")):
        return {"npu_available": True, "npu_vendor": "qualcomm"}
    if npu_names:
        if "intel" in haystack or "ai boost" in haystack:
            return {"npu_available": True, "npu_vendor": "intel"}
        if "amd" in haystack or "xdna" in haystack or "ryzen" in haystack:
            return {"npu_available": True, "npu_vendor": "amd"}
        return {"npu_available": True, "npu_vendor": None}
    if machine == "arm64" and platform.system() == "Darwin":
        return {"npu_available": True, "npu_vendor": "apple"}
    return {"npu_available": False, "npu_vendor": None}


def _inventory_id(fields: dict) -> str:
    canonical = {k: v for k, v in fields.items() if k not in ("inventory_id", "profiled_at", "detector_errors")}
    payload = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return f"inv-{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:16]}"


def collect_inventory(*, refresh: bool = False) -> HardwareInventory:
    """Run every detector, fault-isolated, into one inventory record.

    Cached for the process lifetime by default: the Windows CIM/PnP queries
    cost real seconds and this is reached on every voice round trip. Pass
    `refresh=True` (or call `reset_inventory_cache()`) when the host may have
    changed underneath a long-lived process.
    """
    global _INVENTORY_CACHE
    if _INVENTORY_CACHE is not None and not refresh:
        return _INVENTORY_CACHE

    merged: dict = {}
    errors: dict[str, str] = {}
    detectors = (
        ("os", detect_os_info),
        ("cpu", detect_cpu_info),
        ("memory", detect_memory_info),
        ("gpu", detect_gpu_info),
        ("cuda", detect_cuda_info),
        ("npu", detect_npu_info),
    )
    known_fields = set(HardwareInventory.__dataclass_fields__)
    for name, detector in detectors:
        try:
            payload = detector()
        except Exception as exc:  # a detector failing must not fail the profiler
            errors[name] = f"{type(exc).__name__}: {exc}"
            continue
        if isinstance(payload, dict):
            merged.update({k: v for k, v in payload.items() if k in known_fields})

    inventory = HardwareInventory(
        **merged,
        detector_errors=errors,
        inventory_id=_inventory_id(merged),
        profiled_at=utc_now_rfc3339(),
    )
    _INVENTORY_CACHE = inventory
    return inventory


def reset_inventory_cache() -> None:
    global _INVENTORY_CACHE
    _INVENTORY_CACHE = None


def _available_providers() -> list[str]:
    ort = _load_optional("onnxruntime")
    if ort is None:
        return []
    try:
        return list(ort.get_available_providers())
    except Exception:
        return []


def _verify_provider_loads(provider: str, provider_options: dict | None = None) -> bool:
    """Probe-verify (not just list) that an ONNX Runtime execution provider
    actually loads, by constructing a session that requests it."""
    ort = _load_optional("onnxruntime")
    if ort is None or provider not in _available_providers():
        return False

    onnx_helper = _load_optional("onnx.helper")
    onnx_module = _load_optional("onnx")
    if onnx_helper is None or onnx_module is None:
        return False

    # A minimal valid ONNX model (single Identity node) - enough to prove the
    # provider genuinely initializes, not just that its package exists.
    try:
        float_type = onnx_module.TensorProto.FLOAT
        node = onnx_helper.make_node("Identity", ["x"], ["y"])
        graph = onnx_helper.make_graph(
            [node],
            "probe",
            [onnx_helper.make_tensor_value_info("x", float_type, [1])],
            [onnx_helper.make_tensor_value_info("y", float_type, [1])],
        )
        model = onnx_helper.make_model(graph)
        if provider_options:
            session = ort.InferenceSession(
                model.SerializeToString(), providers=[provider], provider_options=[provider_options]
            )
        else:
            session = ort.InferenceSession(model.SerializeToString(), providers=[provider])
        return provider in session.get_providers()
    except Exception:
        return False


def _qnn_package_root(module) -> Path | None:
    lib_dir = getattr(module, "LIB_DIR_FULL_PATH", None)
    if lib_dir:
        return Path(lib_dir).resolve()
    module_file = getattr(module, "__file__", None)
    return Path(module_file).resolve().parent if module_file else None


def _qnn_provider_library_path(module) -> Path | None:
    get_library_path = getattr(module, "get_library_path", None)
    if callable(get_library_path):
        try:
            candidate = Path(get_library_path()).resolve()
            if candidate.is_file():
                return candidate
        except Exception:
            pass
    root = _qnn_package_root(module)
    if root is None:
        return None
    candidate = root / "onnxruntime_providers_qnn.dll"
    return candidate if candidate.is_file() else None


def resolve_qnn_backend_path() -> Path | None:
    """Locate `QnnHtp.dll` - the QNN backend library the provider needs as an
    explicit option. Searched in the installed onnxruntime packages, then in
    an operator-supplied `QAIRT_SDK_PATH`."""
    for module_name in ("onnxruntime_qnn", "onnxruntime"):
        module = _load_optional(module_name)
        if module is None:
            continue
        helper_fn = getattr(module, "get_qnn_htp_path", None)
        if callable(helper_fn):
            try:
                candidate = Path(helper_fn()).resolve()
                if candidate.is_file():
                    return candidate
            except Exception:
                pass
        root = _qnn_package_root(module)
        if root is None:
            continue
        try:
            found = next((p for p in root.rglob("QnnHtp.dll") if p.is_file()), None)
        except OSError:
            found = None
        if found is not None:
            return found

    sdk_path = os.getenv("QAIRT_SDK_PATH")
    if sdk_path:
        sdk_root = Path(sdk_path)
        for directory in (sdk_root, sdk_root / "bin", sdk_root / "lib"):
            candidate = directory / "QnnHtp.dll"
            if candidate.is_file():
                return candidate
    return None


def activate_qnn_execution_provider() -> QnnActivation:
    """Register the QNN execution provider library if ONNX Runtime hasn't
    already exposed it.

    Without this, a genuine Snapdragon NPU host reports no
    `QNNExecutionProvider` in `get_available_providers()` and resolves to its
    CPU floor - a false negative, not a hardware fact.
    """
    backend_path = resolve_qnn_backend_path()
    backend_str = str(backend_path) if backend_path else None

    if _QNN_PROVIDER in _available_providers():
        return QnnActivation(provider_registered=True, backend_path=backend_str)

    qnn_module = _load_optional("onnxruntime_qnn")
    if qnn_module is None:
        return QnnActivation(
            provider_registered=False, backend_path=backend_str, error="onnxruntime_qnn import failed"
        )

    library_path = _qnn_provider_library_path(qnn_module)
    if library_path is None:
        return QnnActivation(
            provider_registered=False,
            backend_path=backend_str,
            error="onnxruntime_qnn provider library not found",
        )

    dll_directory = _qnn_package_root(qnn_module)
    add_dll_directory = getattr(os, "add_dll_directory", None)
    if dll_directory is not None and add_dll_directory is not None:
        try:
            _DLL_DIRECTORY_HANDLES.append(add_dll_directory(str(dll_directory)))
        except Exception as exc:
            return QnnActivation(
                provider_registered=False,
                provider_library_path=str(library_path),
                dll_directory_path=str(dll_directory),
                backend_path=backend_str,
                error=f"add_dll_directory failed: {exc}",
            )

    ort = _load_optional("onnxruntime")
    register = getattr(ort, "register_execution_provider_library", None) if ort else None
    if not callable(register):
        return QnnActivation(
            provider_registered=False,
            provider_library_path=str(library_path),
            dll_directory_path=str(dll_directory) if dll_directory else None,
            backend_path=backend_str,
            error="onnxruntime register_execution_provider_library unavailable",
        )

    try:
        register(_QNN_PROVIDER, str(library_path))
    except Exception as exc:
        return QnnActivation(
            provider_registered=False,
            provider_library_path=str(library_path),
            dll_directory_path=str(dll_directory) if dll_directory else None,
            backend_path=backend_str,
            error=f"{_QNN_PROVIDER} registration failed: {exc}",
        )

    registered = _QNN_PROVIDER in _available_providers()
    return QnnActivation(
        provider_registered=registered,
        provider_library_path=str(library_path),
        dll_directory_path=str(dll_directory) if dll_directory else None,
        backend_path=backend_str,
        error=None if registered else f"{_QNN_PROVIDER} not exposed after registration",
    )


def _opencl_platform_count() -> int:
    """Count OpenCL platforms the host can actually enumerate.

    Section 16.4 defines arm64 `-gpu` as Adreno via OpenCL, for which ONNX
    Runtime publishes no execution provider - so this is probed directly
    rather than inferred from a device name.
    """
    library_names = ("OpenCL.dll",) if platform.system() == "Windows" else ("libOpenCL.so.1", "libOpenCL.so")
    for name in library_names:
        try:
            library = ctypes.CDLL(name)
        except OSError:
            continue
        try:
            count = ctypes.c_uint(0)
            status = library.clGetPlatformIDs(0, None, ctypes.byref(count))
        except Exception:
            continue
        if status == 0 and count.value > 0:
            return int(count.value)
    return 0


def _verify_gpu_provider(os_name: str, arch: str) -> tuple[bool, str | None]:
    for provider in GPU_PROVIDER_CANDIDATES.get((os_name, arch), ()):
        if _verify_provider_loads(provider):
            return True, provider
    return False, None


def _probe_evidence(arch: str) -> dict:
    """Accelerator evidence for `arch` on this host. Same arity as the
    existing profiler's own `_probe_evidence(arch)` so callers and tests that
    substitute it keep working; the returned dict is a superset of that
    module's keys (`available_providers`, `cuda_verified`, `gpu_verified`,
    `qnn_verified`).
    """
    os_name = _detect_os()
    inventory = collect_inventory()
    evidence: dict = {
        "os": os_name,
        "arch": arch,
        "available_providers": _available_providers(),
        "cuda_verified": False,
        "gpu_verified": False,
        "qnn_verified": False,
        "gpu_provider": None,
        "inventory_id": inventory.inventory_id,
    }

    if arch == "arm64":
        activation = activate_qnn_execution_provider()
        evidence["qnn_activation"] = asdict(activation)
        provider_options = {"backend_path": activation.backend_path} if activation.backend_path else None
        evidence["qnn_verified"] = activation.provider_registered and _verify_provider_loads(
            _QNN_PROVIDER, provider_options
        )
        # Re-read: registration mutates what ONNX Runtime reports.
        evidence["available_providers"] = _available_providers()
    else:
        evidence["cuda_verified"] = _verify_provider_loads(_CUDA_PROVIDER)

    gpu_verified, gpu_provider = _verify_gpu_provider(os_name, arch)
    if not gpu_verified and arch == "arm64":
        platform_count = _opencl_platform_count()
        evidence["opencl_platforms"] = platform_count
        # Adreno OpenCL counts only when the GPU is actually Qualcomm's -
        # an enumerable OpenCL platform alone can be a CPU runtime.
        if platform_count > 0 and inventory.gpu_vendor == "qualcomm":
            gpu_verified, gpu_provider = True, "opencl:adreno"

    evidence["gpu_verified"] = gpu_verified
    evidence["gpu_provider"] = gpu_provider
    return evidence


def resolve_hardware_profile_id() -> tuple[str, dict]:
    """Resolve the host to exactly one canonical profile ID.

    Order per Section 16.4 is QNN/CUDA -> GPU -> CPU, and every profile falls
    back to its arch's `*64-cpu` floor. A profile above `-cpu` is returned
    only when its execution provider was probe-verified to load.
    """
    os_name = _detect_os()
    arch = _detect_arch()
    evidence = _probe_evidence(arch)

    if arch == "x64":
        if evidence.get("cuda_verified"):
            return f"{os_name}-{arch}-cuda", evidence
        if evidence.get("gpu_verified"):
            return f"{os_name}-{arch}-gpu", evidence
        return f"{os_name}-{arch}-cpu", evidence

    if evidence.get("qnn_verified"):
        return f"{os_name}-{arch}-qnn", evidence
    if evidence.get("gpu_verified"):
        return f"{os_name}-{arch}-gpu", evidence
    return f"{os_name}-{arch}-cpu", evidence


def _ensure_system_run(conn: sqlite3.Connection) -> None:
    row = conn.execute("SELECT 1 FROM runs WHERE run_id = ?", (SYSTEM_RUN_ID,)).fetchone()
    if row is not None:
        return
    now = utc_now_rfc3339()
    conn.execute(
        "INSERT INTO runs (run_id, workflow_ref, status, input_json, budget_json, created_at, updated_at) "
        "VALUES (?, ?, 'SUCCEEDED', '{}', '{}', ?, ?)",
        (SYSTEM_RUN_ID, SYSTEM_WORKFLOW_REF, now, now),
    )
    conn.commit()


def run_hardware_profiler(conn: sqlite3.Connection, *, refresh: bool = False) -> str:
    """Resolve the host's canonical profile ID and write the resolution, its
    probe evidence, and the host inventory to the `events` table (Section
    16.4), anchored to the permanent sentinel "system" Run since probing
    isn't scoped to any one Run.

    Returns the profile ID. The event payload's `profile_id` key and the
    `hardware_profile_resolved` reason code match the existing profiler
    module's, so existing queries and consumers are unaffected.
    """
    if refresh:
        reset_inventory_cache()
    profile_id, evidence = resolve_hardware_profile_id()
    inventory = collect_inventory()
    _ensure_system_run(conn)
    write_event(
        conn,
        run_id=SYSTEM_RUN_ID,
        new_status="RESOLVED",
        actor="hardware_profiler",
        reason_code="hardware_profile_resolved",
        payload_json=json.dumps(
            {"profile_id": profile_id, "evidence": evidence, "inventory": asdict(inventory)},
            default=str,
        ),
    )
    return profile_id
