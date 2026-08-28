"""GitHub Copilot CLI adapter (Section 10.2).

Required default configuration state: non-interactive invocation (`-p`),
explicit `--allow-tool` entries only. `--allow-all`/`--yolo` MUST NOT be used
by AWF's default profile. This adapter's permission model is
application-level and advisory, not OS-enforced (Section 10.3): a
repo-scoped `preToolUse` hook is generated for each invocation when AWF run
context is available.

JSONL events are typed `session.*`/`user.*`/`assistant.*`, terminated by one
`result` event carrying `exitCode` and `usage.codeChanges.filesModified`.
Success/failure is determined primarily by the process exit code, not event
contents.

`constraints["model_override"]` (ADR-0005), when set, is passed through
`--model`.
"""

import json
import subprocess
import sys
from pathlib import Path

from awf.adapters.base import AgentInvocation, AgentResult, AgentStatus, parse_jsonl_events, run_cli

DEFAULT_TIMEOUT_SECONDS = 300
DEFAULT_ALLOWED_TOOLS = ("write",)
FORBIDDEN_CONSTRAINT_KEYS = ("allow_all", "yolo")
HOOK_CONFIG_RELATIVE = Path(".github/hooks/awf-copilot-guard.json")
HOOK_BASH_RELATIVE = Path(".github/hooks/scripts/awf-pre-tool-use.sh")
HOOK_POWERSHELL_RELATIVE = Path(".github/hooks/scripts/awf-pre-tool-use.ps1")


class CopilotAdapterError(RuntimeError):
    pass


def _final_assistant_message(events: list[dict]) -> str | None:
    for event in reversed(events):
        if event.get("type") == "assistant.message":
            return event.get("data", {}).get("content")
    return None


def _write_hook_files(workspace_root: Path) -> tuple[Path, ...]:
    paths = (
        workspace_root / HOOK_CONFIG_RELATIVE,
        workspace_root / HOOK_BASH_RELATIVE,
        workspace_root / HOOK_POWERSHELL_RELATIVE,
    )
    existing = [path.relative_to(workspace_root).as_posix() for path in paths if path.exists()]
    if existing:
        raise CopilotAdapterError(f"refusing to overwrite existing Copilot hook files: {', '.join(existing)}")

    for path in paths:
        path.parent.mkdir(parents=True, exist_ok=True)
    paths[0].write_text(
        json.dumps(
            {
                "version": 1,
                "hooks": {
                    "preToolUse": [
                        {
                            "type": "command",
                            "bash": "./scripts/awf-pre-tool-use.sh",
                            "powershell": "./scripts/awf-pre-tool-use.ps1",
                            "cwd": ".github/hooks",
                            "timeoutSec": 15,
                        }
                    ]
                },
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    paths[1].write_text(
        '#!/usr/bin/env bash\nset -euo pipefail\n"${AWF_HOOK_PYTHON:-python3}" -m awf.adapters.copilot_guard_hook\n',
        encoding="utf-8",
    )
    paths[1].chmod(0o755)
    paths[2].write_text(
        '$ErrorActionPreference = "Stop"\n'
        '$python = if ($env:AWF_HOOK_PYTHON) { $env:AWF_HOOK_PYTHON } else { "python" }\n'
        "& $python -m awf.adapters.copilot_guard_hook\n"
        "exit $LASTEXITCODE\n",
        encoding="utf-8",
    )
    return paths


def _cleanup_hook_files(workspace_root: Path, paths: tuple[Path, ...]) -> None:
    for path in paths:
        path.unlink(missing_ok=True)
    for relative in (Path(".github/hooks/scripts"), Path(".github/hooks"), Path(".github")):
        directory = workspace_root / relative
        try:
            directory.rmdir()
        except OSError:
            pass


def _guard_env(invocation: AgentInvocation) -> dict[str, str]:
    context = invocation.trace_context.get("awf_guard", {})
    if not context:
        return {}
    env = {
        "AWF_HOOK_PYTHON": sys.executable,
        "AWF_REPO_ROOT": str(context["repo_root"]),
        "AWF_RUN_ID": str(context["run_id"]),
        "AWF_STEP_ID": str(context.get("step_id", "")),
        "AWF_ACTOR": str(context.get("actor", "copilot")),
        "AWF_AGENT_ALLOWLIST": json.dumps(context.get("agent_allowlist", [])),
    }
    if context.get("role"):
        env["AWF_ROLE"] = str(context["role"])
    tool_capabilities = invocation.constraints.get("copilot_tool_capabilities")
    if tool_capabilities:
        env["AWF_COPILOT_TOOL_CAPABILITIES"] = json.dumps(tool_capabilities)
    return env


def invoke(invocation: AgentInvocation) -> AgentResult:
    for key in FORBIDDEN_CONSTRAINT_KEYS:
        if invocation.constraints.get(key):
            raise CopilotAdapterError("--allow-all/--yolo MUST NOT be used by AWF's default profile")
    allowed_tools = invocation.constraints.get("allowed_tools", DEFAULT_ALLOWED_TOOLS)
    timeout_seconds = invocation.constraints.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS)

    command = ["copilot", "-p", invocation.objective, "--output-format", "json", "--no-color"]
    for tool in allowed_tools:
        command += ["--allow-tool", tool]
    model_override = invocation.constraints.get("model_override")
    if model_override:
        command += ["--model", model_override]
    command += list(invocation.constraints.get("mcp_extra_args", []))

    hook_paths: tuple[Path, ...] = ()
    guard_env = _guard_env(invocation)
    if guard_env:
        hook_paths = _write_hook_files(invocation.workspace_root)

    try:
        result = run_cli(
            command,
            invocation,
            timeout_seconds=timeout_seconds,
            extra_env=guard_env,
            run_fn=subprocess.run,
        )
        if isinstance(result, AgentResult):
            return result
    finally:
        if hook_paths:
            _cleanup_hook_files(invocation.workspace_root, hook_paths)

    events = parse_jsonl_events(result.stdout)

    if result.returncode != 0:
        return AgentResult(
            status=AgentStatus.FAILED,
            output={"events": events, "stdout": result.stdout, "stderr": result.stderr},
            termination_reason=f"exit code {result.returncode}",
        )

    return AgentResult(
        status=AgentStatus.COMPLETED,
        output={"result": _final_assistant_message(events), "events": events},
        termination_reason="success",
    )
