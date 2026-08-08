"""Cline CLI adapter (Section 10.2).

Required default configuration state: non-interactive invocation (`--json`,
NDJSON streaming) with `--auto-approve true`, so a non-TTY subprocess never
blocks on an approval prompt (`--auto-approve false` would *deny* required
approvals in a non-TTY terminal). `--yolo` / `--dangerously-skip-permissions`
MUST NOT be used outside an explicit container/VM escalation - this adapter
never passes them.

Cline reads MCP config from `~/.cline/cline_mcp_settings.json` (the default
`--config` directory, under `$HOME`) and state from `~/.cline/data`. With the
throwaway `HOME` override that `engine.agent_step._apply_mcp` already sets
for Antigravity, `~/.cline` resolves under the isolated scratch `HOME` - no
per-invocation `--config` flag is needed.

JSON parsing contract (pinned against observed `cline --json` output): the
stream is NDJSON with top-level `run_result` (carrying `finishReason`,
`usage`, and the final `text`), `error` (a fatal `message`), `agent_event`
(wrapping inner `iteration_*`/`error` events), and `hook_event`. Cline reports
internal failures in the stream and returns exit code 0 even then, so this
adapter treats a top-level `error` event, or a `run_result` whose
`finishReason` is not a success term, as a failure - the exit code alone is
not sufficient.

`constraints["model_override"]` (ADR-0005), when set, is passed through `-m`.
"""

import json
import os
import subprocess

from awf.adapters.base import AgentInvocation, AgentResult, AgentStatus

DEFAULT_TIMEOUT_SECONDS = 300
FORBIDDEN_CONSTRAINT_KEYS = ("yolo", "dangerously_skip_permissions")
_SUCCESS_FINISH_REASONS = {"done", "success", "successful", "completed"}


class ClineAdapterError(RuntimeError):
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


def _fatal_error_message(events: list[dict]) -> str | None:
    for event in events:
        if event.get("type") == "error":
            message = event.get("message")
            if message:
                return message
    return None


def _run_result(events: list[dict]) -> dict | None:
    for event in events:
        if event.get("type") == "run_result":
            return event
    return None


def _is_success_finish_reason(finish_reason: str) -> bool:
    return finish_reason.lower() in _SUCCESS_FINISH_REASONS


def invoke(invocation: AgentInvocation) -> AgentResult:
    for key in FORBIDDEN_CONSTRAINT_KEYS:
        if invocation.constraints.get(key):
            raise ClineAdapterError(
                "--yolo/--dangerously-skip-permissions MUST NOT be used by AWF's default profile"
            )
    timeout_seconds = invocation.constraints.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS)

    command = [
        "cline",
        invocation.objective,
        "--json",
        "--auto-approve", "true",
        "--cwd", str(invocation.workspace_root),
    ]
    model_override = invocation.constraints.get("model_override")
    if model_override:
        command += ["-m", model_override]
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
    fatal_message = _fatal_error_message(events)
    run_result = _run_result(events)
    finish_reason = (run_result or {}).get("finishReason", "") if run_result else ""
    usage = (run_result or {}).get("usage", {}) if run_result else {}

    if fatal_message:
        return AgentResult(
            status=AgentStatus.FAILED,
            output={"events": events, "stdout": result.stdout, "stderr": result.stderr},
            usage=usage,
            termination_reason=fatal_message,
        )

    if result.returncode != 0:
        return AgentResult(
            status=AgentStatus.FAILED,
            output={"events": events, "stdout": result.stdout, "stderr": result.stderr},
            usage=usage,
            termination_reason=f"exit code {result.returncode}",
        )

    if run_result is None or not _is_success_finish_reason(finish_reason):
        reason = f"finishReason={finish_reason}" if finish_reason else "no run_result event"
        return AgentResult(
            status=AgentStatus.FAILED,
            output={"events": events, "stdout": result.stdout, "stderr": result.stderr},
            usage=usage,
            termination_reason=reason,
        )

    return AgentResult(
        status=AgentStatus.COMPLETED,
        output={"result": (run_result or {}).get("text", ""), "events": events},
        usage=usage,
        termination_reason="success",
    )
