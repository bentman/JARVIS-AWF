"""Unit tests for LLM server configuration parsing (ADR-0017)."""

from textwrap import indent

import pytest

from awf.llm.servers import LlmServerError, artifact_for, load_servers


def write_llm_servers(repo_root, spec: str) -> None:
    path = repo_root / "config" / "app_registry" / "llm-servers" / "default" / "1.0.0.yaml"
    path.parent.mkdir(parents=True)
    path.write_text(
        f"""apiVersion: awf/v1
kind: LlmServers
metadata:
  name: default
  version: 1.0.0
  digest: sha256:test
spec:
{indent(spec.strip(), "  ")}
"""
    )


def test_load_servers_valid(tmp_path):
    yaml_content = """
default_server: llama-server
servers:
  llama-server:
    managed: true
    base_url: http://127.0.0.1:8080
    openai_base_path: /v1
    provider: openai
    health_paths: [/health, /v1/models]
    artifacts:
      linux-x64-cpu:
        url: https://example.com/llama.tar.gz
        archive: tar_gz
        binary: llama-server
        accelerator: cpu
    launch:
      ctx_size: 4096
"""
    write_llm_servers(tmp_path, yaml_content)

    default_id, servers = load_servers(tmp_path)
    assert default_id == "llama-server"
    assert "llama-server" in servers

    s = servers["llama-server"]
    assert s.managed is True
    assert s.api_base == "http://127.0.0.1:8080/v1"

    art = artifact_for(s, "linux-x64-cpu")
    assert art is not None
    assert art.profile_id == "linux-x64-cpu"
    assert art.binary == "llama-server"
    assert art.launch["ctx_size"] == 4096

    assert artifact_for(s, "windows-x64-cpu") is None


def test_load_real_servers_declares_every_canonical_profile(repo_root):
    from awf.hardware.profiler import CANONICAL_PROFILES

    _default_id, servers = load_servers(repo_root)
    llama_server = servers["llama-server"]

    assert set(llama_server.artifacts) == set(CANONICAL_PROFILES)
    assert artifact_for(llama_server, "linux-x64-cuda").archive == "manual"
    assert artifact_for(llama_server, "linux-x64-cuda").accelerator == "gpu.cuda"
    assert artifact_for(llama_server, "windows-x64-cuda").archive == "zip"
    assert "llama-b9704-bin-win-cuda-12.4-x64.zip" in artifact_for(llama_server, "windows-x64-cuda").url
    assert artifact_for(llama_server, "linux-x64-gpu").accelerator == "gpu.vulkan"
    assert artifact_for(llama_server, "windows-arm64-gpu").accelerator == "gpu.opencl.adreno"
    assert artifact_for(llama_server, "windows-arm64-qnn").accelerator == "npu.qnn"


def test_load_servers_invalid_canonical_profile(tmp_path):
    yaml_content = """
default_server: llama-server
servers:
  llama-server:
    managed: true
    base_url: http://127.0.0.1:8080
    openai_base_path: /v1
    provider: openai
    health_paths: [/health]
    artifacts:
      invalid-host-profile:
        url: https://example.com/llama.tar.gz
        archive: tar_gz
        binary: llama-server
        accelerator: cpu
"""
    write_llm_servers(tmp_path, yaml_content)

    with pytest.raises(LlmServerError) as exc_info:
        load_servers(tmp_path)

    assert "invalid-host-profile" in str(exc_info.value)
