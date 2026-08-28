import sys
from pathlib import Path

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
