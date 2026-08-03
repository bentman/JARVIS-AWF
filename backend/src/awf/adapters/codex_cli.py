"""OpenAI Codex CLI adapter (Section 10.2).

Required default configuration state: non-interactive invocation (`codex
exec`), `sandbox_mode` equivalent to `workspace-write`, `approval_policy`
equivalent to `on-request`, sourced from a named profile committed to the
repository (`config/codex/awf-default.toml`) rather than the operator's home
directory, so it travels with `config/`. `--dangerously-bypass-approvals-and-sandbox`
and `danger-full-access` MUST NOT be used outside an explicit container/VM
escalation.

Codex's own `--profile` flag layers a file from `$CODEX_HOME` (where auth
also lives, confirmed via `codex exec --help`) - it cannot point at an
arbitrary repo path without also relocating auth. This adapter instead loads
the repo-committed TOML file directly and applies its keys as `-c
key=value` overrides, which is the mechanism Codex documents for setting
these same values non-interactively.
"""

import json
import os
import subprocess
import tomllib
from pathlib import Path

from awf.adapters.base import AgentInvocation, AgentResult, AgentStatus

DEFAULT_TIMEOUT_SECONDS = 300
DANGER_SANDBOX_MODE = "danger-full-access"
DEFAULT_PROFILE_PATH = Path(__file__).resolve().parents[4] / "config" / "codex" / "awf-default.toml"


class CodexAdapterError(RuntimeError):
    pass


def _load_profile(path: Path) -> dict:
    with path.open("rb") as profile_file:
        return tomllib.load(profile_file)


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
    profile_path = invocation.constraints.get("profile_path", DEFAULT_PROFILE_PATH)
    profile = _load_profile(profile_path)

    sandbox_mode = invocation.constraints.get("sandbox_mode", profile.get("sandbox_mode", "workspace-write"))
    if sandbox_mode == DANGER_SANDBOX_MODE and not invocation.constraints.get("container_escalation"):
        raise CodexAdapterError(
            "danger-full-access sandbox_mode MUST NOT be used outside an explicit container/VM escalation"
        )
    approval_policy = invocation.constraints.get(
        "approval_policy", profile.get("approval_policy", "on-request")
    )
    timeout_seconds = invocation.constraints.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS)

    command = [
        "codex", "exec", invocation.objective,
        "-s", sandbox_mode,
        "-c", f"approval_policy={approval_policy}",
        "--json",
    ]
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
