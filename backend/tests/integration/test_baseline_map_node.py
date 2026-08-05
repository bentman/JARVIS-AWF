import subprocess

import pytest

from awf.db.bootstrap import init_db
from awf.db.connection import get_connection
from awf.engine.run import create_run, create_step
from awf.isolation.worktree import branch_name, create_worktree, worktree_path
from awf.workflow.map_node import MapNodeError, make_map_node_executor


def run_git(args, cwd):
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    return result


@pytest.fixture
def repo(tmp_path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    run_git(["init", "-q"], cwd=repo_root)
    run_git(["config", "user.email", "t@e.com"], cwd=repo_root)
    run_git(["config", "user.name", "T"], cwd=repo_root)
    (repo_root / "README.md").write_text("hello\n")
    run_git(["add", "-A"], cwd=repo_root)
    run_git(["commit", "-q", "-m", "init"], cwd=repo_root)
    return repo_root


@pytest.fixture
def parent_worktree(repo):
    return create_worktree(repo, "run-1")


@pytest.fixture
def conn(tmp_path):
    db_path = tmp_path / "awf.db"
    init_db(db_path)
    connection = get_connection(db_path)
    create_run(connection, run_id="run-1", workflow_ref="demo@1.0.0")
    create_step(connection, step_id="step-1", run_id="run-1", node_id="fan-out")
    return connection


def make_real_child_run(repo_root, parent_head, index, *, filename=None, content=None):
    """Returns a run_map_item-shaped result for a real, isolated child
    worktree that wrote and committed one real file - not a stub."""
    child_run_id = f"child-{index}"
    item_worktree = create_worktree(repo_root, child_run_id, base_ref=parent_head)
    if filename is not None:
        (item_worktree / filename).write_text(content)
        run_git(["add", "-A"], cwd=item_worktree)
        run_git(["commit", "-q", "-m", f"map item {index}"], cwd=item_worktree)
    return child_run_id, item_worktree


def test_map_runs_items_concurrently_and_merges_results_in_order(repo, parent_worktree, conn):
    seen_indices = []

    def run_map_item(parent_head, index, workflow_ref, item):
        seen_indices.append(index)
        child_run_id, item_worktree = make_real_child_run(
            repo, parent_head, index, filename=f"item_{index}.txt", content=f"result for {item}\n"
        )
        return child_run_id, item_worktree, {"status": "SUCCEEDED"}

    executor = make_map_node_executor(run_map_item, worktree_path=parent_worktree, repo_root=repo)
    output = executor(
        conn, "run-1", "step-1",
        {
            "id": "fan-out", "type": "map", "workflowRef": "child@1.0.0",
            "items": ["a", "b", "c"], "maxItems": 5, "maxConcurrency": 2,
        },
    )

    assert output["item_count"] == 3
    assert output["child_run_ids"] == ["child-0", "child-1", "child-2"]
    assert sorted(seen_indices) == [0, 1, 2]

    # each item's file is visible in the parent worktree - a git merge
    # happened, not just bookkeeping.
    assert (parent_worktree / "item_0.txt").read_text() == "result for a\n"
    assert (parent_worktree / "item_1.txt").read_text() == "result for b\n"
    assert (parent_worktree / "item_2.txt").read_text() == "result for c\n"

    log = run_git(["log", "--oneline"], cwd=parent_worktree).stdout
    assert log.count("map: merge item") == 3

    # every child worktree was cleaned up afterward
    worktrees = run_git(["worktree", "list"], cwd=repo).stdout
    for index in range(3):
        assert str(worktree_path(repo, f"child-{index}")) not in worktrees
        branches = run_git(["branch", "--list", branch_name(f"child-{index}")], cwd=repo).stdout
        assert branches.strip() == ""


def test_map_rejects_more_items_than_max_items(repo, parent_worktree, conn):
    def run_map_item(parent_head, index, workflow_ref, item):
        raise AssertionError("must not be called - maxItems check happens first")

    executor = make_map_node_executor(run_map_item, worktree_path=parent_worktree, repo_root=repo)

    with pytest.raises(MapNodeError):
        executor(
            conn, "run-1", "step-1",
            {
                "id": "fan-out", "type": "map", "workflowRef": "child@1.0.0",
                "items": ["a", "b", "c"], "maxItems": 2, "maxConcurrency": 2,
            },
        )


def test_map_raises_when_any_item_fails_and_leaves_earlier_merges_in_place(repo, parent_worktree, conn):
    def run_map_item(parent_head, index, workflow_ref, item):
        if index == 1:
            child_run_id, item_worktree = make_real_child_run(repo, parent_head, index)
            return child_run_id, item_worktree, {"status": "FAILED"}
        child_run_id, item_worktree = make_real_child_run(
            repo, parent_head, index, filename=f"item_{index}.txt", content="ok\n"
        )
        return child_run_id, item_worktree, {"status": "SUCCEEDED"}

    executor = make_map_node_executor(run_map_item, worktree_path=parent_worktree, repo_root=repo)

    with pytest.raises(MapNodeError):
        executor(
            conn, "run-1", "step-1",
            {
                "id": "fan-out", "type": "map", "workflowRef": "child@1.0.0",
                "items": ["a", "b"], "maxItems": 5, "maxConcurrency": 2,
            },
        )

    row = conn.execute("SELECT status FROM steps WHERE step_id = 'step-1'").fetchone()
    assert row["status"] == "FAILED"
    # item 0 succeeded and merged before item 1's failure was reached (in
    # order) - that work is not rolled back, same as any other Step-level
    # durability in this system.
    assert (parent_worktree / "item_0.txt").is_file()

    worktrees = run_git(["worktree", "list"], cwd=repo).stdout
    assert str(worktree_path(repo, "child-0")) not in worktrees
    assert str(worktree_path(repo, "child-1")) not in worktrees


def test_map_merge_conflict_aborts_cleanly_and_fails_with_integrity_failure(repo, parent_worktree, conn):
    def run_map_item(parent_head, index, workflow_ref, item):
        # both items modify the same file with conflicting content
        child_run_id, item_worktree = make_real_child_run(
            repo, parent_head, index, filename="shared.txt", content=f"written by item {index}\n"
        )
        return child_run_id, item_worktree, {"status": "SUCCEEDED"}

    executor = make_map_node_executor(run_map_item, worktree_path=parent_worktree, repo_root=repo)

    with pytest.raises(MapNodeError) as exc_info:
        executor(
            conn, "run-1", "step-1",
            {
                "id": "fan-out", "type": "map", "workflowRef": "child@1.0.0",
                "items": ["a", "b"], "maxItems": 5, "maxConcurrency": 2,
            },
        )
    assert exc_info.value.failure_class == "INTEGRITY_FAILURE"

    # the aborted merge left the parent worktree clean, not mid-conflict
    status = run_git(["status", "--porcelain"], cwd=parent_worktree).stdout
    assert status.strip() == ""
