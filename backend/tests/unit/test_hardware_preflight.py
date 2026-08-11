import os
from types import SimpleNamespace

from awf.hardware import preflight
from awf.hardware.profiler import HardwareInventory


def test_transformers_import_probe_suppresses_advisory_warning_env(monkeypatch):
    observed = []

    def import_module(name):
        observed.append((name, os.environ.get("TRANSFORMERS_NO_ADVISORY_WARNINGS")))
        return object()

    monkeypatch.delenv("TRANSFORMERS_NO_ADVISORY_WARNINGS", raising=False)
    monkeypatch.setattr(preflight.importlib, "import_module", import_module)

    assert preflight._load_optional("transformers") is not None

    assert observed == [("transformers", "1")]
    assert "TRANSFORMERS_NO_ADVISORY_WARNINGS" not in os.environ


def test_transformers_import_probe_restores_existing_advisory_env(monkeypatch):
    observed = []

    def import_module(name):
        observed.append((name, os.environ.get("TRANSFORMERS_NO_ADVISORY_WARNINGS")))
        return object()

    monkeypatch.setenv("TRANSFORMERS_NO_ADVISORY_WARNINGS", "0")
    monkeypatch.setattr(preflight.importlib, "import_module", import_module)

    assert preflight._load_optional("transformers") is not None

    assert observed == [("transformers", "1")]
    assert os.environ["TRANSFORMERS_NO_ADVISORY_WARNINGS"] == "0"


def test_opencl_adreno_token_can_come_from_qualcomm_platform_identity(monkeypatch):
    monkeypatch.setattr(preflight, "_import_tokens", lambda: ["import:onnxruntime"])
    monkeypatch.setattr(preflight, "activate_qnn_execution_provider", lambda: None)
    monkeypatch.setattr(preflight, "_available_providers", lambda: ["CPUExecutionProvider"])
    monkeypatch.setattr(preflight, "resolve_qnn_backend_path", lambda: None)
    monkeypatch.setattr(preflight, "_opencl_platform_count", lambda: 0)
    monkeypatch.setattr(preflight, "_opencl_qualcomm_platform_present", lambda: True)
    monkeypatch.setattr(preflight, "_vulkan_available", lambda: False)
    monkeypatch.setattr(preflight, "_ct2_cuda_count", lambda: 0)
    preflight.reset_preflight_cache()

    tokens = preflight.collect_preflight_tokens(HardwareInventory(os_name="linux", arch="arm64"), refresh=True)

    assert "opencl:adreno" in tokens


def test_qnn_provider_and_backend_paths_use_linux_shared_library_names(monkeypatch, tmp_path):
    qnn_root = tmp_path / "onnxruntime_qnn"
    qnn_root.mkdir()
    provider = qnn_root / "libonnxruntime_providers_qnn.so"
    backend = qnn_root / "libQnnHtp.so"
    provider.write_text("", encoding="utf-8")
    backend.write_text("", encoding="utf-8")
    module = SimpleNamespace(__file__=str(qnn_root / "__init__.py"))

    monkeypatch.setattr(preflight.platform, "system", lambda: "Linux")

    assert preflight._qnn_provider_library_path(module) == provider
    monkeypatch.setattr(preflight, "_load_optional", lambda name: module if name == "onnxruntime_qnn" else None)
    monkeypatch.delenv("QAIRT_SDK_PATH", raising=False)
    assert preflight.resolve_qnn_backend_path() == backend


def test_qnn_activation_registers_linux_provider_without_preloading_qnn_skel_libraries(monkeypatch, tmp_path):
    qnn_root = tmp_path / "onnxruntime_qnn"
    qnn_root.mkdir()
    provider = qnn_root / "libonnxruntime_providers_qnn.so"
    backend = qnn_root / "libQnnHtp.so"
    system = qnn_root / "libQnnSystem.so"
    provider.write_text("", encoding="utf-8")
    backend.write_text("", encoding="utf-8")
    system.write_text("", encoding="utf-8")
    providers = ["CPUExecutionProvider"]
    registered = []

    module = SimpleNamespace(
        LIB_DIR_FULL_PATH=str(qnn_root),
        get_library_path=lambda: str(provider),
        get_qnn_htp_path=lambda: str(backend),
    )
    ort = SimpleNamespace(
        get_available_providers=lambda: list(providers),
        register_execution_provider_library=lambda name, path: registered.append((name, path))
        or providers.append("QNNExecutionProvider"),
    )

    monkeypatch.setattr(preflight.platform, "system", lambda: "Linux")
    monkeypatch.setattr(preflight, "_load_optional", lambda name: module if name == "onnxruntime_qnn" else ort)

    def fail_if_preloaded(path, mode=0):
        raise AssertionError(f"QNN activation should not preload Linux shared libraries: {path}")

    monkeypatch.setattr(preflight.ctypes, "CDLL", fail_if_preloaded)

    result = preflight.activate_qnn_execution_provider()

    assert result.provider_registered is True
    assert result.provider_library_path == str(provider)
    assert result.backend_path == str(backend)
    assert registered == [("QNNExecutionProvider", str(provider))]


def test_qnn_activation_accepts_plugin_ep_device_when_provider_list_stays_legacy(monkeypatch, tmp_path):
    qnn_root = tmp_path / "onnxruntime_qnn"
    qnn_root.mkdir()
    provider = qnn_root / "libonnxruntime_providers_qnn.so"
    backend = qnn_root / "libQnnHtp.so"
    provider.write_text("", encoding="utf-8")
    backend.write_text("", encoding="utf-8")
    ep_device = SimpleNamespace(ep_name="QNNExecutionProvider")

    module = SimpleNamespace(
        LIB_DIR_FULL_PATH=str(qnn_root),
        get_library_path=lambda: str(provider),
        get_qnn_htp_path=lambda: str(backend),
    )
    ort = SimpleNamespace(
        get_available_providers=lambda: ["AzureExecutionProvider", "CPUExecutionProvider"],
        get_ep_devices=lambda: [ep_device],
        register_execution_provider_library=lambda name, path: None,
    )

    monkeypatch.setattr(preflight.platform, "system", lambda: "Linux")
    monkeypatch.setattr(preflight, "_load_optional", lambda name: module if name == "onnxruntime_qnn" else ort)

    result = preflight.activate_qnn_execution_provider()

    assert result.provider_registered is True
    assert result.error is None


def test_preflight_reports_qnn_activation_paths_and_errors(monkeypatch):
    activation = preflight.QnnActivation(
        provider_registered=False,
        provider_library_path="/tmp/libonnxruntime_providers_qnn.so",
        backend_path="/tmp/libQnnHtp.so",
        error="registration failed",
    )
    monkeypatch.setattr(preflight, "_import_tokens", lambda: ["import:onnxruntime_qnn"])
    monkeypatch.setattr(preflight, "activate_qnn_execution_provider", lambda: activation)
    monkeypatch.setattr(preflight, "_available_providers", lambda: ["CPUExecutionProvider"])
    monkeypatch.setattr(preflight, "resolve_qnn_backend_path", lambda: None)
    monkeypatch.setattr(preflight, "_opencl_platform_count", lambda: 0)
    monkeypatch.setattr(preflight, "_opencl_qualcomm_platform_present", lambda: False)
    monkeypatch.setattr(preflight, "_vulkan_available", lambda: False)
    monkeypatch.setattr(preflight, "_ct2_cuda_count", lambda: 0)

    tokens = preflight.collect_preflight_tokens(HardwareInventory(os_name="linux", arch="arm64"), refresh=True)

    assert "qnn:provider_library:/tmp/libonnxruntime_providers_qnn.so" in tokens
    assert "qnn:backend_path:/tmp/libQnnHtp.so" in tokens
    assert "qnn:provider_activation_error:registration failed" in tokens


def test_preflight_emits_qnn_ep_token_from_plugin_ep_device(monkeypatch):
    activation = preflight.QnnActivation(provider_registered=True)
    monkeypatch.setattr(preflight, "_import_tokens", lambda: ["import:onnxruntime_qnn"])
    monkeypatch.setattr(preflight, "activate_qnn_execution_provider", lambda: activation)
    monkeypatch.setattr(preflight, "_available_providers", lambda: ["CPUExecutionProvider"])
    monkeypatch.setattr(preflight, "_qnn_ep_device_names", lambda: ["QNNExecutionProvider"])
    monkeypatch.setattr(preflight, "resolve_qnn_backend_path", lambda: None)
    monkeypatch.setattr(preflight, "_opencl_platform_count", lambda: 0)
    monkeypatch.setattr(preflight, "_opencl_qualcomm_platform_present", lambda: False)
    monkeypatch.setattr(preflight, "_vulkan_available", lambda: False)
    monkeypatch.setattr(preflight, "_ct2_cuda_count", lambda: 0)

    tokens = preflight.collect_preflight_tokens(HardwareInventory(os_name="linux", arch="arm64"), refresh=True)

    assert "ep:QNNExecutionProvider" in tokens
    assert "ep_device:QNNExecutionProvider" in tokens
