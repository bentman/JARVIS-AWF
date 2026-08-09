"""Unit tests for LLM sidecar command construction and probing (ADR-0017)."""

import json
from pathlib import Path

from awf.db.bootstrap import init_db
from awf.db.connection import get_connection
from awf.hardware.profiler import SYSTEM_RUN_ID
from awf.llm.servers import LlmServer
from awf.llm.sidecar import Health, build_command, probe, start, stop


def test_build_command_full_row_coverage_and_isolation():
    binary = Path("/runtimes/llama.cpp/linux-x64-cpu/llama-server")
    model_path = Path("/models/llm/model.gguf")
    base_url = "http://127.0.0.1:8080"
    launch = {
        "ctx_size": 4096,
        "threads": "auto",
        "threads_batch": 4,
        "batch_size": 512,
        "ubatch_size": 128,
        "gpu_layers": "all",
        "cache_type_k": "q8_0",
        "cache_type_v": "q8_0",
        "split_mode": "layer",
        "main_gpu": 0,
        "flash_attn": "on",
        "device": "cuda:0",
        "warmup": True,
        "parallel": 4,  # turn isolation override
        "cont_batching": True,  # turn isolation override
        "cache_ram_mb": 1024,  # turn isolation override
        "invalid_key": "val",  # unsupported launch key
    }

    cmd = build_command(binary, model_path, base_url, launch)

    expected_argv = (
        str(binary),
        "--model",
        str(model_path),
        "--host",
        "127.0.0.1",
        "--port",
        "8080",
        "--ctx-size",
        "4096",
        "--threads",
        "-1",
        "--threads-batch",
        "4",
        "--batch-size",
        "512",
        "--ubatch-size",
        "128",
        "--gpu-layers",
        "all",
        "--cache-type-k",
        "q8_0",
        "--cache-type-v",
        "q8_0",
        "--split-mode",
        "layer",
        "--main-gpu",
        "0",
        "--flash-attn",
        "on",
        "--device",
        "cuda:0",
        "--warmup",
        "--cache-ram",
        "0",
        "--parallel",
        "1",
        "--no-cont-batching",
    )

    assert cmd.argv == expected_argv

    expected_warnings = (
        "launch key 'parallel' is overridden by turn isolation",
        "launch key 'cont_batching' is overridden by turn isolation",
        "launch key 'cache_ram_mb' is overridden by turn isolation",
        "unsupported launch key: invalid_key",
    )
    assert cmd.warnings == expected_warnings


def test_build_command_invalid_values():
    binary = Path("/runtimes/llama.cpp/linux-x64-cpu/llama-server")
    model_path = Path("/models/llm/model.gguf")
    base_url = "http://127.0.0.1:8080"
    launch = {
        "ctx_size": "not_an_int",
        "warmup": "not_a_bool",
    }

    cmd = build_command(binary, model_path, base_url, launch)
    expected_warnings = (
        "unsupported launch value: ctx_size='not_an_int'",
        "unsupported launch value: warmup='not_a_bool'",
    )
    assert cmd.warnings == expected_warnings


def test_start_emits_event_on_adoption(tmp_path, monkeypatch):
    db_path = tmp_path / "awf.db"
    init_db(db_path)
    conn = get_connection(db_path)

    s = LlmServer(
        id="llama-server",
        managed=True,
        base_url="http://127.0.0.1:8080",
        openai_base_path="/v1",
        provider="openai",
        health_paths=("/health",),
        artifacts={},
        launch={},
        api_key_secret_name=None,
    )

    monkeypatch.setattr("awf.llm.sidecar.probe", lambda s: Health(reachable=True, reason="reachable"))

    status_obj = start(tmp_path, s, None, None, conn=conn)
    assert status_obj.state == "adopted"
    assert status_obj.adopted is True

    row = conn.execute(
        "SELECT * FROM events WHERE run_id = ? AND reason_code = 'llm_server_started'", (SYSTEM_RUN_ID,)
    ).fetchone()
    assert row is not None
    payload = json.loads(row["payload_json"])
    assert payload["server_id"] == "llama-server"
    assert payload["adopted"] is True

    # Stop adopted server should also log event and leave server running
    stop_status = stop(conn=conn)
    assert stop_status.state == "stopped"
    assert stop_status.adopted is True

    stop_row = conn.execute(
        "SELECT * FROM events WHERE run_id = ? AND reason_code = 'llm_server_stopped'", (SYSTEM_RUN_ID,)
    ).fetchone()
    assert stop_row is not None

    conn.close()


def test_probe_unreachable():
    s = LlmServer(
        id="test",
        managed=True,
        base_url="http://127.0.0.1:59999",
        openai_base_path="/v1",
        provider="openai",
        health_paths=("/health",),
        artifacts={},
        launch={},
        api_key_secret_name=None,
    )
    h = probe(s)
    assert h.reachable is False
