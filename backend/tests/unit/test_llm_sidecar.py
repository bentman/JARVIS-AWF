"""Unit tests for LLM sidecar command construction and probing (ADR-0017)."""

import json
from pathlib import Path

from awf.db.bootstrap import init_db
from awf.db.connection import get_connection
from awf.hardware.profiler import SYSTEM_RUN_ID
from awf.llm.discovery import LocalModel
from awf.llm.servers import Artifact, LlmServer
from awf.llm.sidecar import Health, build_command, probe, start, status, stop


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


def test_detached_start_persists_status_for_later_cli_process(tmp_path, monkeypatch):
    db_path = tmp_path / "awf.db"
    init_db(db_path)
    conn = get_connection(db_path)

    binary = tmp_path / "runtimes" / "llama.cpp" / "linux-x64-cpu" / "llama-server"
    binary.parent.mkdir(parents=True)
    binary.write_text("bin")
    model_path = tmp_path / "models" / "llm" / "demo" / "demo.gguf"
    model_path.parent.mkdir(parents=True)
    model_path.write_text("model")

    server = LlmServer(
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
    artifact = Artifact(
        profile_id="linux-x64-cpu",
        url="https://example.test/cpu.tar.gz",
        archive="tar_gz",
        binary="llama-server",
        accelerator="cpu",
        launch={},
    )
    model = LocalModel(name="demo", files=(model_path,), primary=model_path)

    probes = iter([Health(False, "not yet"), Health(True, "ready"), Health(True, "ready")])
    monkeypatch.setattr("awf.llm.sidecar.probe", lambda _server: next(probes))

    class FakeProcess:
        pid = 12345
        returncode = None

        def poll(self):
            return None

    captured = {}

    def fake_popen(argv, **kwargs):
        captured["argv"] = argv
        captured["kwargs"] = kwargs
        return FakeProcess()

    monkeypatch.setattr("awf.llm.sidecar.subprocess.Popen", fake_popen)
    monkeypatch.setattr("awf.llm.sidecar._pid_alive", lambda pid: pid == 12345)

    st = start(tmp_path, server, artifact, model, conn=conn, detach=True)

    assert st.state == "running"
    assert st.pid == 12345
    assert captured["kwargs"]["start_new_session"] is True
    assert status(server, repo_root=tmp_path).state == "running"
    conn.close()


def test_stop_uses_persisted_detached_pid(tmp_path, monkeypatch):
    state_dir = tmp_path / "cache" / "llm"
    state_dir.mkdir(parents=True)
    (state_dir / "sidecar.json").write_text(
        json.dumps(
            {
                "state": "running",
                "server_id": "llama-server",
                "base_url": "http://127.0.0.1:8080",
                "model_path": "/models/demo.gguf",
                "profile_id": "linux-x64-cpu",
                "pid": 12345,
                "adopted": False,
                "warnings": [],
                "reason": None,
            }
        )
    )
    alive = {12345}
    signals = []

    def fake_alive(pid):
        return pid in alive

    def fake_kill(pid, sig):
        signals.append((pid, sig))
        alive.discard(pid)

    monkeypatch.setattr("awf.llm.sidecar._pid_alive", fake_alive)
    monkeypatch.setattr("awf.llm.sidecar.os.kill", fake_kill)

    st = stop(repo_root=tmp_path)

    assert st.state == "stopped"
    assert st.pid == 12345
    assert signals
    assert not (state_dir / "sidecar.json").exists()
