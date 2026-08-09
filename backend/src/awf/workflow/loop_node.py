"""`loop` node (Section 12.2): repeats a child Workflow while a condition
holds, bounded by `maxIterations`.

The condition is read from the child Run's own last-executed Step output
(`steps.output_json` for the most recently started Step of that child
run_id) - a named boolean field, `conditionField` (default `continue`) -
rather than a fabricated side-channel file, since that value is already
real, persisted state. That same output becomes the next iteration's input,
so a loop body can carry state forward.

Reaching `maxIterations` while the condition is still true moves the Run to
`WAITING_INPUT` for operator disposition, mirroring the Handoff node's
`maxHops` rule (Section 13.4) - it MUST NOT silently continue or silently
succeed past its own bound. Like Handoff, `loop` is self-stepping: each
iteration is already a fully durable child Run in its own right, so the
loop node itself creates no outer Step whose terminal status could be
wrongly cached across a resume (the risk a plain `run_step` wrapper would
carry here, since "still waiting" is not a terminal outcome).
"""

import json
import sqlite3

from awf.clock import utc_now_rfc3339
from awf.events.writer import write_event
from awf.workflow.subworkflow import RunChildFn


class LoopNodeError(RuntimeError):
    def __init__(self, message: str, *, failure_class: str = "TOOL_ERROR"):
        super().__init__(message)
        self.failure_class = failure_class


def _last_step_output(conn: sqlite3.Connection, run_id: str) -> dict:
    row = conn.execute(
        "SELECT output_json FROM steps WHERE run_id = ? AND output_json IS NOT NULL ORDER BY started_at DESC LIMIT 1",
        (run_id,),
    ).fetchone()
    if row is None:
        return {}
    return json.loads(row["output_json"])


def make_loop_node_executor(run_child: RunChildFn):
    def executor(conn: sqlite3.Connection, run_id: str, _step_id: str, node: dict) -> dict:
        max_iterations = node["maxIterations"]
        condition_field = node.get("conditionField", "continue")
        current_input = node.get("input", {})
        child_run_ids = []

        for iteration in range(max_iterations):
            child_run_id, result = run_child(conn, node["workflowRef"], current_input)
            if result.get("status") != "SUCCEEDED":
                raise LoopNodeError(
                    f"loop iteration {iteration + 1} (child run {child_run_id}) did not succeed: {result}"
                )
            child_run_ids.append(child_run_id)

            last_output = _last_step_output(conn, child_run_id)
            if not last_output.get(condition_field):
                return {
                    "completed": True,
                    "iterations_used": iteration + 1,
                    "child_run_ids": child_run_ids,
                }
            current_input = last_output

        now = utc_now_rfc3339()
        conn.execute(
            "UPDATE runs SET status = 'WAITING_INPUT', updated_at = ? WHERE run_id = ?",
            (now, run_id),
        )
        conn.commit()
        write_event(
            conn,
            run_id=run_id,
            new_status="WAITING_INPUT",
            actor="engine",
            reason_code="loop_max_iterations_reached",
        )
        return {
            "completed": False,
            "iterations_used": max_iterations,
            "child_run_ids": child_run_ids,
            "waiting_input": True,
        }

    return executor
