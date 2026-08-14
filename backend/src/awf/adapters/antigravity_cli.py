"""Google Antigravity CLI (`agy`) adapter (Section 10.2).

Required default configuration state: non-interactive/headless invocation
(`--print`) with an explicit approval mode set (`--mode accept-edits` -
never an implicit interactive default), native OS-level terminal sandbox
(`--sandbox`) enabled. `--dangerously-skip-permissions` MUST NOT be used
outside an explicit container/VM escalation.

`agy` does not bind to the caller's cwd by default - it writes into its own
scratch project unless `--add-dir <workspace_root> --new-project` is passed.

`agy` compiles in a headful-by-default Playwright browser tool suite
(`open_browser_url`, `read_browser_page`, `browser_click_element`, etc.),
reachable during a plain research objective and capable of opening a
visible window. `JETSKI_BROWSER_HEADLESS=true` forces headless without
disabling the tool outright - set unconditionally here, since a Run's
adapter subprocess must never surface a visible UI element on the
operator's desktop.

`constraints["model_override"]` (ADR-0005), when set, is passed through
`--model`.
"""

import json
import subprocess

from awf.adapters.base import AgentInvocation, AgentResult, AgentStatus, run_cli

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
        "--print",
        invocation.objective,
        "--mode",
        mode,
        "--sandbox",
        "--output-format",
        "json",
        "--add-dir",
        str(invocation.workspace_root),
        "--new-project",
    ]
    model_override = invocation.constraints.get("model_override")
    if model_override:
        command += ["--model", model_override]
    command += list(invocation.constraints.get("mcp_extra_args", []))

    result = run_cli(
        command,
        invocation,
        timeout_seconds=timeout_seconds,
        extra_env=REQUIRED_ENV,
        run_fn=subprocess.run,
    )
    if isinstance(result, AgentResult):
        return result

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
