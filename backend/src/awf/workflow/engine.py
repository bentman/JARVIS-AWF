"""Workflow engine (Section 12): executes a WorkflowDefinition as durable Steps.

Only enough execution semantics exist here to run the produce -> gate ->
repair example workflow end to end - Phase 7's stated scope. `activity`,
`agent`, and `gate` nodes are interpreted; `approval`, `subworkflow`, `map`,
`loop`, and `handoff` are validated as node shapes (Section 12.2, in
`workflow.nodes`) but have no execution semantics yet - `handoff` is built in
Phase 9, full Trifecta `gate` tiering in Phase 8.

Branching is driven by two engine-specific node fields that are NOT part of
the Section 12.1 spec shape: `next` (the node id to run afterward; absent
means the workflow completes) and, on `gate` nodes, `onFail` (the node id to
jump to when the gate fails).
"""

import sqlite3
from pathlib import Path
from typing import Callable

from awf.adapters.base import AgentInvocation, AgentStatus
from awf.clock import utc_now_rfc3339
from awf.engine.executor import run_step
from awf.engine.run import create_step
from awf.events.writer import write_event
from awf.isolation.worktree import commit_all_changes
from awf.workflow.definition import WorkflowDefinition

NodeExecutor = Callable[[sqlite3.Connection, str, str, dict], dict]
AdapterFn = Callable[[AgentInvocation], "AgentResult"]

EXECUTABLE_NODE_TYPES = ("activity", "agent", "gate")


class WorkflowEngineError(RuntimeError):
    pass


def make_agent_node_executor(
    adapter_registry: dict[str, AdapterFn], worktree_path: Path
) -> NodeExecutor:
    def executor(conn: sqlite3.Connection, run_id: str, step_id: str, node: dict) -> dict:
        adapter_fn = adapter_registry[node["adapter"]]
        invocation = AgentInvocation(
            objective=node["objective"],
            inputs={},
            workspace_root=worktree_path,
            constraints=node.get("constraints", {}),
        )

        def fn(_payload: dict) -> dict:
            result = adapter_fn(invocation)
            if result.status != AgentStatus.COMPLETED:
                raise WorkflowEngineError(
                    f"agent node '{node['id']}' did not complete: "
                    f"status={result.status.value} reason={result.termination_reason!r}"
                )
            return {"status": result.status.value}

        output = run_step(conn, step_id=step_id, run_id=run_id, fn=fn, input_payload={})
        commit_sha = commit_all_changes(worktree_path, f"workflow: {node['id']}")
        return {**output, "commit_sha": commit_sha}

    return executor


def make_gate_node_executor(check_fn: Callable[[dict], bool]) -> NodeExecutor:
    def executor(conn: sqlite3.Connection, run_id: str, step_id: str, node: dict) -> dict:
        def fn(_payload: dict) -> dict:
            return {"passed": bool(check_fn(node))}

        return run_step(conn, step_id=step_id, run_id=run_id, fn=fn, input_payload={})

    return executor


def run_workflow_definition(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    workflow: WorkflowDefinition,
    node_executors: dict[str, NodeExecutor],
) -> dict:
    max_repairs = workflow.budgets.get("maxRepairIterations", 3)
    repairs_used = 0
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
        step_id = f"{current_id}#{attempt_counts[current_id]}"
        create_step(conn, step_id=step_id, run_id=run_id, node_id=current_id, attempt=attempt_counts[current_id])

        output = executor(conn, run_id, step_id, node)

        if node_type == "gate":
            if output.get("passed"):
                current_id = node.get("next")
            else:
                if repairs_used >= max_repairs:
                    conn.execute(
                        "UPDATE runs SET status = 'FAILED', updated_at = ? WHERE run_id = ?",
                        (utc_now_rfc3339(), run_id),
                    )
                    conn.commit()
                    write_event(
                        conn, run_id=run_id, new_status="FAILED",
                        actor="engine", reason_code="gate_repair_budget_exhausted",
                    )
                    return {"status": "FAILED", "repairs_used": repairs_used}
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
    return {"status": "SUCCEEDED", "repairs_used": repairs_used}
