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


def commit_all_changes(worktree_path: Path, message: str) -> str | None:
    """Commit all changes, or return None if there was nothing to commit."""
    _run_git(["add", "-A"], cwd=worktree_path)
    staged = subprocess.run(
        ["git", "diff", "--cached", "--quiet"], cwd=worktree_path
    )
    if staged.returncode == 0:
        return None
    _run_git(["commit", "-m", message], cwd=worktree_path)
    result = _run_git(["rev-parse", "HEAD"], cwd=worktree_path)
    return result.stdout.strip()


def last_commit_diff(worktree_path: Path, *, max_chars: int = 8000) -> str:
    """The real diff the most recent commit introduced - what an LLM reviewer
    (`gates/verifier.py`, `gates/adversary.py`) is actually shown, instead of
    a gate node's short `check` label. Truncated, never silently empty: a
    diff with no parent commit or with nothing to show still returns a real,
    honest string rather than letting the caller assume content exists."""
    try:
        result = _run_git(["diff", "HEAD~1", "HEAD"], cwd=worktree_path)
    except WorktreeError as exc:
        return f"(no diff available: {exc})"
    diff = result.stdout
    if not diff:
        return "(most recent commit introduced no diff)"
    if len(diff) > max_chars:
        return diff[:max_chars] + f"\n... (truncated, {len(diff) - max_chars} more characters)"
    return diff


def current_head(worktree_path: Path) -> str:
    return _run_git(["rev-parse", "HEAD"], cwd=worktree_path).stdout.strip()


def merge_branch(worktree_path: Path, branch: str, *, message: str) -> None:
    """Merges `branch` into whatever is currently checked out at `worktree_path`
    (`git merge --no-ff`, a real merge commit - never a silent fast-forward
    that would hide which branch a change came from). A conflict aborts the
    merge cleanly and raises, rather than picking a side."""
    result = subprocess.run(
        ["git", "merge", "--no-ff", branch, "-m", message],
        cwd=worktree_path, capture_output=True, text=True,
    )
    if result.returncode != 0:
        subprocess.run(["git", "merge", "--abort"], cwd=worktree_path, capture_output=True, text=True)
        raise WorktreeError(f"merging {branch} conflicted: {result.stderr.strip()}")


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
