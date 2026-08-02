"""OpenAI Codex CLI adapter (Section 10.2).

Required default configuration state: non-interactive invocation (`codex
exec`), `sandbox_mode` equivalent to `workspace-write`, `approval_policy`
equivalent to `on-request`. `--dangerously-bypass-approvals-and-sandbox` and
`danger-full-access` MUST NOT be used outside an explicit container/VM
escalation.
"""

import json
import subprocess

from awf.adapters.base import AgentInvocation, AgentResult, AgentStatus

DEFAULT_TIMEOUT_SECONDS = 300
DANGER_SANDBOX_MODE = "danger-full-access"


class CodexAdapterError(RuntimeError):
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


def _final_agent_message(events: list[dict]) -> str | None:
    for event in reversed(events):
        item = event.get("item", {})
        if event.get("type") == "item.completed" and item.get("type") == "agent_message":
            return item.get("text")
    return None


def invoke(invocation: AgentInvocation) -> AgentResult:
    sandbox_mode = invocation.constraints.get("sandbox_mode", "workspace-write")
    if sandbox_mode == DANGER_SANDBOX_MODE and not invocation.constraints.get("container_escalation"):
        raise CodexAdapterError(
            "danger-full-access sandbox_mode MUST NOT be used outside an explicit container/VM escalation"
        )
    approval_policy = invocation.constraints.get("approval_policy", "on-request")
    timeout_seconds = invocation.constraints.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS)

    command = [
        "codex", "exec", invocation.objective,
        "-s", sandbox_mode,
        "-c", f"approval_policy={approval_policy}",
        "--json",
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

    events = _parse_events(result.stdout)
    failed_events = [e for e in events if e.get("type") == "turn.failed"]

    if result.returncode != 0 or failed_events:
        reason = (
            failed_events[-1].get("error", {}).get("message", "turn failed")
            if failed_events
            else f"exit code {result.returncode}"
        )
        return AgentResult(
            status=AgentStatus.FAILED,
            output={"events": events, "stderr": result.stderr},
            termination_reason=reason,
        )

    return AgentResult(
        status=AgentStatus.COMPLETED,
        output={"result": _final_agent_message(events), "events": events},
        termination_reason="success",
    )
