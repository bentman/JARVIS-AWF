"""Runs an Agent node as a durable Step (Section 12.2 node type, Section 10).

The worktree is committed only after the Step's `SUCCEEDED` status is
persisted to `steps` - never before, and never if the adapter didn't
complete. When `capability` is supplied, the Capability Guard (Section 9.2)
authorizes the action before the adapter runs; a DENY/APPROVAL_REQUIRED
decision fails the Step with `POLICY_DENIED` rather than proceeding.

`voice` (an Agent Manifest's `voice` ref, ADR-0002), when given, is folded
into the Step's own persisted output - not just the in-memory return value -
so a later `awf status`/`op_run_status` query can actually see which voice
a Step's output should be spoken in.
"""

import sqlite3
from pathlib import Path
from typing import Callable

from awf.adapters.base import AgentInvocation, AgentResult, AgentStatus
from awf.engine.executor import StepFailure, run_step
from awf.guard.capability_guard import Decision, authorize
from awf.isolation.worktree import commit_all_changes
from awf.registry.capability_record import CapabilityRecord

AdapterFn = Callable[[AgentInvocation], AgentResult]

AGENT_STATUS_FAILURE_CLASSES = {
    AgentStatus.FAILED: "TOOL_ERROR",
    AgentStatus.LIMIT_EXCEEDED: "TIMEOUT",
}


class AgentStepError(StepFailure):
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
    capability: CapabilityRecord | None = None,
    agent_allowlist: list[str] | None = None,
    role: str | None = None,
    actor: str = "agent",
    voice: str | None = None,
) -> dict:
    def fn(_payload: dict) -> dict:
        if capability is not None:
            # A real Agent Manifest's declared `capabilities` (ADR-0002) is
            # the caller-supplied allowlist; a caller with no manifest to
            # resolve (no `agentRef` on the node) falls back to a
            # self-permitting singleton, matching pre-ADR-0002 behavior.
            decision = authorize(
                conn,
                capability=capability,
                agent_allowlist=agent_allowlist if agent_allowlist is not None else [capability.ref],
                run_id=run_id,
                actor=actor,
                step_id=step_id,
                role=role,
            )
            if decision != Decision.ALLOW:
                raise AgentStepError(
                    f"blocked by Capability Guard: {decision.value}",
                    failure_class="POLICY_DENIED",
                )

        result = adapter_fn(invocation)
        if result.status != AgentStatus.COMPLETED:
            raise AgentStepError(
                f"adapter did not complete: status={result.status.value} "
                f"reason={result.termination_reason!r}",
                failure_class=AGENT_STATUS_FAILURE_CLASSES.get(result.status, "INTERNAL"),
            )
        output = {"status": result.status.value, "termination_reason": result.termination_reason}
        if voice is not None:
            output["voice"] = voice
        return output

    output = run_step(conn, step_id=step_id, run_id=run_id, fn=fn, input_payload={})
    # Reached only when `fn` returned without raising, meaning the Step's
    # SUCCEEDED status is already committed to `steps` (Section 13.2).
    # Only now is it safe to commit the worktree's changes.
    commit_sha = commit_all_changes(worktree_path, commit_message)
    return {**output, "commit_sha": commit_sha}
