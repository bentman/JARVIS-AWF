"""Integration tests for LLM CLI operations and activities (ADR-0017)."""

import shutil

from awf.cli import core_ops as ops
from awf.db.bootstrap import init_db
from awf.db.connection import get_connection
from awf.paths import REPO_ROOT, config_voice_dir
from awf.workflow.activities import ACTIVITY_REGISTRY


def test_llm_cli_servers_and_models(tmp_path):
    conn_path = tmp_path / "data" / "awf.db"
    init_db(conn_path)
    conn = get_connection(conn_path)

    # Copy config/voice to tmp_path for voice manifest resolution
    v_dir = config_voice_dir(tmp_path)
    if not v_dir.exists():
        shutil.copytree(config_voice_dir(REPO_ROOT), v_dir)

    # Add dummy local model for managed server selection
    m_dir = tmp_path / "models" / "llm" / "qwen-4b"
    m_dir.mkdir(parents=True)
    (m_dir / "qwen.gguf").write_bytes(b"dummy gguf content")

    # Add servers.yaml
    cfg_dir = tmp_path / "config" / "llm"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "servers.yaml").write_text("""
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
""")

    servers_report = ops.op_llm_servers(tmp_path)
    assert servers_report["default_server"] == "llama-server"
    assert "llama-server" in servers_report["servers"]

    models_report = ops.op_llm_models(tmp_path)
    assert "local_models" in models_report
    assert len(models_report["local_models"]) == 1

    select_report = ops.op_llm_select(tmp_path, conn, server_id="llama-server")
    assert select_report["server_id"] == "llama-server"
    assert select_report["profile_ref"] == "resident-mind@1.0.0"

    conn.close()


def test_llm_activity_ensure_registered(tmp_path):
    assert "llm_server_ensure" in ACTIVITY_REGISTRY
    conn_path = tmp_path / "data" / "awf.db"
    init_db(conn_path)
    conn = get_connection(conn_path)

    # Copy config/voice to tmp_path
    v_dir = config_voice_dir(tmp_path)
    if not v_dir.exists():
        shutil.copytree(config_voice_dir(REPO_ROOT), v_dir)

    cfg_dir = tmp_path / "config" / "llm"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "servers.yaml").write_text("""
default_server: llama-server
servers:
  llama-server:
    managed: true
    base_url: http://127.0.0.1:8080
    openai_base_path: /v1
    provider: openai
    health_paths: [/health]
    artifacts: {}
""")

    fn = ACTIVITY_REGISTRY["llm_server_ensure"]
    res = fn(conn, {})
    assert "state" in res

    conn.close()
