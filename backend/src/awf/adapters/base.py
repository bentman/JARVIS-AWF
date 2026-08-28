"""Generic Agent Runtime Adapter contract (Section 10.1).

Every adapter - named or future - normalizes to these two envelopes.
`COMPLETED` means the invocation satisfied its completion contract; it does
NOT mean accepted - acceptance is computed by the Gate node (Section 12.3),
never by the agent itself.
"""

import inspect
import json
import os
import shutil
import signal
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class AgentStatus(Enum):
    COMPLETED = "COMPLETED"
    NEEDS_INPUT = "NEEDS_INPUT"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    LIMIT_EXCEEDED = "LIMIT_EXCEEDED"
    CANCELED = "CANCELED"


@dataclass(frozen=True)
class AgentInvocation:
    objective: str
    inputs: dict
    workspace_root: Path
    capabilities: tuple[str, ...] = ()
    skills: tuple[str, ...] = ()
    constraints: dict = field(default_factory=dict)
    completion_contract: str = ""
    trace_context: dict = field(default_factory=dict)


@dataclass(frozen=True)
class AgentResult:
    status: AgentStatus
    output: dict
    artifact_candidates: tuple[str, ...] = ()
    findings: tuple[dict, ...] = ()
    usage: dict = field(default_factory=dict)
    termination_reason: str = ""


DEFAULT_TIMEOUT_SECONDS = 300
RunFn = Callable[..., subprocess.CompletedProcess]
_REAL_SUBPROCESS_RUN = subprocess.run
_REAL_SUBPROCESS_POPEN = subprocess.Popen


def parse_jsonl_events(stdout: str) -> list[dict]:
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


def _accepts_kwarg(fn: RunFn, name: str) -> bool:
    try:
        signature = inspect.signature(fn)
    except (TypeError, ValueError):
        return True
    return name in signature.parameters or any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in signature.parameters.values()
    )


def run_cli(
    argv: list[str],
    invocation: AgentInvocation,
    *,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    extra_env: dict[str, str] | None = None,
    run_fn: RunFn = subprocess.run,
    preflight: bool = True,
) -> subprocess.CompletedProcess | AgentResult:
    if not argv:
        return AgentResult(
            status=AgentStatus.FAILED,
            output={},
            termination_reason="agent CLI command is empty",
        )

    executable = argv[0]
    if preflight and run_fn is _REAL_SUBPROCESS_RUN and shutil.which(executable) is None:
        return AgentResult(
            status=AgentStatus.FAILED,
            output={},
            termination_reason=f"agent CLI '{executable}' not installed - run `awf doctor` or select another adapter",
        )

    env = {**os.environ, **invocation.constraints.get("mcp_env_overlay", {})}
    env.update(invocation.constraints.get("skill_env_overlay", {}))
    if extra_env:
        env.update(extra_env)

    kwargs = {
        "cwd": invocation.workspace_root,
        "capture_output": True,
        "text": True,
        "env": env,
    }
    if _accepts_kwarg(run_fn, "stdin"):
        kwargs["stdin"] = subprocess.DEVNULL
    if run_fn is _REAL_SUBPROCESS_RUN:
        popen_kwargs = {
            "cwd": invocation.workspace_root,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "stdin": subprocess.DEVNULL,
            "text": True,
            "env": env,
        }
        if os.name == "nt":
            popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            popen_kwargs["start_new_session"] = True
        try:
            proc = _REAL_SUBPROCESS_POPEN(argv, **popen_kwargs)
        except FileNotFoundError:
            return AgentResult(
                status=AgentStatus.FAILED,
                output={},
                termination_reason=f"agent CLI '{executable}' not installed - run `awf doctor` or select another adapter",
            )
        try:
            stdout, stderr = proc.communicate(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            if os.name == "nt":
                _REAL_SUBPROCESS_RUN(
                    ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
            else:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                except OSError:
                    proc.kill()
            try:
                proc.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.communicate()
            return AgentResult(
                status=AgentStatus.LIMIT_EXCEEDED,
                output={},
                termination_reason=f"timed out after {timeout_seconds}s",
            )
        return subprocess.CompletedProcess(argv, proc.returncode, stdout, stderr)
    kwargs["timeout"] = timeout_seconds
    try:
        return run_fn(argv, **kwargs)
    except FileNotFoundError:
        return AgentResult(
            status=AgentStatus.FAILED,
            output={},
            termination_reason=f"agent CLI '{executable}' not installed - run `awf doctor` or select another adapter",
        )
    except subprocess.TimeoutExpired as exc:
        if os.name != "nt" and getattr(exc, "pid", None):
            try:
                os.killpg(os.getpgid(exc.pid), signal.SIGTERM)
            except OSError:
                pass
        return AgentResult(
            status=AgentStatus.LIMIT_EXCEEDED,
            output={},
            termination_reason=f"timed out after {timeout_seconds}s",
        )
