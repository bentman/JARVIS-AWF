import os

from awf.hardware import preflight


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
