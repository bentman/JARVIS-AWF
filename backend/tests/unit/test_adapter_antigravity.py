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
        captured["env"] = env
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"status": "SUCCESS", "response": "done", "usage": {}}),
            stderr="",
        )

    monkeypatch.setattr("awf.adapters.antigravity_cli.subprocess.run", fake_run)

    result = invoke(make_invocation())

    assert captured["command"] == [
        "agy",
        "--print",
        "do the thing",
        "--mode",
        "accept-edits",
        "--sandbox",
        "--output-format",
        "json",
        "--add-dir",
        str(Path("/tmp/does-not-matter")),
        "--new-project",
    ]
    assert result.status == AgentStatus.COMPLETED
    # a Run's adapter subprocess must never surface a visible UI element
    assert captured["env"]["JETSKI_BROWSER_HEADLESS"] == "true"


def test_invoke_appends_model_override(monkeypatch):
    captured = {}

    def fake_run(command, cwd, capture_output, text, timeout, stdin, env):
        captured["command"] = command
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"status": "SUCCESS", "response": "done", "usage": {}}),
            stderr="",
        )

    monkeypatch.setattr("awf.adapters.antigravity_cli.subprocess.run", fake_run)

    invoke(make_invocation(model_override="gemini-3-pro"))

    assert "--model" in captured["command"]
    assert captured["command"][captured["command"].index("--model") + 1] == "gemini-3-pro"


def test_invoke_forces_headless_browser_even_if_constraints_try_to_override(monkeypatch):
    env_capture = {}

    def fake_run(command, cwd, capture_output, text, timeout, stdin, env):
        env_capture["env"] = env
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"status": "SUCCESS", "response": "done", "usage": {}}),
            stderr="",
        )

    monkeypatch.setattr("awf.adapters.antigravity_cli.subprocess.run", fake_run)

    invoke(make_invocation(mcp_env_overlay={"JETSKI_BROWSER_HEADLESS": "false"}))

    assert env_capture["env"]["JETSKI_BROWSER_HEADLESS"] == "true"


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
