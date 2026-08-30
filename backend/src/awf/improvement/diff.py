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


def parse_patch_diff_previews(patch_text: str, max_lines_per_file: int = 15) -> list[dict]:
    """Parse a unified git diff into structured per-file previews and stats."""
    file_chunks: list[tuple[str, list[str], int, int, bool]] = []
    current_path: str | None = None
    current_lines: list[str] = []
    additions = 0
    deletions = 0
    is_binary = False

    for line in patch_text.splitlines():
        if line.startswith("diff --git "):
            if current_path is not None:
                file_chunks.append((current_path, current_lines, additions, deletions, is_binary))
            parts = line.split(" ")
            b_path = parts[3] if len(parts) >= 4 else "unknown"
            current_path = b_path[2:] if b_path.startswith("b/") else b_path
            current_lines = []
            additions = 0
            deletions = 0
            is_binary = False
        elif current_path is not None:
            current_lines.append(line)
            if line.startswith("Binary files ") or line.startswith("GIT binary patch"):
                is_binary = True
            elif line.startswith("+") and not line.startswith("+++"):
                additions += 1
            elif line.startswith("-") and not line.startswith("---"):
                deletions += 1

    if current_path is not None:
        file_chunks.append((current_path, current_lines, additions, deletions, is_binary))

    previews: list[dict] = []
    for path, lines, adds, dels, binary in file_chunks:
        total = len(lines)
        truncated = total > max_lines_per_file
        previews.append(
            {
                "path": path,
                "additions": adds,
                "deletions": dels,
                "is_binary": binary,
                "preview_lines": lines[:max_lines_per_file],
                "truncated": truncated,
                "total_lines": total,
            }
        )
    return previews


def diff_file_previews(
    repo_root: Path, base_commit: str, candidate_commit: str, max_lines_per_file: int = 15
) -> list[dict]:
    """Extract structured per-file diff stats and compact previews from git commits."""
    try:
        raw_diff = git_text(["diff", "--binary", base_commit, candidate_commit], repo_root)
        numstat_rows = changed_paths(repo_root, base_commit, candidate_commit)
    except Exception:
        return []

    parsed = parse_patch_diff_previews(raw_diff, max_lines_per_file=max_lines_per_file)
    parsed_map = {item["path"]: item for item in parsed}

    previews: list[dict] = []
    for item in numstat_rows:
        path = item["path"]
        if path in parsed_map:
            previews.append(parsed_map[path])
        else:
            added_str = str(item.get("added", "0"))
            deleted_str = str(item.get("deleted", "0"))
            is_binary = added_str == "-" or deleted_str == "-"
            previews.append(
                {
                    "path": path,
                    "additions": int(added_str) if not is_binary and added_str.isdigit() else 0,
                    "deletions": int(deleted_str) if not is_binary and deleted_str.isdigit() else 0,
                    "is_binary": is_binary,
                    "preview_lines": [],
                    "truncated": False,
                    "total_lines": 0,
                }
            )
    return previews
