"""Hardware Profiler (Section 16.4, ADR-0008).

Resolves the host to exactly one canonical profile ID, as a summary of four
per-speech-function `hardware.readiness` results. Public contract:
`CANONICAL_PROFILES`, `SYSTEM_RUN_ID`, `_detect_os`, `_detect_arch`,
`resolve_hardware_profile_id(repo_root) -> (profile_id, payload)`, and
`run_hardware_profiler(conn, *, repo_root=None, refresh=False) -> profile_id`,
which writes one `hardware_profile_resolved` event whose payload carries
`profile_id`, `inventory`, `tokens`, and `readiness`. Callers:
`speech/pipeline.py`, `workflow/activities.py` (the `hardware_probe`
activity, which calls `run_hardware_profiler(conn)` with no other arguments -
`repo_root` defaults to `awf.paths.REPO_ROOT`).

Every claim is probe-derived, never assumed. This module owns exactly the
**profile** stage: a full host **inventory** (OS/device class, CPU, memory,
GPU vendor/VRAM, CUDA driver, NPU vendor), each detector independently
fault-isolated, and a content-addressed `inventory_id` over the inventory's
own fields so two identical hosts hash identically and a changed host is
visible as a changed digest. `collect_inventory` is this stage's whole
output - it never decides the profile on its own: whether the installed
environment can actually reach an accelerator is
`hardware.preflight.collect_preflight_tokens`'s job, and which device each
speech function gets is `hardware.readiness`'s job. The canonical profile ID
is the strongest device any function's readiness selected, mapped onto the
Section 16.4 enum, keeping the `*64-cpu` floor.

Identifier note: `profile_id` always means the canonical Section 16.4 enum
value (e.g. `windows-arm64-qnn`). The host inventory's own content-hash
identity is carried separately as `inventory_id` (`inv-<16 hex>`), so the
two vocabularies never collide.

Vocabulary note: architecture is normalized to this repo's `x64`/`arm64`
(the canonical profile enum's own spelling), not `platform.machine()`'s
`amd64`.
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
from awf.hardware.preflight import collect_preflight_tokens, reset_preflight_cache
from awf.hardware.readiness import (
    derive_llm_readiness,
    derive_stt_readiness,
    derive_tts_readiness,
    derive_vad_readiness,
    derive_wake_readiness,
)
from awf.paths import REPO_ROOT
from awf.registry.hardware_voice_manifest import artifact_paths

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

# Chassis types the SMBIOS spec assigns to portable enclosures.
_LAPTOP_CHASSIS_TYPES = {8, 9, 10, 11, 12, 14, 18, 21, 30, 31, 32}

_INVENTORY_CACHE: "HardwareInventory | None" = None


class HardwareProfilerError(RuntimeError):
    pass


@dataclass(frozen=True)
class HardwareInventory:
    """Descriptive host facts. The canonical profile ID is rolled up from the
    four per-function readiness results (ADR-0008), which consult these
    fields alongside preflight tokens - a detector that comes back empty
    degrades the record's detail and can floor a function's readiness to
    `cpu`, but decides nothing by itself."""

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
        raise HardwareProfilerError(f"unsupported architecture for the canonical profile enum: {platform.machine()}")
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
            "(Get-CimInstance Win32_SystemEnclosure | Select-Object -ExpandProperty ChassisTypes) -join ','"
        )
        chassis_types = {
            int(part.strip()) for part in output.replace("[", "").replace("]", "").split(",") if part.strip().isdigit()
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
        "Get-CimInstance Win32_VideoController | Select-Object Name,AdapterRAM | ConvertTo-Json -Compress"
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


def resolve_hardware_profile_id(repo_root: Path) -> tuple[str, dict]:
    """Resolve the host to exactly one canonical profile ID, as a summary of
    four per-function `hardware.readiness` results.

    Order per Section 16.4 is QNN/CUDA -> GPU -> CPU, and every profile falls
    back to its arch's `*64-cpu` floor: the suffix is `qnn` if any function's
    readiness selected `qnn`, else `cuda` if any selected `cuda`, else `gpu`
    if any selected `directml` or an Adreno OpenCL platform was found, else
    `cpu`. VAD and wake readiness need artifact paths, hence `repo_root`.
    """
    os_name = _detect_os()
    arch = _detect_arch()
    inventory = collect_inventory()
    tokens = collect_preflight_tokens(inventory)

    vad_paths = artifact_paths(repo_root, "vad")
    wake_paths = artifact_paths(repo_root, "wake")

    readiness = {
        "stt": derive_stt_readiness(inventory, tokens),
        "tts": derive_tts_readiness(inventory, tokens),
        "vad": derive_vad_readiness(inventory, tokens, vad_paths.get("silero_vad.onnx")),
        "wake": derive_wake_readiness(inventory, tokens, wake_paths),
    }

    devices = {name: result.device for name, result in readiness.items()}
    if "qnn" in devices.values():
        suffix = "qnn"
    elif "cuda" in devices.values():
        suffix = "cuda"
    elif "directml" in devices.values() or "opencl:adreno" in tokens:
        suffix = "gpu"
    else:
        suffix = "cpu"

    profile_id = f"{os_name}-{arch}-{suffix}"

    try:
        from awf.llm.discovery import model_by_name
        from awf.llm.selector import current_selection
        from awf.llm.servers import load_servers

        default_id, servers = load_servers(repo_root)
        sel = current_selection(repo_root)
        if sel is not None and sel.server_id in servers:
            server = servers[sel.server_id]
            model_p = None
            if sel.model:
                try:
                    lm = model_by_name(repo_root, sel.model)
                    model_p = lm.primary
                except Exception:
                    pass
        else:
            server = servers[default_id]
            model_p = None

        readiness["llm"] = derive_llm_readiness(
            inventory, tokens, server=server, profile_id=profile_id, model_path=model_p, repo_root=repo_root
        )
    except Exception as exc:
        from awf.hardware.readiness import Readiness

        readiness["llm"] = Readiness(device="cpu", ready=False, reason=f"llm readiness resolution failed: {exc}")

    return profile_id, {"inventory": inventory, "tokens": tokens, "readiness": readiness}


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


def run_hardware_profiler(conn: sqlite3.Connection, *, repo_root: Path | None = None, refresh: bool = False) -> str:
    """Resolve the host's canonical profile ID and write the resolution -
    the host inventory, the preflight tokens, and all four readiness results
    - to the `events` table (Section 16.4), anchored to the permanent
    sentinel "system" Run since probing isn't scoped to any one Run.

    `repo_root` defaults to `awf.paths.REPO_ROOT` - not a signature change
    for existing callers (`refresh` was already keyword-only with a
    default; `repo_root` is added the same way).

    Returns the profile ID. The event payload's `profile_id` key and the
    `hardware_profile_resolved` reason code match the existing profiler
    module's, so existing queries and consumers are unaffected.
    """
    if refresh:
        reset_inventory_cache()
        reset_preflight_cache()
    if repo_root is None:
        repo_root = REPO_ROOT
    profile_id, payload = resolve_hardware_profile_id(repo_root)
    _ensure_system_run(conn)
    write_event(
        conn,
        run_id=SYSTEM_RUN_ID,
        new_status="RESOLVED",
        actor="hardware_profiler",
        reason_code="hardware_profile_resolved",
        payload_json=json.dumps(
            {
                "profile_id": profile_id,
                "inventory": asdict(payload["inventory"]),
                "tokens": payload["tokens"],
                "readiness": {name: asdict(result) for name, result in payload["readiness"].items()},
            },
            default=str,
        ),
    )
    return profile_id
