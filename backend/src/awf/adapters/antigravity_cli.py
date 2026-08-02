"""Google Antigravity CLI (`agy`) adapter (Section 10.2).

Required default configuration state: non-interactive/headless invocation
(`--print`) with an explicit approval mode set (`--mode accept-edits` -
never an implicit interactive default), native OS-level terminal sandbox
(`--sandbox`) enabled. `--dangerously-skip-permissions` MUST NOT be used
outside an explicit container/VM escalation.

`agy` does not bind to the caller's cwd by default - it writes into its own
scratch project unless `--add-dir <workspace_root> --new-project` is passed
(confirmed by probing the installed CLI; not documented in the spec text).
"""

import json
import subprocess

from awf.adapters.base import AgentInvocation, AgentResult, AgentStatus

DEFAULT_TIMEOUT_SECONDS = 300


class AntigravityAdapterError(RuntimeError):
    pass


def invoke(invocation: AgentInvocation) -> AgentResult:
    if invocation.constraints.get("dangerously_skip_permissions"):
        raise AntigravityAdapterError(
            "--dangerously-skip-permissions MUST NOT be used outside an explicit container/VM escalation"
        )
    mode = invocation.constraints.get("mode", "accept-edits")
    timeout_seconds = invocation.constraints.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS)

    command = [
        "agy",
        "--print", invocation.objective,
        "--mode", mode,
        "--sandbox",
        "--output-format", "json",
        "--add-dir", str(invocation.workspace_root),
        "--new-project",
    ]

    try:
        result = subprocess.run(
            command,
            cwd=invocation.workspace_root,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            stdin=subprocess.DEVNULL,
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

    if payload.get("status") != "SUCCESS":
        return AgentResult(
            status=AgentStatus.FAILED,
            output=payload,
            usage=payload.get("usage", {}),
            termination_reason=payload.get("error") or payload.get("status", "error"),
        )

    return AgentResult(
        status=AgentStatus.COMPLETED,
        output=payload,
        usage=payload.get("usage", {}),
        termination_reason="success",
    )
