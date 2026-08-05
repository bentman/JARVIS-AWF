"""Runtime-capability probes of the installed environment (ADR-0008).

Preflight answers "what can the installed environment actually do," as a
sorted list of tokens. A hardware fact (from `hardware.profiler.collect_inventory`)
and a runtime token together are what `hardware.readiness` requires before it
grants a speech function anything above its `cpu` floor - a token alone never
decides a device.

Provider tokens (`ep:<provider>`) come from `onnxruntime.get_available_providers()`
alone - no probe here constructs an ONNX Runtime session. A provider's own
library loading its actual backend (CUDA, DirectML, QNN) at first real use is
where a mismatched driver or runtime surfaces, and it surfaces at the adapter
that made the call, not here.
"""

import ctypes
import importlib
import os
import platform
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from awf.hardware.profiler import HardwareInventory

_QNN_PROVIDER = "QNNExecutionProvider"

_IMPORT_CHECK_MODULES = ("onnxruntime", "ctranslate2", "faster_whisper", "kokoro_onnx", "openwakeword", "silero_vad")

# Registered DLL directory handles must outlive the call that added them.
_DLL_DIRECTORY_HANDLES: list[object] = []
_PREFLIGHT_CACHE: list[str] | None = None


@dataclass(frozen=True)
class QnnActivation:
    provider_registered: bool
    provider_library_path: str | None = None
    dll_directory_path: str | None = None
    backend_path: str | None = None
    error: str | None = None


def _load_optional(module_name: str):
    try:
        return importlib.import_module(module_name)
    except Exception:
        return None


def _available_providers() -> list[str]:
    ort = _load_optional("onnxruntime")
    if ort is None:
        return []
    try:
        return list(ort.get_available_providers())
    except Exception:
        return []


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


def _import_tokens() -> list[str]:
    tokens = []
    for module_name in _IMPORT_CHECK_MODULES:
        if _load_optional(module_name) is not None:
            tokens.append(f"import:{module_name}")
        else:
            tokens.append(f"import:{module_name}:MISSING")
    return tokens


def _ct2_cuda_count() -> int:
    ct2 = _load_optional("ctranslate2")
    if ct2 is None:
        return 0
    try:
        return int(ct2.get_cuda_device_count())
    except Exception:
        return 0


def collect_preflight_tokens(inventory: "HardwareInventory", *, refresh: bool = False) -> list[str]:
    global _PREFLIGHT_CACHE
    if _PREFLIGHT_CACHE is not None and not refresh:
        return _PREFLIGHT_CACHE

    tokens = _import_tokens()

    # QNN activation before reading available providers: registration
    # mutates what ONNX Runtime reports. Registration only loads a provider
    # library into ONNX Runtime's own registry - it builds no session, so it
    # carries none of session construction's native-crash risk.
    activate_qnn_execution_provider()
    tokens.extend(f"ep:{provider}" for provider in _available_providers())

    backend_path = resolve_qnn_backend_path()
    tokens.append("dll:QnnHtp" if backend_path is not None else "dll:QnnHtp:MISSING")

    if _opencl_platform_count() > 0 and inventory.gpu_vendor == "qualcomm":
        tokens.append("opencl:adreno")

    tokens.append(f"ct2:cuda:{_ct2_cuda_count()}")

    tokens = sorted(set(tokens))
    _PREFLIGHT_CACHE = tokens
    return tokens


def reset_preflight_cache() -> None:
    global _PREFLIGHT_CACHE
    _PREFLIGHT_CACHE = None
