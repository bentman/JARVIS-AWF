import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from awf.adapters.base import AgentInvocation, AgentStatus
from awf.adapters.cline_cli import ClineAdapterError, invoke


def make_invocation(**constraints) -> AgentInvocation:
    return AgentInvocation(
        objective="do the thing",
        inputs={},
        workspace_root=Path("/tmp/does-not-matter"),
        constraints=constraints,
    )


def _run_result_event(text="done", finish_reason="done", usage=None):
    return {
        "ts": "2026-08-08T00:00:00.000Z",
        "type": "run_result",
        "finishReason": finish_reason,
        "iterations": 1,
        "usage": usage
        or {
            "inputTokens": 10,
            "outputTokens": 5,
            "cacheReadTokens": 0,
            "cacheWriteTokens": 0,
            "totalCost": 0.01,
        },
        "text": text,
    }


def test_invoke_builds_headless_command_and_no_yolo(monkeypatch):
    captured = {}

    def fake_run(command, cwd, capture_output, text, timeout, stdin, env):
        captured["command"] = command
        return SimpleNamespace(returncode=0, stdout=json.dumps(_run_result_event()), stderr="")

    monkeypatch.setattr("awf.adapters.cline_cli.subprocess.run", fake_run)

    result = invoke(make_invocation())

    assert captured["command"] == [
        "cline",
        "do the thing",
        "--json",
        "--auto-approve",
        "true",
        "--cwd",
        "/tmp/does-not-matter",
    ]
    assert "--yolo" not in captured["command"]
    assert "--dangerously-skip-permissions" not in captured["command"]
    assert result.status == AgentStatus.COMPLETED
    assert result.output["result"] == "done"


def test_invoke_appends_model_override(monkeypatch):
    captured = {}

    def fake_run(command, cwd, capture_output, text, timeout, stdin, env):
        captured["command"] = command
        return SimpleNamespace(returncode=0, stdout=json.dumps(_run_result_event()), stderr="")

    monkeypatch.setattr("awf.adapters.cline_cli.subprocess.run", fake_run)

    invoke(make_invocation(model_override="anthropic/claude-sonnet-4-6"))

    assert "-m" in captured["command"]
    assert captured["command"][captured["command"].index("-m") + 1] == "anthropic/claude-sonnet-4-6"


def test_invoke_extracts_final_message_and_usage(monkeypatch):
    lines = [
        json.dumps({"ts": "t", "type": "agent_event", "event": {"type": "iteration_start", "iteration": 1}}),
        json.dumps(_run_result_event(text="final answer", usage={"inputTokens": 7, "outputTokens": 3})),
    ]

    def fake_run(command, cwd, capture_output, text, timeout, stdin, env):
        return SimpleNamespace(returncode=0, stdout="\n".join(lines), stderr="")

    monkeypatch.setattr("awf.adapters.cline_cli.subprocess.run", fake_run)

    result = invoke(make_invocation())

    assert result.output["result"] == "final answer"
    assert result.usage["inputTokens"] == 7
    assert result.usage["outputTokens"] == 3
    assert result.status == AgentStatus.COMPLETED


def test_invoke_maps_nonzero_exit_to_failed(monkeypatch):
    def fake_run(command, cwd, capture_output, text, timeout, stdin, env):
        return SimpleNamespace(returncode=1, stdout="", stderr="cline: no such command")

    monkeypatch.setattr("awf.adapters.cline_cli.subprocess.run", fake_run)

    result = invoke(make_invocation())

    assert result.status == AgentStatus.FAILED
    assert "exit code 1" in result.termination_reason


def test_invoke_maps_stream_error_event_to_failed_even_with_zero_exit(monkeypatch):
    # Cline can return exit 0 while reporting a failure in the stream (e.g. auth).
    stdout = "\n".join(
        [
            json.dumps({"ts": "t", "type": "agent_event", "event": {"type": "error", "error": {"message": "boom"}}}),
            json.dumps({"ts": "t", "type": "error", "message": "Unauthorized: please re-authenticate"}),
        ]
    )

    def fake_run(command, cwd, capture_output, text, timeout, stdin, env):
        return SimpleNamespace(returncode=0, stdout=stdout, stderr="")

    monkeypatch.setattr("awf.adapters.cline_cli.subprocess.run", fake_run)

    result = invoke(make_invocation())

    assert result.status == AgentStatus.FAILED
    assert "Unauthorized" in result.termination_reason


def test_invoke_maps_non_success_finish_reason_to_failed(monkeypatch):
    stdout = json.dumps(_run_result_event(finish_reason="error", text=""))

    def fake_run(command, cwd, capture_output, text, timeout, stdin, env):
        return SimpleNamespace(returncode=0, stdout=stdout, stderr="")

    monkeypatch.setattr("awf.adapters.cline_cli.subprocess.run", fake_run)

    result = invoke(make_invocation())

    assert result.status == AgentStatus.FAILED
    assert "finishReason=error" in result.termination_reason


def test_invoke_maps_non_json_output_to_failed(monkeypatch):
    def fake_run(command, cwd, capture_output, text, timeout, stdin, env):
        return SimpleNamespace(returncode=0, stdout="not json at all", stderr="")

    monkeypatch.setattr("awf.adapters.cline_cli.subprocess.run", fake_run)

    result = invoke(make_invocation())

    assert result.status == AgentStatus.FAILED
    assert "no run_result event" in result.termination_reason


def test_invoke_maps_timeout_to_limit_exceeded(monkeypatch):
    import subprocess as _subprocess

    def fake_run(command, cwd, capture_output, text, timeout, stdin, env):
        raise _subprocess.TimeoutExpired(command, timeout=timeout)

    monkeypatch.setattr("awf.adapters.cline_cli.subprocess.run", fake_run)

    result = invoke(make_invocation())

    assert result.status == AgentStatus.LIMIT_EXCEEDED
    assert "timed out" in result.termination_reason


def test_invoke_refuses_yolo_constraint():
    with pytest.raises(ClineAdapterError):
        invoke(make_invocation(yolo=True))


def test_invoke_refuses_dangerously_skip_permissions_constraint():
    with pytest.raises(ClineAdapterError):
        invoke(make_invocation(dangerously_skip_permissions=True))
