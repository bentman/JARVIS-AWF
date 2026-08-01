import subprocess

import pytest

from awf.isolation.scratch import create_scratch_dir, remove_scratch_dir, scratch_path
from awf.isolation.worktree import (
    WorktreeError,
    branch_name,
    commit_all_changes,
    create_worktree,
    remove_worktree,
    worktree_path,
)


def run_git(args, cwd):
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    return result


@pytest.fixture
def repo(tmp_path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    run_git(["init", "-q"], cwd=repo_root)
    run_git(["config", "user.email", "test@example.com"], cwd=repo_root)
    run_git(["config", "user.name", "Test"], cwd=repo_root)
    (repo_root / "README.md").write_text("hello\n")
    run_git(["add", "-A"], cwd=repo_root)
    run_git(["commit", "-q", "-m", "init"], cwd=repo_root)
    return repo_root


def test_create_worktree_checks_out_dedicated_branch(repo):
    path = create_worktree(repo, "run-1")

    assert path == worktree_path(repo, "run-1")
    assert path.is_dir()
    assert (path / "README.md").is_file()

    branches = run_git(["branch", "--list", branch_name("run-1")], cwd=repo).stdout
    assert branch_name("run-1") in branches


def test_two_runs_get_independent_worktrees(repo):
    path_a = create_worktree(repo, "run-a")
    path_b = create_worktree(repo, "run-b")

    assert path_a != path_b
    (path_a / "only_a.txt").write_text("a\n")
    assert not (path_b / "only_a.txt").exists()


def test_commit_all_changes_commits_only_the_worktree(repo):
    path = create_worktree(repo, "run-1")
    (path / "new_file.txt").write_text("content\n")

    sha = commit_all_changes(path, "add new_file.txt")

    assert sha
    log = run_git(["log", "--oneline", "-1"], cwd=path).stdout
    assert "add new_file.txt" in log
    # main worktree/branch is untouched
    main_log = run_git(["log", "--oneline", "-1"], cwd=repo).stdout
    assert "init" in main_log


def test_remove_worktree_cleans_up_path_and_branch(repo):
    create_worktree(repo, "run-1")
    remove_worktree(repo, "run-1")

    assert not worktree_path(repo, "run-1").exists()
    branches = run_git(["branch", "--list", branch_name("run-1")], cwd=repo).stdout
    assert branch_name("run-1") not in branches


def test_create_worktree_raises_on_invalid_base_ref(repo):
    with pytest.raises(WorktreeError):
        create_worktree(repo, "run-1", base_ref="not-a-real-ref")


def test_scratch_dir_lifecycle(tmp_path):
    path = create_scratch_dir(tmp_path, "run-1")
    assert path == scratch_path(tmp_path, "run-1")
    assert path.is_dir()

    (path / "tmp.txt").write_text("x")
    remove_scratch_dir(tmp_path, "run-1")
    assert not path.exists()
