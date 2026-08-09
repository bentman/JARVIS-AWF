"""Unit tests for LLM device readiness ladder resolution (ADR-0017)."""

from awf.hardware.profiler import HardwareInventory
from awf.hardware.readiness import derive_llm_readiness
from awf.llm.servers import Artifact, LlmServer


def _managed_server(profile_id: str, accelerator: str) -> LlmServer:
    return LlmServer(
        id="llama-server",
        managed=True,
        base_url="http://127.0.0.1:8080",
        openai_base_path="/v1",
        provider="openai",
        health_paths=(),
        artifacts={
            profile_id: Artifact(
                profile_id=profile_id,
                url=f"https://example.com/{profile_id}.tar.gz",
                archive="tar_gz",
                binary="llama-server",
                accelerator=accelerator,
                launch={},
            )
        },
        launch={},
        api_key_secret_name=None,
    )


def _write_ready_artifacts(tmp_path, profile_id: str):
    bin_path = tmp_path / "runtimes" / "llama.cpp" / profile_id / "llama-server"
    bin_path.parent.mkdir(parents=True)
    bin_path.write_bytes(b"binary content")

    model_path = tmp_path / "models" / "llm" / "model.gguf"
    model_path.parent.mkdir(parents=True)
    model_path.write_bytes(b"model content")

    return model_path


def test_derive_llm_readiness_unmanaged():
    inv = HardwareInventory()
    s = LlmServer(
        id="ollama",
        managed=False,
        base_url="http://127.0.0.1:11434",
        openai_base_path="/v1",
        provider="ollama",
        health_paths=(),
        artifacts={},
        launch={},
        api_key_secret_name=None,
    )

    r = derive_llm_readiness(inv, [], server=s, profile_id="linux-x64-cpu", model_path=None)
    assert r.ready is True
    assert "ollama is operator-run" in r.reason


def test_derive_llm_readiness_cuda_hardware_missing_artifact(tmp_path):
    inv = HardwareInventory(gpu_vendor="nvidia", cuda_available=True)
    tokens = ["ep:CUDAExecutionProvider"]

    bin_path = tmp_path / "runtimes" / "llama.cpp" / "linux-x64-cuda" / "llama-server"
    bin_path.parent.mkdir(parents=True)
    bin_path.write_bytes(b"binary content")

    model_path = tmp_path / "models" / "llm" / "model.gguf"
    model_path.parent.mkdir(parents=True)
    model_path.write_bytes(b"model content")

    # Managed server with only CPU artifacts
    s = LlmServer(
        id="llama-server",
        managed=True,
        base_url="http://127.0.0.1:8080",
        openai_base_path="/v1",
        provider="openai",
        health_paths=(),
        artifacts={
            "linux-x64-cuda": Artifact(
                profile_id="linux-x64-cuda",
                url="https://example.com/cuda.tar.gz",
                archive="tar_gz",
                binary="llama-server",
                accelerator="cpu",  # CPU accelerator declared for cuda profile
                launch={},
            )
        },
        launch={},
        api_key_secret_name=None,
    )

    r = derive_llm_readiness(
        inv, tokens, server=s, profile_id="linux-x64-cuda", model_path=model_path, repo_root=tmp_path
    )
    assert r.device == "cpu"
    assert r.ready is True
    assert "Degraded-accelerator-unavailable: no gpu.cuda artifact declared for linux-x64-cuda" in r.reason


def test_derive_llm_readiness_missing_binary(tmp_path):
    inv = HardwareInventory()
    tokens = []

    s = LlmServer(
        id="llama-server",
        managed=True,
        base_url="http://127.0.0.1:8080",
        openai_base_path="/v1",
        provider="openai",
        health_paths=(),
        artifacts={
            "linux-x64-cpu": Artifact(
                profile_id="linux-x64-cpu",
                url="https://example.com/cpu.tar.gz",
                archive="tar_gz",
                binary="llama-server",
                accelerator="cpu",
                launch={},
            )
        },
        launch={},
        api_key_secret_name=None,
    )

    r = derive_llm_readiness(inv, tokens, server=s, profile_id="linux-x64-cpu", model_path=None, repo_root=tmp_path)
    assert r.device == "cpu"
    assert r.ready is False
    assert "Degraded-no-sidecar-binary" in r.reason


def test_derive_llm_readiness_missing_model(tmp_path):
    inv = HardwareInventory()
    tokens = []

    bin_path = tmp_path / "runtimes" / "llama.cpp" / "linux-x64-cpu" / "llama-server"
    bin_path.parent.mkdir(parents=True)
    bin_path.write_bytes(b"binary content")

    s = LlmServer(
        id="llama-server",
        managed=True,
        base_url="http://127.0.0.1:8080",
        openai_base_path="/v1",
        provider="openai",
        health_paths=(),
        artifacts={
            "linux-x64-cpu": Artifact(
                profile_id="linux-x64-cpu",
                url="https://example.com/cpu.tar.gz",
                archive="tar_gz",
                binary="llama-server",
                accelerator="cpu",
                launch={},
            )
        },
        launch={},
        api_key_secret_name=None,
    )

    r = derive_llm_readiness(inv, tokens, server=s, profile_id="linux-x64-cpu", model_path=None, repo_root=tmp_path)
    assert r.device == "cpu"
    assert r.ready is False
    assert "Degraded-no-local-model-artifact" in r.reason


def test_derive_llm_readiness_fully_ready(tmp_path):
    inv = HardwareInventory()
    tokens = []

    model_path = _write_ready_artifacts(tmp_path, "linux-x64-cpu")
    s = _managed_server("linux-x64-cpu", "cpu")

    r = derive_llm_readiness(
        inv, tokens, server=s, profile_id="linux-x64-cpu", model_path=model_path, repo_root=tmp_path
    )
    assert r.device == "cpu"
    assert r.ready is True
    assert "running on cpu" in r.reason


def test_derive_llm_readiness_uses_cpu_profile_artifact_for_cpu_fallback(tmp_path):
    inv = HardwareInventory(gpu_vendor="nvidia", cuda_available=True)
    tokens = ["ep:CUDAExecutionProvider"]
    model_path = _write_ready_artifacts(tmp_path, "linux-x64-cpu")
    s = LlmServer(
        id="llama-server",
        managed=True,
        base_url="http://127.0.0.1:8080",
        openai_base_path="/v1",
        provider="openai",
        health_paths=(),
        artifacts={
            "linux-x64-cpu": Artifact(
                profile_id="linux-x64-cpu",
                url="https://example.com/cpu.tar.gz",
                archive="tar_gz",
                binary="llama-server",
                accelerator="cpu",
                launch={},
            )
        },
        launch={},
        api_key_secret_name=None,
    )

    r = derive_llm_readiness(
        inv, tokens, server=s, profile_id="linux-x64-cuda", model_path=model_path, repo_root=tmp_path
    )

    assert r.device == "cpu"
    assert r.ready is True
    assert "Degraded-accelerator-unavailable: no gpu.cuda artifact declared for linux-x64-cuda" in r.reason


def test_derive_llm_readiness_returns_cuda_when_declared_and_present(tmp_path):
    model_path = _write_ready_artifacts(tmp_path, "linux-x64-cuda")
    s = _managed_server("linux-x64-cuda", "gpu.cuda")
    inv = HardwareInventory(gpu_vendor="nvidia", cuda_available=True)
    tokens = ["ep:CUDAExecutionProvider"]

    r = derive_llm_readiness(
        inv,
        tokens,
        server=s,
        profile_id="linux-x64-cuda",
        model_path=model_path,
        repo_root=tmp_path,
    )

    assert r.device == "gpu.cuda"
    assert r.ready is True
    assert "gpu.cuda artifact declared" in r.reason


def test_derive_llm_readiness_returns_vulkan_when_declared_and_present(tmp_path):
    model_path = _write_ready_artifacts(tmp_path, "linux-x64-gpu")
    s = _managed_server("linux-x64-gpu", "gpu.vulkan")
    inv = HardwareInventory(gpu_available=True, gpu_vendor="amd")
    tokens = ["vulkan:available"]

    r = derive_llm_readiness(
        inv,
        tokens,
        server=s,
        profile_id="linux-x64-gpu",
        model_path=model_path,
        repo_root=tmp_path,
    )

    assert r.device == "gpu.vulkan"
    assert r.ready is True
    assert "gpu.vulkan artifact declared" in r.reason


def test_derive_llm_readiness_returns_qnn_when_declared_and_present(tmp_path):
    model_path = _write_ready_artifacts(tmp_path, "windows-arm64-qnn")
    s = _managed_server("windows-arm64-qnn", "npu.qnn")
    inv = HardwareInventory(npu_vendor="qualcomm", npu_available=True)
    tokens = ["ep:QNNExecutionProvider", "dll:QnnHtp"]

    r = derive_llm_readiness(
        inv,
        tokens,
        server=s,
        profile_id="windows-arm64-qnn",
        model_path=model_path,
        repo_root=tmp_path,
    )

    assert r.device == "npu.qnn"
    assert r.ready is True
    assert "npu.qnn artifact declared" in r.reason


def test_derive_llm_readiness_returns_adreno_when_declared_and_present(tmp_path):
    model_path = _write_ready_artifacts(tmp_path, "windows-arm64-gpu")
    s = _managed_server("windows-arm64-gpu", "gpu.opencl.adreno")
    inv = HardwareInventory(gpu_vendor="qualcomm", gpu_available=True)
    tokens = ["opencl:adreno"]

    r = derive_llm_readiness(
        inv,
        tokens,
        server=s,
        profile_id="windows-arm64-gpu",
        model_path=model_path,
        repo_root=tmp_path,
    )

    assert r.device == "gpu.opencl.adreno"
    assert r.ready is True
    assert "gpu.opencl.adreno artifact declared" in r.reason
