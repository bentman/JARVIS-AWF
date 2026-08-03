"""GitHub Copilot CLI adapter (Section 10.2).

Required default configuration state: non-interactive invocation (`-p`),
explicit `--allow-tool` entries only. `--allow-all`/`--yolo` MUST NOT be used
by AWF's default profile. This adapter's permission model is
application-level and advisory, not OS-enforced (Section 10.3): a
`preToolUse` hook wired to the Capability Guard belongs to a future revision
of this module, not the Guard itself.

JSONL events are typed `session.*`/`user.*`/`assistant.*`, terminated by one
`result` event carrying `exitCode` and `usage.codeChanges.filesModified`.
Success/failure is determined primarily by the process exit code, not event
contents.
"""

import json
import os
import subprocess

from awf.adapters.base import AgentInvocation, AgentResult, AgentStatus

DEFAULT_TIMEOUT_SECONDS = 300
DEFAULT_ALLOWED_TOOLS = ("write",)
FORBIDDEN_CONSTRAINT_KEYS = ("allow_all", "yolo")


class CopilotAdapterError(RuntimeError):
    pass


def _parse_events(stdout: str) -> list[dict]:
    events = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events


def _final_assistant_message(events: list[dict]) -> str | None:
    for event in reversed(events):
        if event.get("type") == "assistant.message":
            return event.get("data", {}).get("content")
    return None


def invoke(invocation: AgentInvocation) -> AgentResult:
    for key in FORBIDDEN_CONSTRAINT_KEYS:
        if invocation.constraints.get(key):
            raise CopilotAdapterError(
                "--allow-all/--yolo MUST NOT be used by AWF's default profile"
            )
    allowed_tools = invocation.constraints.get("allowed_tools", DEFAULT_ALLOWED_TOOLS)
    timeout_seconds = invocation.constraints.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS)

    command = ["copilot", "-p", invocation.objective, "--output-format", "json", "--no-color"]
    for tool in allowed_tools:
        command += ["--allow-tool", tool]
    command += list(invocation.constraints.get("mcp_extra_args", []))

    try:
        result = subprocess.run(
            command,
            cwd=invocation.workspace_root,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            stdin=subprocess.DEVNULL,
            env={**os.environ, **invocation.constraints.get("mcp_env_overlay", {})},
        )
    except subprocess.TimeoutExpired:
        return AgentResult(
            status=AgentStatus.LIMIT_EXCEEDED,
            output={},
            termination_reason=f"timed out after {timeout_seconds}s",
        )

    events = _parse_events(result.stdout)

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
