import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from awf.adapters.antigravity_cli import AntigravityAdapterError, invoke
from awf.adapters.base import AgentInvocation, AgentStatus


def make_invocation(**constraints) -> AgentInvocation:
    return AgentInvocation(
        objective="do the thing",
        inputs={},
        workspace_root=Path("/tmp/does-not-matter"),
        constraints=constraints,
    )


def test_invoke_builds_sandboxed_accept_edits_command_bound_to_workspace(monkeypatch):
    captured = {}

    def fake_run(command, cwd, capture_output, text, timeout, stdin, env):
        captured["command"] = command
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"status": "SUCCESS", "response": "done", "usage": {}}),
            stderr="",
        )

    monkeypatch.setattr("awf.adapters.antigravity_cli.subprocess.run", fake_run)

    result = invoke(make_invocation())

    assert captured["command"] == [
        "agy",
        "--print", "do the thing",
        "--mode", "accept-edits",
        "--sandbox",
        "--output-format", "json",
        "--add-dir", "/tmp/does-not-matter",
        "--new-project",
    ]
    assert result.status == AgentStatus.COMPLETED


def test_invoke_maps_error_status_to_failed(monkeypatch):
    def fake_run(command, cwd, capture_output, text, timeout, stdin, env):
        return SimpleNamespace(
            returncode=1,
            stdout=json.dumps({"status": "ERROR", "error": "invalid model"}),
            stderr="",
        )

    monkeypatch.setattr("awf.adapters.antigravity_cli.subprocess.run", fake_run)

    result = invoke(make_invocation())

    assert result.status == AgentStatus.FAILED
    assert result.termination_reason == "invalid model"


def test_invoke_refuses_dangerously_skip_permissions():
    with pytest.raises(AntigravityAdapterError):
        invoke(make_invocation(dangerously_skip_permissions=True))
