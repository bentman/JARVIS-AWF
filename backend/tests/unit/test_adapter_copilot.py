import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from awf.adapters.base import AgentInvocation, AgentStatus
from awf.adapters.copilot_cli import CopilotAdapterError, invoke


def make_invocation(**constraints) -> AgentInvocation:
    return AgentInvocation(
        objective="do the thing",
        inputs={},
        workspace_root=Path("/tmp/does-not-matter"),
        constraints=constraints,
    )


def make_guarded_invocation(workspace_root: Path, repo_root: Path) -> AgentInvocation:
    return AgentInvocation(
        objective="do the thing",
        inputs={},
        workspace_root=workspace_root,
        constraints={},
        trace_context={
            "awf_guard": {
                "repo_root": str(repo_root),
                "run_id": "run-1",
                "step_id": "step-1",
                "actor": "copilot",
                "agent_allowlist": ["fs_write@1.0.0"],
                "role": "builder",
            }
        },
    )


def test_invoke_builds_explicit_allow_tool_command_no_yolo(monkeypatch):
    captured = {}

    def fake_run(command, cwd, capture_output, text, timeout, stdin, env):
        captured["command"] = command
        return SimpleNamespace(returncode=0, stdout='{"type":"done"}', stderr="")

    monkeypatch.setattr("awf.adapters.copilot_cli.subprocess.run", fake_run)

    result = invoke(make_invocation())

    assert captured["command"] == [
        "copilot",
        "-p",
        "do the thing",
        "--output-format",
        "json",
        "--no-color",
        "--allow-tool",
        "write",
    ]
    assert "--yolo" not in captured["command"]
    assert "--allow-all" not in captured["command"]
    assert result.status == AgentStatus.COMPLETED


def test_invoke_writes_copilot_pre_tool_use_hook_when_guard_context_exists(monkeypatch, tmp_path, repo_root):
    captured = {}

    def fake_run(command, cwd, capture_output, text, timeout, stdin, env):
        workspace_root = Path(cwd)
        captured["env"] = env
        assert (workspace_root / ".github/hooks/awf-copilot-guard.json").is_file()
        assert (workspace_root / ".github/hooks/scripts/awf-pre-tool-use.sh").is_file()
        assert (workspace_root / ".github/hooks/scripts/awf-pre-tool-use.ps1").is_file()
        return SimpleNamespace(returncode=0, stdout='{"type":"done"}', stderr="")

    monkeypatch.setattr("awf.adapters.copilot_cli.subprocess.run", fake_run)

    result = invoke(make_guarded_invocation(tmp_path, repo_root))

    assert result.status == AgentStatus.COMPLETED
    assert captured["env"]["AWF_RUN_ID"] == "run-1"
    assert json.loads(captured["env"]["AWF_AGENT_ALLOWLIST"]) == ["fs_write@1.0.0"]
    assert not (tmp_path / ".github/hooks/awf-copilot-guard.json").exists()
    assert not (tmp_path / ".github/hooks/scripts/awf-pre-tool-use.sh").exists()


def test_invoke_refuses_to_overwrite_existing_copilot_hook(tmp_path, repo_root):
    hook_path = tmp_path / ".github/hooks/awf-copilot-guard.json"
    hook_path.parent.mkdir(parents=True)
    hook_path.write_text("{}", encoding="utf-8")

    with pytest.raises(CopilotAdapterError, match="refusing to overwrite"):
        invoke(make_guarded_invocation(tmp_path, repo_root))


def test_invoke_appends_model_override(monkeypatch):
    captured = {}

    def fake_run(command, cwd, capture_output, text, timeout, stdin, env):
        captured["command"] = command
        return SimpleNamespace(returncode=0, stdout='{"type":"done"}', stderr="")

    monkeypatch.setattr("awf.adapters.copilot_cli.subprocess.run", fake_run)

    invoke(make_invocation(model_override="gpt-5.4"))

    assert "--model" in captured["command"]
    assert captured["command"][captured["command"].index("--model") + 1] == "gpt-5.4"


def test_invoke_extracts_final_assistant_message(monkeypatch):
    events = [
        {"type": "assistant.message", "data": {"content": "first"}},
        {"type": "assistant.message", "data": {"content": "final answer"}},
        {"type": "result", "exitCode": 0},
    ]
    stdout = "\n".join(json.dumps(e) for e in events)

    def fake_run(command, cwd, capture_output, text, timeout, stdin, env):
        return SimpleNamespace(returncode=0, stdout=stdout, stderr="")

    monkeypatch.setattr("awf.adapters.copilot_cli.subprocess.run", fake_run)

    result = invoke(make_invocation())

    assert result.output["result"] == "final answer"


def test_invoke_maps_nonzero_exit_to_failed(monkeypatch):
    def fake_run(command, cwd, capture_output, text, timeout, stdin, env):
        return SimpleNamespace(returncode=1, stdout="", stderr="Error: No authentication information found.")

    monkeypatch.setattr("awf.adapters.copilot_cli.subprocess.run", fake_run)

    result = invoke(make_invocation())

    assert result.status == AgentStatus.FAILED
    assert "exit code 1" in result.termination_reason


def test_invoke_refuses_yolo_constraint():
    with pytest.raises(CopilotAdapterError):
        invoke(make_invocation(yolo=True))


def test_invoke_refuses_allow_all_constraint():
    with pytest.raises(CopilotAdapterError):
        invoke(make_invocation(allow_all=True))
