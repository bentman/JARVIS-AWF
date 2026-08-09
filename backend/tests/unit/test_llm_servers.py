"""Unit tests for LLM server configuration parsing (ADR-0017)."""

import pytest

from awf.llm.servers import Artifact, LlmServerError, artifact_for, load_servers


def test_load_servers_valid(tmp_path):
    config_dir = tmp_path / "config" / "llm"
    config_dir.mkdir(parents=True)
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
    (config_dir / "servers.yaml").write_text(yaml_content)

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


def test_load_servers_invalid_canonical_profile(tmp_path):
    config_dir = tmp_path / "config" / "llm"
    config_dir.mkdir(parents=True)
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
    (config_dir / "servers.yaml").write_text(yaml_content)

    with pytest.raises(LlmServerError) as exc_info:
        load_servers(tmp_path)

    assert "invalid-host-profile" in str(exc_info.value)
