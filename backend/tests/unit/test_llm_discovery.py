"""Unit tests for LLM local model discovery and binary acquisition (ADR-0017)."""

import zipfile

import pytest

from awf.llm.discovery import acquire_binary, binary_path, local_models, model_by_name
from awf.llm.servers import Artifact, LlmServerError


def test_local_models_discovery(tmp_path):
    models_dir = tmp_path / "models" / "llm" / "qwen3-4b"
    models_dir.mkdir(parents=True)

    small = models_dir / "small.gguf"
    small.write_bytes(b"12345")
    large = models_dir / "large.gguf"
    large.write_bytes(b"1234567890")

    found = local_models(tmp_path)
    assert len(found) == 1
    assert found[0].name == "qwen3-4b"
    assert found[0].primary == large
    assert len(found[0].files) == 2

    m = model_by_name(tmp_path, "qwen3-4b")
    assert m.primary == large
    assert model_by_name(tmp_path, "large.gguf").primary == large
    assert model_by_name(tmp_path, "small.gguf").primary == large

    with pytest.raises(LlmServerError):
        model_by_name(tmp_path, "nonexistent-model")


def test_acquire_binary_present(tmp_path):
    prof_id = "linux-x64-cpu"
    art = Artifact(
        profile_id=prof_id,
        url="https://example.com/test.zip",
        archive="zip",
        binary="llama-server",
        accelerator="cpu",
        launch={},
    )

    b_path = binary_path(tmp_path, prof_id, art)
    b_path.parent.mkdir(parents=True)
    b_path.write_bytes(b"dummy binary content")

    res = acquire_binary(tmp_path, prof_id, art)
    assert res["status"] == "PRESENT"
    assert res["path"] == str(b_path)


def test_acquire_binary_manual_missing_reports_operator_action(tmp_path):
    prof_id = "linux-x64-cuda"
    art = Artifact(
        profile_id=prof_id,
        url="manual://llama.cpp/b9704/linux-x64-cuda",
        archive="manual",
        binary="llama-server",
        accelerator="gpu.cuda",
        launch={},
    )

    with pytest.raises(LlmServerError) as exc_info:
        acquire_binary(tmp_path, prof_id, art)

    assert "declared as manual" in str(exc_info.value)
    assert "runtimes/llama.cpp/linux-x64-cuda" in str(exc_info.value)


def test_acquire_binary_extract(tmp_path, monkeypatch):
    prof_id = "linux-x64-cpu"
    art = Artifact(
        profile_id=prof_id,
        url="https://example.com/test.zip",
        archive="zip",
        binary="llama-server",
        accelerator="cpu",
        launch={},
    )

    zip_path = tmp_path / "test.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("bin_folder/llama-server", "binary data")
        zf.writestr("bin_folder/libggml.so", "library data")

    def mock_urlopen(url):
        class MockResp:
            def __enter__(self):
                return open(zip_path, "rb")

            def __exit__(self, *args):
                pass

        return MockResp()

    monkeypatch.setattr("urllib.request.urlopen", mock_urlopen)

    res = acquire_binary(tmp_path, prof_id, art)
    assert res["status"] == "ACQUIRED"

    target_bin = binary_path(tmp_path, prof_id, art)
    assert target_bin.is_file()
    assert (target_bin.parent / "libggml.so").is_file()
