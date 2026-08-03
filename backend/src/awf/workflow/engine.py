"""Workflow engine (Section 12): executes a WorkflowDefinition as durable Steps.

`activity`, `agent`, `gate`, and `handoff` nodes are interpreted; `approval`,
`subworkflow`, `map`, and `loop` are validated as node shapes (Section 12.2,
in `workflow.nodes`) but have no execution semantics yet.

Branching is driven by two engine-specific node fields that are NOT part of
the Section 12.1 spec shape: `next` (the node id to run afterward; absent
means the workflow completes) and, on `gate` nodes, `onFail` (the node id to
jump to when the gate fails).

Any node executor MAY return `{"waiting_input": True, ...}` (the `handoff`
executor does this when it exhausts `maxHops` without its termination
condition being set, Section 13.4) - the engine stops there and returns
`status: "WAITING_INPUT"` without advancing to `next`, matching the "MUST
NOT silently continue or silently succeed" rule.

`handoff` nodes manage their own per-hop Steps internally (Section 13.4:
"each hop is a normal, durable Step") - the engine does not create a Step
row for the handoff node itself, only for `activity`/`agent`/`gate`.

Every `agent` node passes through the Capability Guard (Section 9.2) before
its adapter runs: a node MAY declare `capability: {name, version}` to
resolve a real, published Capability Record; one that doesn't gets a
conservative synthesized R1/approval-never record instead, so every
invocation is still authorized and logged, never skipped.

A Step that raises is caught here at the Run level: the Run is marked
`FAILED` and a clean result dict is returned, rather than letting the
exception propagate to the caller as an unhandled crash.
"""

import sqlite3
from pathlib import Path
from typing import Callable

from awf.adapters.base import AgentInvocation
from awf.clock import utc_now_rfc3339
from awf.engine.agent_step import run_agent_step
from awf.engine.run import create_step
from awf.events.writer import write_event
from awf.registry.capability_record import CapabilityRecord, Effects, Identity, load_capability_record
from awf.registry.resolve import resolve_registry_object
from awf.workflow.definition import WorkflowDefinition

NodeExecutor = Callable[[sqlite3.Connection, str, str, dict], dict]
AdapterFn = Callable[[AgentInvocation], "AgentResult"]

EXECUTABLE_NODE_TYPES = ("activity", "agent", "gate", "handoff")

# Node types that manage their own internal Step rows and should not get a
# generic outer Step created for them by the engine.
SELF_STEPPING_NODE_TYPES = ("handoff",)


class WorkflowEngineError(RuntimeError):
    pass


def _synthesized_capability_for_node(node: dict) -> CapabilityRecord:
    """A conservative stand-in Capability Record for an `agent` node that
    doesn't declare a real one - still real enough to be evaluated and
    logged by the Guard, never a rubber stamp."""
    return CapabilityRecord(
        identity=Identity(type="cli-adapter-action", provider=node["adapter"], name=f"agent_node_{node['id']}", version="0.0.0"),
        schema_input="",
        schema_output="",
        effects=Effects(operation="update", reversible=True, idempotent=False, external_side_effect=True),
        risk_class="R1",
        approval="never",
    )


def _resolve_node_capability(node: dict, repo_root: Path) -> CapabilityRecord:
    declared = node.get("capability")
    if not declared:
        return _synthesized_capability_for_node(node)
    path, _source = resolve_registry_object(repo_root, "capabilities", declared["name"], declared["version"])
    return load_capability_record(path)


def make_agent_node_executor(
    adapter_registry: dict[str, AdapterFn], worktree_path: Path, repo_root: Path
) -> NodeExecutor:
    def executor(conn: sqlite3.Connection, run_id: str, step_id: str, node: dict) -> dict:
        invocation = AgentInvocation(
            objective=node["objective"],
            inputs={},
            workspace_root=worktree_path,
            constraints=node.get("constraints", {}),
        )
        return run_agent_step(
            conn,
            step_id=step_id,
            run_id=run_id,
            worktree_path=worktree_path,
            invocation=invocation,
            adapter_fn=adapter_registry[node["adapter"]],
            commit_message=f"workflow: {node['id']}",
            capability=_resolve_node_capability(node, repo_root),
            role=node.get("role"),
            actor=node["adapter"],
        )

    return executor


def _mark_run_failed(conn: sqlite3.Connection, *, run_id: str, reason_code: str) -> None:
    conn.execute(
        "UPDATE runs SET status = 'FAILED', updated_at = ? WHERE run_id = ?",
        (utc_now_rfc3339(), run_id),
    )
    conn.commit()
    write_event(conn, run_id=run_id, new_status="FAILED", actor="engine", reason_code=reason_code)


def run_workflow_definition(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    workflow: WorkflowDefinition,
    node_executors: dict[str, NodeExecutor],
) -> dict:
    max_repairs = workflow.budgets.get("maxRepairIterations", 3)
    repairs_used = 0
    last_verdict_artifact_id = None
    attempt_counts: dict[str, int] = {}

    conn.execute(
        "UPDATE runs SET status = 'RUNNING', updated_at = ? WHERE run_id = ?",
        (utc_now_rfc3339(), run_id),
    )
    conn.commit()

    current_id = workflow.nodes[0]["id"]
    while current_id is not None:
        node = workflow.node(current_id)
        node_type = node["type"]
        if node_type not in EXECUTABLE_NODE_TYPES:
            raise WorkflowEngineError(
                f"node '{current_id}' (type={node_type}) has no execution semantics yet "
                f"(only {EXECUTABLE_NODE_TYPES} are executable in this phase)"
            )
        executor = node_executors.get(node_type)
        if executor is None:
            raise WorkflowEngineError(f"no executor registered for node type '{node_type}'")

        attempt_counts[current_id] = attempt_counts.get(current_id, 0) + 1
        # step_id is globally unique (Section 8: PRIMARY KEY) - scoped by
        # run_id, not just node id, since the same node id recurs across
        # different Runs of the same workflow.
        step_id = f"{run_id}:{current_id}#{attempt_counts[current_id]}"
        if node_type not in SELF_STEPPING_NODE_TYPES:
            create_step(conn, step_id=step_id, run_id=run_id, node_id=current_id, attempt=attempt_counts[current_id])

        try:
            output = executor(conn, run_id, step_id, node)
        except Exception as exc:
            # run_step (or the handoff executor's own per-hop run_step calls)
            # already recorded the Step's FAILED status and failure_class
            # before this propagated - this is the Run-level consequence.
            _mark_run_failed(conn, run_id=run_id, reason_code=f"step_failed:{exc}")
            return {"status": "FAILED", "repairs_used": repairs_used, "error": str(exc)}

        if output.get("waiting_input"):
            return {"status": "WAITING_INPUT", "repairs_used": repairs_used, **output}

        if node_type == "gate":
            if output.get("passed"):
                last_verdict_artifact_id = output.get("verdict_artifact_id")
                current_id = node.get("next")
            else:
                terminal_failure = output.get("terminal_failure", False)
                if terminal_failure or repairs_used >= max_repairs:
                    reason_code = (
                        "gate_terminal_failure" if terminal_failure else "gate_repair_budget_exhausted"
                    )
                    _mark_run_failed(conn, run_id=run_id, reason_code=reason_code)
                    return {
                        "status": "FAILED",
                        "repairs_used": repairs_used,
                        "verdict_artifact_id": output.get("verdict_artifact_id"),
                    }
                repairs_used += 1
                current_id = node.get("onFail")
                if current_id is None:
                    raise WorkflowEngineError(f"gate node '{node['id']}' failed with no 'onFail' target")
        else:
            current_id = node.get("next")

    conn.execute(
        "UPDATE runs SET status = 'SUCCEEDED', updated_at = ? WHERE run_id = ?",
        (utc_now_rfc3339(), run_id),
    )
    conn.commit()
    write_event(conn, run_id=run_id, new_status="SUCCEEDED", actor="engine", reason_code="run_completed")
    return {
        "status": "SUCCEEDED",
        "repairs_used": repairs_used,
        "verdict_artifact_id": last_verdict_artifact_id,
    }
