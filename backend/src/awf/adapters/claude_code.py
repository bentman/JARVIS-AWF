"""Claude Code adapter (Section 10.2): the Phase 5 reference adapter.

Required default configuration state: non-interactive invocation (`--print`),
permission mode equivalent to `acceptEdits`. `--dangerously-skip-permissions`
/ `bypassPermissions` MUST NOT be used outside an explicit container/VM
escalation - this adapter never passes it.

`constraints["model_override"]` (ADR-0005), when set, is passed through
`--model` - confirmed real and live-tested against the installed CLI.
"""

import json
import os
import subprocess

from awf.adapters.base import AgentInvocation, AgentResult, AgentStatus

DEFAULT_TIMEOUT_SECONDS = 300
FORBIDDEN_PERMISSION_MODE = "bypassPermissions"


class ClaudeCodeAdapterError(RuntimeError):
    pass


def invoke(invocation: AgentInvocation) -> AgentResult:
    permission_mode = invocation.constraints.get("permission_mode", "acceptEdits")
    if permission_mode == FORBIDDEN_PERMISSION_MODE:
        raise ClaudeCodeAdapterError(
            "bypassPermissions MUST NOT be used outside an explicit container/VM escalation"
        )
    timeout_seconds = invocation.constraints.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS)

    command = [
        "claude",
        "--print",
        invocation.objective,
        "--permission-mode", permission_mode,
        "--output-format", "json",
    ]
    model_override = invocation.constraints.get("model_override")
    if model_override:
        command += ["--model", model_override]
    command += list(invocation.constraints.get("mcp_extra_args", []))

    try:
        result = subprocess.run(
            command,
            cwd=invocation.workspace_root,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            env={**os.environ, **invocation.constraints.get("mcp_env_overlay", {})},
        )
    except subprocess.TimeoutExpired:
        return AgentResult(
            status=AgentStatus.LIMIT_EXCEEDED,
            output={},
            termination_reason=f"timed out after {timeout_seconds}s",
        )

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        return AgentResult(
            status=AgentStatus.FAILED,
            output={"stdout": result.stdout, "stderr": result.stderr},
            termination_reason=f"non-JSON output: {exc}",
        )

    if payload.get("is_error"):
        return AgentResult(
            status=AgentStatus.FAILED,
            output=payload,
            usage=payload.get("usage", {}),
            termination_reason=payload.get("subtype", "error"),
        )

    return AgentResult(
        status=AgentStatus.COMPLETED,
        output=payload,
        usage=payload.get("usage", {}),
        termination_reason=payload.get("subtype", "success"),
    )
