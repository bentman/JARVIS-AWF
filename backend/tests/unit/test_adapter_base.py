import signal
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

from awf.adapters.base import AgentInvocation, AgentStatus, run_cli


def test_run_cli_preflights_missing_binary():
    invocation = AgentInvocation(objective="do work", inputs={}, workspace_root=Path("."))

    result = run_cli(["definitely-not-an-awf-agent-cli"], invocation)

    assert result.status == AgentStatus.FAILED
    assert "awf doctor" in result.termination_reason


def test_run_cli_times_out_real_process(tmp_path):
    invocation = AgentInvocation(objective="do work", inputs={}, workspace_root=tmp_path)

    result = run_cli([sys.executable, "-c", "import time; time.sleep(10)"], invocation, timeout_seconds=1)

    assert result.status == AgentStatus.LIMIT_EXCEEDED
    assert "timed out after 1s" in result.termination_reason


def test_run_cli_timeout_signal_handling_windows(tmp_path, monkeypatch):
    invocation = AgentInvocation(objective="do work", inputs={}, workspace_root=tmp_path)
    fake_proc = MagicMock()
    fake_proc.pid = 9999
    fake_proc.communicate.side_effect = [
        subprocess.TimeoutExpired(cmd=["test"], timeout=1),
        ("", ""),
    ]
    mock_run = MagicMock()

    monkeypatch.setattr("awf.adapters.base._REAL_SUBPROCESS_POPEN", lambda *a, **k: fake_proc)
    monkeypatch.setattr("awf.adapters.base._REAL_SUBPROCESS_RUN", mock_run)
    monkeypatch.setattr("awf.adapters.base.os.name", "nt")

    result = run_cli([sys.executable, "-c", "pass"], invocation, timeout_seconds=1, run_fn=mock_run)

    assert result.status == AgentStatus.LIMIT_EXCEEDED
    mock_run.assert_called_with(
        ["taskkill", "/F", "/T", "/PID", "9999"],
        capture_output=True,
        text=True,
        timeout=5,
    )


def test_run_cli_timeout_signal_handling_posix(tmp_path, monkeypatch):
    invocation = AgentInvocation(objective="do work", inputs={}, workspace_root=tmp_path)
    fake_proc = MagicMock()
    fake_proc.pid = 9999
    fake_proc.communicate.side_effect = [
        subprocess.TimeoutExpired(cmd=["test"], timeout=1),
        ("", ""),
    ]
    mock_killpg = MagicMock()

    monkeypatch.setattr("awf.adapters.base._REAL_SUBPROCESS_POPEN", lambda *a, **k: fake_proc)
    monkeypatch.setattr("awf.adapters.base.os.name", "posix")
    monkeypatch.setattr("awf.adapters.base.os.killpg", mock_killpg, raising=False)
    monkeypatch.setattr("awf.adapters.base.os.getpgid", lambda pid: 12345, raising=False)

    result = run_cli([sys.executable, "-c", "pass"], invocation, timeout_seconds=1)

    assert result.status == AgentStatus.LIMIT_EXCEEDED
    mock_killpg.assert_called_with(12345, signal.SIGTERM)
