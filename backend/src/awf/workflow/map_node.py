"""`map` node (Section 12.2): bounded fan-out over an input array - runs the
same child Workflow once per item in `items` (a literal list embedded in
the node; this engine has no runtime expression language to pull `items`
from a Run's input dynamically).

`maxItems` bounds how many items may be declared at all (mandatory).
`maxConcurrency` bounds a real thread pool, not just a declared number:
each item runs its child Workflow in its own isolated worktree (branched
from the parent worktree's current HEAD) with its own `sqlite3.Connection`
- neither is shared between concurrently-running items, since
`sqlite3.Connection` is not thread-safe and two items committing into the
same worktree concurrently would race.

After every item finishes, each *successful* item's commits are merged
back into the parent worktree in item order (`git merge --no-ff`) - so a
later node in the parent workflow sees a map item's file changes exactly
as it always could when this ran sequentially in the shared worktree. A
merge conflict between two items' changes is a real failure
(`INTEGRITY_FAILURE`), not silently resolved by picking one side.
"""

import concurrent.futures
import inspect
import os
import sqlite3
from collections.abc import Callable
from pathlib import Path

from awf.engine.executor import run_step
from awf.isolation.worktree import WorktreeError, branch_name, current_head, merge_branch, remove_worktree

# (parent_head_sha, index, workflow_ref, item, optional sqlite connection) -> (child_run_id, item_worktree_path, result)
RunMapItemFn = Callable[[str, int, str, object, sqlite3.Connection | None], tuple[str, Path, dict]]


class MapNodeError(RuntimeError):
    def __init__(self, message: str, *, failure_class: str = "TOOL_ERROR"):
        super().__init__(message)
        self.failure_class = failure_class


def _run_map_item(run_map_item: RunMapItemFn, parent_head: str, index: int, workflow_ref: str, item, conn):
    try:
        signature = inspect.signature(run_map_item)
    except (TypeError, ValueError):
        return run_map_item(parent_head, index, workflow_ref, item, conn)
    if len(signature.parameters) >= 5:
        return run_map_item(parent_head, index, workflow_ref, item, conn)
    return run_map_item(parent_head, index, workflow_ref, item)


def make_map_node_executor(run_map_item: RunMapItemFn, *, worktree_path: Path, repo_root: Path):
    def executor(conn: sqlite3.Connection, run_id: str, step_id: str, node: dict) -> dict:
        def fn(_payload: dict) -> dict:
            items = node["items"]
            max_items = node["maxItems"]
            if len(items) > max_items:
                raise MapNodeError(
                    f"node '{node['id']}': {len(items)} items exceeds maxItems={max_items}",
                    failure_class="INVALID_INPUT",
                )
            max_concurrency = max(1, node["maxConcurrency"])
            if os.name == "nt":
                max_concurrency = 1
            workflow_ref = node["workflowRef"]
            parent_head = current_head(worktree_path)

            results_by_index: dict[int, tuple[str, Path, dict]] = {}
            if max_concurrency == 1:
                for index, item in enumerate(items):
                    results_by_index[index] = _run_map_item(run_map_item, parent_head, index, workflow_ref, item, conn)
            else:
                with concurrent.futures.ThreadPoolExecutor(max_workers=max_concurrency) as pool:
                    futures = {
                        pool.submit(_run_map_item, run_map_item, parent_head, index, workflow_ref, item, None): index
                        for index, item in enumerate(items)
                    }
                    for future in concurrent.futures.as_completed(futures):
                        results_by_index[futures[future]] = future.result()

            child_run_ids = []
            try:
                for index in range(len(items)):
                    child_run_id, _item_worktree, result = results_by_index[index]
                    if result.get("status") != "SUCCEEDED":
                        raise MapNodeError(f"map item {index} (child run {child_run_id}) did not succeed: {result}")
                    child_run_ids.append(child_run_id)
                    try:
                        merge_branch(
                            worktree_path,
                            branch_name(child_run_id),
                            message=f"map: merge item {index} (child run {child_run_id})",
                        )
                    except WorktreeError as exc:
                        raise MapNodeError(f"map item {index}: {exc}", failure_class="INTEGRITY_FAILURE") from exc
            finally:
                for child_run_id, _item_worktree, _result in results_by_index.values():
                    remove_worktree(repo_root, child_run_id)

            return {"item_count": len(items), "child_run_ids": child_run_ids}

        return run_step(conn, step_id=step_id, run_id=run_id, fn=fn, input_payload={})

    return executor
