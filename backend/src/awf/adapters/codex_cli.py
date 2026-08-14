"""OpenAI Codex CLI adapter (Section 10.2).

Required default configuration state: non-interactive invocation (`codex
exec`), `sandbox_mode` equivalent to `workspace-write`, `approval_policy`
equivalent to `on-request`, sourced from a named profile committed to the
repository (`config/codex/awf-default.toml`) rather than the operator's home
directory, so it travels with `config/`. `--dangerously-bypass-approvals-and-sandbox`
and `danger-full-access` MUST NOT be used outside an explicit container/VM
escalation.

Codex's own `--profile` flag layers a file from `$CODEX_HOME`, where auth
also lives - it cannot point at an arbitrary repo path without also
relocating auth. This adapter instead loads the repo-committed TOML file
directly and applies its keys as `-c key=value` overrides, which is the
mechanism Codex documents for setting these same values non-interactively.

`constraints["model_override"]` (ADR-0005), when set, is passed through
`-m/--model`. Codex's `--local-provider` flag (paired with `--oss`) only
accepts `lmstudio`/`ollama`, not an arbitrary OpenAI-compatible `api_base` -
so when the winning candidate's `provider` is `ollama`
(`constraints["model_override_provider"]`), this adapter also passes `--oss
--local-provider ollama` to force Codex's own reasoning through that local
backend; any other provider (including a custom local `api_base`, e.g.
`llama-server`) gets plain `-m <model>` only, since Codex has no flag to
point `--local-provider` at an arbitrary endpoint.
"""

import subprocess
import tomllib
from pathlib import Path

from awf.adapters.base import AgentInvocation, AgentResult, AgentStatus, parse_jsonl_events, run_cli
from awf.paths import REPO_ROOT

DEFAULT_TIMEOUT_SECONDS = 300
DANGER_SANDBOX_MODE = "danger-full-access"
DEFAULT_PROFILE_PATH = REPO_ROOT / "config" / "codex" / "awf-default.toml"


class CodexAdapterError(RuntimeError):
    pass


def _load_profile(path: Path) -> dict:
    with path.open("rb") as profile_file:
        return tomllib.load(profile_file)


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
    approval_policy = invocation.constraints.get("approval_policy", profile.get("approval_policy", "on-request"))
    timeout_seconds = invocation.constraints.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS)

    command = [
        "codex",
        "exec",
        invocation.objective,
        "-s",
        sandbox_mode,
        "-c",
        f"approval_policy={approval_policy}",
        "--json",
    ]
    model_override = invocation.constraints.get("model_override")
    if model_override:
        if invocation.constraints.get("model_override_provider") == "ollama":
            command += ["--oss", "--local-provider", "ollama"]
        command += ["-m", model_override]
    command += list(invocation.constraints.get("mcp_extra_args", []))

    result = run_cli(command, invocation, timeout_seconds=timeout_seconds, run_fn=subprocess.run)
    if isinstance(result, AgentResult):
        return result

    events = parse_jsonl_events(result.stdout)
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
