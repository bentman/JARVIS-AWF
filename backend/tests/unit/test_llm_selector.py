"""Unit tests for LLM selector and resident-mind publishing (ADR-0017)."""

import pytest

from awf.db.bootstrap import init_db
from awf.db.connection import get_connection
from awf.llm.selector import current_selection, select
from awf.llm.servers import LlmServerError


def test_select_loopback_and_remote(tmp_path):
    conn_path = tmp_path / "data" / "awf.db"
    init_db(conn_path)
    conn = get_connection(conn_path)

    config_dir = tmp_path / "config" / "llm"
    config_dir.mkdir(parents=True)

    servers_yaml = """
default_server: llama-server
servers:
  llama-server:
    managed: true
    base_url: http://127.0.0.1:8080
    openai_base_path: /v1
    provider: openai
    health_paths: [/health]
    artifacts:
      linux-x64-cpu:
        url: https://example.com/llama.tar.gz
        archive: tar_gz
        binary: llama-server
        accelerator: cpu

  remote-server:
    managed: false
    base_url: http://192.168.1.50:8080
    openai_base_path: /v1
    provider: openai
    health_paths: [/v1/models]
"""
    (config_dir / "servers.yaml").write_text(servers_yaml)

    # Setup dummy model directory
    m_dir = tmp_path / "models" / "llm" / "model1"
    m_dir.mkdir(parents=True)
    (m_dir / "qwen.gguf").write_bytes(b"123")

    # Select local loopback server
    res_local = select(tmp_path, conn, server_id="llama-server")
    assert res_local["server_id"] == "llama-server"
    assert res_local["local_only"] is True

    sel = current_selection(tmp_path)
    assert sel is not None
    assert sel.server_id == "llama-server"
    assert sel.local_only is True

    # Remote server without allow_remote should raise LlmServerError
    with pytest.raises(LlmServerError):
        select(tmp_path, conn, server_id="remote-server")

    # Remote server with allow_remote should succeed
    res_remote = select(tmp_path, conn, server_id="remote-server", allow_remote=True)
    assert res_remote["server_id"] == "remote-server"
    assert res_remote["local_only"] is False

    conn.close()


def test_select_openai_compatible_same_port_unambiguous(tmp_path):
    conn_path = tmp_path / "data" / "awf.db"
    init_db(conn_path)
    conn = get_connection(conn_path)

    config_dir = tmp_path / "config" / "llm"
    config_dir.mkdir(parents=True)

    servers_yaml = """
default_server: llama-server
servers:
  llama-server:
    managed: true
    base_url: http://127.0.0.1:8080
    openai_base_path: /v1
    provider: openai
    health_paths: [/health]
    artifacts: {}

  openai-compatible:
    managed: false
    base_url: http://127.0.0.1:8080
    openai_base_path: /v1
    provider: openai
    health_paths: [/v1/models]
"""
    (config_dir / "servers.yaml").write_text(servers_yaml)

    # Select openai-compatible which shares base_url with llama-server
    select(tmp_path, conn, server_id="openai-compatible", model="llama.app/qwen")
    sel = current_selection(tmp_path)
    assert sel is not None
    assert sel.server_id == "openai-compatible"
    assert sel.model == "llama.app/qwen"

    conn.close()
