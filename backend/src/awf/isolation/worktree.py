"""Git worktree manager: one dedicated worktree per mutating Run (Section 10.4).

Never shared concurrently between Runs. Lives under `cache/worktrees/<run_id>/`
- disposable and re-derivable from git history, so it belongs alongside the
other `cache/` scratch state rather than under `data/`.
"""

import subprocess
from pathlib import Path


class WorktreeError(RuntimeError):
    pass


def _run_git(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    result = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True
    )
    if result.returncode != 0:
        raise WorktreeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result


def branch_name(run_id: str) -> str:
    return f"awf/run/{run_id}"


def worktree_path(repo_root: Path, run_id: str) -> Path:
    return repo_root / "cache" / "worktrees" / run_id


def create_worktree(repo_root: Path, run_id: str, base_ref: str = "HEAD") -> Path:
    path = worktree_path(repo_root, run_id)
    _run_git(
        ["worktree", "add", "-b", branch_name(run_id), str(path), base_ref],
        cwd=repo_root,
    )
    return path


def commit_all_changes(worktree_path: Path, message: str) -> str:
    _run_git(["add", "-A"], cwd=worktree_path)
    _run_git(["commit", "-m", message], cwd=worktree_path)
    result = _run_git(["rev-parse", "HEAD"], cwd=worktree_path)
    return result.stdout.strip()


def remove_worktree(repo_root: Path, run_id: str) -> None:
    path = worktree_path(repo_root, run_id)
    subprocess.run(
        ["git", "worktree", "remove", "--force", str(path)],
        cwd=repo_root, capture_output=True, text=True,
    )
    subprocess.run(
        ["git", "branch", "-D", branch_name(run_id)],
        cwd=repo_root, capture_output=True, text=True,
    )
