"""Runs an Agent node as a durable Step (Section 12.2 node type, Section 10).

The worktree is committed only after the Step's `SUCCEEDED` status is
persisted to `steps` - never before, and never if the adapter didn't
complete (Phase 5 exit condition).
"""

import sqlite3
from pathlib import Path
from typing import Callable

from awf.adapters.base import AgentInvocation, AgentResult, AgentStatus
from awf.engine.executor import run_step
from awf.isolation.worktree import commit_all_changes

AdapterFn = Callable[[AgentInvocation], AgentResult]


class AgentStepError(RuntimeError):
    pass


def run_agent_step(
    conn: sqlite3.Connection,
    *,
    step_id: str,
    run_id: str,
    worktree_path: Path,
    invocation: AgentInvocation,
    adapter_fn: AdapterFn,
    commit_message: str,
) -> dict:
    def fn(_payload: dict) -> dict:
        result = adapter_fn(invocation)
        if result.status != AgentStatus.COMPLETED:
            raise AgentStepError(
                f"adapter did not complete: status={result.status.value} "
                f"reason={result.termination_reason!r}"
            )
        return {"status": result.status.value, "termination_reason": result.termination_reason}

    output = run_step(conn, step_id=step_id, run_id=run_id, fn=fn, input_payload={})
    # Reached only when `fn` returned without raising, meaning the Step's
    # SUCCEEDED status is already committed to `steps` (Section 13.2).
    # Only now is it safe to commit the worktree's changes.
    commit_sha = commit_all_changes(worktree_path, commit_message)
    return {**output, "commit_sha": commit_sha}
