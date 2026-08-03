"""`map` node (Section 12.2): bounded fan-out over an input array - runs the
same child Workflow once per item in `items` (a literal list embedded in
the node; this engine has no runtime expression language to pull `items`
from a Run's input dynamically).

`maxItems` bounds how many items may be declared at all (Section 12.2:
mandatory); `maxConcurrency` is validated as a declared upper bound, but
every item currently runs sequentially through the same `sqlite3.Connection`
- that connection is not thread-safe, and this module does not open
per-thread connections, so it makes no claim of real parallel execution.
"""

import sqlite3

from awf.engine.executor import run_step
from awf.workflow.subworkflow import RunChildFn


class MapNodeError(RuntimeError):
    def __init__(self, message: str, *, failure_class: str = "TOOL_ERROR"):
        super().__init__(message)
        self.failure_class = failure_class


def make_map_node_executor(run_child: RunChildFn):
    def executor(conn: sqlite3.Connection, run_id: str, step_id: str, node: dict) -> dict:
        def fn(_payload: dict) -> dict:
            items = node["items"]
            max_items = node["maxItems"]
            if len(items) > max_items:
                raise MapNodeError(
                    f"node '{node['id']}': {len(items)} items exceeds maxItems={max_items}",
                    failure_class="INVALID_INPUT",
                )

            child_run_ids = []
            for index, item in enumerate(items):
                child_run_id, result = run_child(
                    conn, node["workflowRef"], {"item": item, "index": index}
                )
                if result.get("status") != "SUCCEEDED":
                    raise MapNodeError(
                        f"map item {index} (child run {child_run_id}) did not succeed: {result}"
                    )
                child_run_ids.append(child_run_id)

            return {"item_count": len(items), "child_run_ids": child_run_ids}

        return run_step(conn, step_id=step_id, run_id=run_id, fn=fn, input_payload={})

    return executor
