"""Git diff identity and artifact helpers for Improvement Proposals."""

import hashlib
import sqlite3
import subprocess
from pathlib import Path

from awf.clock import utc_now_rfc3339
from awf.ids import uuid7


class ImprovementDiffError(RuntimeError):
    pass


def _run_git(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True)
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace").strip()
        raise ImprovementDiffError(f"git {' '.join(args)} failed: {stderr}")
    return result


def git_text(args: list[str], cwd: Path) -> str:
    return _run_git(args, cwd).stdout.decode("utf-8", errors="replace").strip()


def current_branch(repo_or_worktree: Path) -> str:
    return git_text(["branch", "--show-current"], repo_or_worktree)


def merge_base(repo_root: Path, target_ref: str, candidate_ref: str) -> str:
    return git_text(["merge-base", target_ref, candidate_ref], repo_root)


def diff_bytes(repo_root: Path, base_commit: str, candidate_commit: str) -> bytes:
    return _run_git(["diff", "--binary", base_commit, candidate_commit], repo_root).stdout


def diff_digest(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def changed_paths(repo_root: Path, base_commit: str, candidate_commit: str) -> list[dict]:
    result = git_text(["diff", "--numstat", base_commit, candidate_commit], repo_root)
    rows: list[dict] = []
    for line in result.splitlines():
        if not line.strip():
            continue
        added, deleted, path = line.split("\t", 2)
        rows.append({"path": path, "added": added, "deleted": deleted})
    return rows


def write_patch_artifact(
    conn: sqlite3.Connection,
    *,
    artifacts_root: Path,
    run_id: str,
    step_id: str,
    payload: bytes,
) -> str:
    sha256 = hashlib.sha256(payload).hexdigest()
    relative_path = f"{sha256[:2]}/{sha256}.patch"
    target = artifacts_root / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)
    artifact_id = uuid7()
    conn.execute(
        "INSERT INTO artifacts "
        "(artifact_id, run_id, step_id, sha256, relative_path, media_type, artifact_type, complete, created_at) "
        "VALUES (?, ?, ?, ?, ?, 'text/x-diff', 'patch', 1, ?)",
        (artifact_id, run_id, step_id, sha256, relative_path, utc_now_rfc3339()),
    )
    conn.commit()
    return artifact_id
