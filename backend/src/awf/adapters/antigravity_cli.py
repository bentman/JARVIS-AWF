"""Google Antigravity CLI (`agy`) adapter (Section 10.2).

Required default configuration state: non-interactive/headless invocation
(`--print`) with an explicit approval mode set (`--mode accept-edits` -
never an implicit interactive default), native OS-level terminal sandbox
(`--sandbox`) enabled. `--dangerously-skip-permissions` MUST NOT be used
outside an explicit container/VM escalation.

`agy` does not bind to the caller's cwd by default - it writes into its own
scratch project unless `--add-dir <workspace_root> --new-project` is passed
(confirmed by probing the installed CLI; not documented in the spec text).

`agy` compiles in a real, headful-by-default Playwright browser tool suite
(`open_browser_url`, `read_browser_page`, `browser_click_element`, etc.) -
live-verified to be reachable during a plain research objective, popping a
real, visible window. `JETSKI_BROWSER_HEADLESS=true` (confirmed via the
installed CLI's own self-inspection) forces headless without disabling the
tool outright - set unconditionally here, since a Run's adapter subprocess
must never surface a visible UI element on the operator's desktop.
"""

import json
import os
import subprocess

from awf.adapters.base import AgentInvocation, AgentResult, AgentStatus

DEFAULT_TIMEOUT_SECONDS = 300
REQUIRED_ENV = {"JETSKI_BROWSER_HEADLESS": "true"}


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
    command += list(invocation.constraints.get("mcp_extra_args", []))

    try:
        result = subprocess.run(
            command,
            cwd=invocation.workspace_root,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            stdin=subprocess.DEVNULL,
            env={**os.environ, **invocation.constraints.get("mcp_env_overlay", {}), **REQUIRED_ENV},
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
