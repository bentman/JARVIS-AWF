import os

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
