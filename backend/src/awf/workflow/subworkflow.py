"""`subworkflow` node (Section 12.2): starts a version-pinned child Workflow
and runs it to completion through the same durable engine as any top-level
Run - a real child `runs` row, real Steps, real events, not a simulated
call.

`run_child` is supplied by the caller (`awf.ops.run`, which already
knows how to resolve a workflow ref and build node executors) rather than
imported here, to avoid a circular dependency between the workflow engine
and the operation layer that wires it up. The same `run_child` callback is reused
by the `map` and `loop` node executors.
"""

import sqlite3
from collections.abc import Callable

from awf.engine.executor import run_step

RunChildFn = Callable[[sqlite3.Connection, str, dict], tuple[str, dict]]


class SubworkflowError(RuntimeError):
    def __init__(self, message: str, *, failure_class: str = "TOOL_ERROR"):
        super().__init__(message)
        self.failure_class = failure_class


def make_subworkflow_node_executor(run_child: RunChildFn):
    def executor(conn: sqlite3.Connection, run_id: str, step_id: str, node: dict) -> dict:
        def fn(_payload: dict) -> dict:
            child_run_id, result = run_child(conn, node["workflowRef"], node.get("input", {}))
            if result.get("status") != "SUCCEEDED":
                raise SubworkflowError(f"child run {child_run_id} ({node['workflowRef']}) did not succeed: {result}")
            return {"child_run_id": child_run_id, "child_status": result["status"]}

        return run_step(conn, step_id=step_id, run_id=run_id, fn=fn, input_payload={})

    return executor
