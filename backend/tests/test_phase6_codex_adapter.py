import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from awf.adapters.base import AgentInvocation, AgentStatus
from awf.adapters.codex_cli import DEFAULT_PROFILE_PATH, CodexAdapterError, invoke


def make_invocation(**constraints) -> AgentInvocation:
    return AgentInvocation(
        objective="do the thing",
        inputs={},
        workspace_root=Path("/tmp/does-not-matter"),
        constraints=constraints,
    )


def jsonl(*events) -> str:
    return "\n".join(json.dumps(e) for e in events)


def test_invoke_builds_workspace_write_on_request_command(monkeypatch):
    captured = {}

    def fake_run(command, cwd, capture_output, text, timeout, stdin):
        captured["command"] = command
        return SimpleNamespace(
            returncode=0,
            stdout=jsonl(
                {"type": "thread.started"},
                {"type": "item.completed", "item": {"type": "agent_message", "text": "done"}},
                {"type": "turn.completed"},
            ),
            stderr="",
        )

    monkeypatch.setattr("awf.adapters.codex_cli.subprocess.run", fake_run)

    result = invoke(make_invocation())

    assert captured["command"] == [
        "codex", "exec", "do the thing",
        "-s", "workspace-write",
        "-c", "approval_policy=on-request",
        "--json",
    ]
    assert result.status == AgentStatus.COMPLETED
    assert result.output["result"] == "done"


def test_invoke_maps_turn_failed_to_failed(monkeypatch):
    def fake_run(command, cwd, capture_output, text, timeout, stdin):
        return SimpleNamespace(
            returncode=1,
            stdout=jsonl(
                {"type": "thread.started"},
                {"type": "turn.failed", "error": {"message": "boom"}},
            ),
            stderr="",
        )

    monkeypatch.setattr("awf.adapters.codex_cli.subprocess.run", fake_run)

    result = invoke(make_invocation())

    assert result.status == AgentStatus.FAILED
    assert result.termination_reason == "boom"


def test_default_profile_is_committed_to_the_repo_not_the_operators_home_dir():
    # Section 10.2: "a named profile committed to the repository (not the
    # operator's home directory) so it travels with config/".
    assert DEFAULT_PROFILE_PATH.is_file()
    assert "config/codex" in str(DEFAULT_PROFILE_PATH)
    assert ".codex" not in DEFAULT_PROFILE_PATH.parts  # not $CODEX_HOME


def test_invoke_sources_sandbox_defaults_from_the_committed_profile(monkeypatch, tmp_path):
    captured = {}

    def fake_run(command, cwd, capture_output, text, timeout, stdin):
        captured["command"] = command
        return SimpleNamespace(returncode=0, stdout=jsonl({"type": "turn.completed"}), stderr="")

    monkeypatch.setattr("awf.adapters.codex_cli.subprocess.run", fake_run)

    custom_profile = tmp_path / "custom.toml"
    custom_profile.write_text('sandbox_mode = "read-only"\napproval_policy = "never"\n')

    result = invoke(make_invocation(profile_path=custom_profile))

    assert result.status == AgentStatus.COMPLETED
    assert captured["command"] == [
        "codex", "exec", "do the thing",
        "-s", "read-only",
        "-c", "approval_policy=never",
        "--json",
    ]


def test_invoke_refuses_danger_full_access_without_escalation():
    with pytest.raises(CodexAdapterError):
        invoke(make_invocation(sandbox_mode="danger-full-access"))


def test_invoke_allows_danger_full_access_with_explicit_escalation(monkeypatch):
    captured = {}

    def fake_run(command, cwd, capture_output, text, timeout, stdin):
        captured["command"] = command
        return SimpleNamespace(
            returncode=0,
            stdout=jsonl({"type": "turn.completed"}),
            stderr="",
        )

    monkeypatch.setattr("awf.adapters.codex_cli.subprocess.run", fake_run)

    result = invoke(make_invocation(sandbox_mode="danger-full-access", container_escalation=True))
    assert result.status == AgentStatus.COMPLETED
    assert captured["command"] == [
        "codex", "exec", "do the thing",
        "-s", "danger-full-access",
        "-c", "approval_policy=on-request",
        "--json",
    ]
