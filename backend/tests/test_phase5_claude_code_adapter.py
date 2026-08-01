import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from awf.adapters.base import AgentInvocation, AgentStatus
from awf.adapters.claude_code import ClaudeCodeAdapterError, invoke


def make_invocation(**constraints) -> AgentInvocation:
    return AgentInvocation(
        objective="do the thing",
        inputs={},
        workspace_root=Path("/tmp/does-not-matter"),
        constraints=constraints,
    )


def test_invoke_builds_non_interactive_acceptedits_command(monkeypatch):
    captured = {}

    def fake_run(command, cwd, capture_output, text, timeout):
        captured["command"] = command
        captured["cwd"] = cwd
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"is_error": False, "result": "done", "subtype": "success"}),
            stderr="",
        )

    monkeypatch.setattr("awf.adapters.claude_code.subprocess.run", fake_run)

    result = invoke(make_invocation())

    assert captured["command"] == [
        "claude", "--print", "do the thing",
        "--permission-mode", "acceptEdits",
        "--output-format", "json",
    ]
    assert "--dangerously-skip-permissions" not in captured["command"]
    assert result.status == AgentStatus.COMPLETED
    assert result.termination_reason == "success"


def test_invoke_maps_is_error_to_failed(monkeypatch):
    def fake_run(command, cwd, capture_output, text, timeout):
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"is_error": True, "subtype": "error_max_turns"}),
            stderr="",
        )

    monkeypatch.setattr("awf.adapters.claude_code.subprocess.run", fake_run)

    result = invoke(make_invocation())

    assert result.status == AgentStatus.FAILED
    assert result.termination_reason == "error_max_turns"


def test_invoke_refuses_bypass_permissions():
    with pytest.raises(ClaudeCodeAdapterError):
        invoke(make_invocation(permission_mode="bypassPermissions"))


def test_invoke_handles_non_json_output(monkeypatch):
    def fake_run(command, cwd, capture_output, text, timeout):
        return SimpleNamespace(returncode=1, stdout="not json", stderr="boom")

    monkeypatch.setattr("awf.adapters.claude_code.subprocess.run", fake_run)

    result = invoke(make_invocation())

    assert result.status == AgentStatus.FAILED
    assert "non-JSON output" in result.termination_reason
