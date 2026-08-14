"""Integration tests for LLM CLI operations and activities (ADR-0017)."""

import shutil
from textwrap import indent

from awf.cli import core_ops as ops
from awf.db.bootstrap import init_db
from awf.db.connection import get_connection
from awf.paths import REPO_ROOT, config_registry_dir
from awf.workflow.activities import ACTIVITY_REGISTRY


def copy_config_registry(repo_root):
    target = config_registry_dir(repo_root)
    if not target.exists():
        shutil.copytree(config_registry_dir(REPO_ROOT), target)


def write_llm_servers(repo_root, spec: str) -> None:
    path = config_registry_dir(repo_root) / "llm-servers" / "default" / "1.0.0.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
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


def test_llm_cli_servers_and_models(tmp_path):
    conn_path = tmp_path / "data" / "awf.db"
    init_db(conn_path)
    conn = get_connection(conn_path)

    copy_config_registry(tmp_path)

    # Add dummy local model for managed server selection
    m_dir = tmp_path / "models" / "llm" / "qwen-4b"
    m_dir.mkdir(parents=True)
    (m_dir / "qwen.gguf").write_bytes(b"dummy gguf content")

    write_llm_servers(
        tmp_path,
        """
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
""",
    )

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

    copy_config_registry(tmp_path)

    write_llm_servers(
        tmp_path,
        """
default_server: llama-server
servers:
  llama-server:
    managed: true
    base_url: http://127.0.0.1:8080
    openai_base_path: /v1
    provider: openai
    health_paths: [/health]
    artifacts: {}
    """,
    )

    fn = ACTIVITY_REGISTRY["llm_server_ensure"].fn
    assert fn is not None
    res = fn(conn, {})
    assert "state" in res

    conn.close()


def test_llm_serve_uses_cpu_fallback_when_host_artifact_missing(tmp_path, monkeypatch):
    conn_path = tmp_path / "data" / "awf.db"
    init_db(conn_path)
    conn = get_connection(conn_path)

    m_dir = tmp_path / "models" / "llm" / "qwen"
    m_dir.mkdir(parents=True)
    (m_dir / "qwen.gguf").write_bytes(b"dummy gguf content")

    cpu_binary = tmp_path / "runtimes" / "llama.cpp" / "linux-x64-cpu" / "llama-server"
    cpu_binary.parent.mkdir(parents=True)
    cpu_binary.write_text("binary")

    write_llm_servers(
        tmp_path,
        """
default_server: llama-server
servers:
  llama-server:
    managed: true
    base_url: http://127.0.0.1:8080
    openai_base_path: /v1
    provider: openai
    health_paths: [/health]
    artifacts:
      linux-x64-cuda:
        url: manual://cuda
        archive: manual
        binary: llama-server
        accelerator: gpu.cuda
      linux-x64-cpu:
        url: https://example.com/llama.tar.gz
        archive: tar_gz
        binary: llama-server
        accelerator: cpu
""",
    )

    monkeypatch.setattr("awf.hardware.profiler.resolve_hardware_profile_id", lambda _repo_root: ("linux-x64-cuda", {}))

    captured = {}

    def fake_start(repo_root, server, artifact, model, *, conn=None, detach=False):
        from awf.llm.sidecar import SidecarStatus

        captured["artifact"] = artifact
        captured["model"] = model
        captured["detach"] = detach
        return SidecarStatus(
            state="running",
            server_id=server.id,
            base_url=server.base_url,
            model_path=str(model.primary),
            profile_id=artifact.profile_id,
            pid=1,
            adopted=False,
            warnings=(),
            reason=None,
        )

    monkeypatch.setattr("awf.llm.sidecar.start", fake_start)

    result = ops.op_llm_serve(tmp_path, conn, action="start")

    assert result["profile_id"] == "linux-x64-cpu"
    assert captured["artifact"].profile_id == "linux-x64-cpu"
    assert captured["detach"] is True
    conn.close()
