"""Handoff node (Section 13.4): bounded multi-agent cycles as a normal pattern.

Each hop is a normal, durable Step - a crash mid-loop resumes at the last
completed hop (Section 13.2), not at the start of the cycle, since hop
progress lives in `steps` like any other Step. A loop that reaches maxHops
without the termination condition being set MUST move the Run to
WAITING_INPUT for operator disposition - it MUST NOT silently continue or
silently succeed.

Handoff is for locally-invoked adapters only (Section 13.4); calling a
remote, independently-deployed agent is the A2A extension point, out of
scope here.

The termination condition and the inter-hop payload are both structured
artifacts, never raw conversation history: each hop's agent is instructed to
write a JSON status file (default `handoff_status.json`) containing at least
`{"<terminationField>": bool, "summary": str}`. The engine reads that file
deterministically - it never parses or trusts agent prose to decide whether
the loop continues.
"""

import json
import sqlite3
from pathlib import Path
from typing import Callable

from awf.adapters.base import AgentInvocation, AgentStatus
from awf.clock import utc_now_rfc3339
from awf.engine.executor import run_step
from awf.engine.run import create_step
from awf.events.writer import write_event
from awf.isolation.worktree import commit_all_changes

AdapterFn = Callable[[AgentInvocation], "AgentResult"]

DEFAULT_STATUS_FILENAME = "handoff_status.json"


class HandoffError(RuntimeError):
    pass


def make_handoff_node_executor(
    adapter_registry: dict[str, AdapterFn],
    worktree_path: Path,
    *,
    status_filename: str = DEFAULT_STATUS_FILENAME,
):
    def executor(conn: sqlite3.Connection, run_id: str, step_id: str, node: dict) -> dict:
        agents = [node["initiatingAgent"], node["receivingAgent"]]
        max_hops = node["maxHops"]
        termination_field = node.get("terminationField", "handoff_complete")
        status_path = worktree_path / status_filename

        previous_summary = ""
        completed = False
        hop_count = 0

        for hop in range(max_hops):
            hop_count = hop + 1
            agent_config = agents[hop % 2]
            adapter_fn = adapter_registry[agent_config["adapter"]]

            objective = agent_config["objective"]
            if previous_summary:
                objective = f"{objective}\n\nPrevious hop summary: {previous_summary}"
            objective += (
                f"\n\nWhen done, write a file named {status_filename} in the current "
                f'directory containing exactly this JSON: {{"{termination_field}": <true or false>, '
                f'"summary": "<one-line summary of what you did>"}}'
            )

            invocation = AgentInvocation(objective=objective, inputs={}, workspace_root=worktree_path)
            hop_step_id = f"{step_id}:hop{hop_count}"
            create_step(
                conn, step_id=hop_step_id, run_id=run_id,
                node_id=f"{node['id']}:hop{hop_count}", attempt=1,
            )

            def fn(_payload: dict, adapter_fn=adapter_fn, invocation=invocation) -> dict:
                result = adapter_fn(invocation)
                if result.status != AgentStatus.COMPLETED:
                    raise HandoffError(
                        f"handoff hop {hop_count} did not complete: "
                        f"status={result.status.value} reason={result.termination_reason!r}"
                    )
                return {"status": result.status.value}

            run_step(conn, step_id=hop_step_id, run_id=run_id, fn=fn, input_payload={})
            commit_all_changes(worktree_path, f"handoff: {node['id']} hop {hop_count}")

            if not status_path.is_file():
                raise HandoffError(f"hop {hop_count}: agent did not write {status_filename}")
            status = json.loads(status_path.read_text())
            previous_summary = status.get("summary", "")
            if status.get(termination_field):
                completed = True
                break

        if completed:
            return {"completed": True, "hops_used": hop_count}

        conn.execute(
            "UPDATE runs SET status = 'WAITING_INPUT', updated_at = ? WHERE run_id = ?",
            (utc_now_rfc3339(), run_id),
        )
        conn.commit()
        write_event(
            conn, run_id=run_id, new_status="WAITING_INPUT",
            actor="engine", reason_code="handoff_max_hops_reached",
        )
        return {"completed": False, "hops_used": hop_count, "waiting_input": True}

    return executor
