"""Disposable scratch directory lifecycle: `cache/sandbox/<run_id>/` (Section 10.4).

Nothing durable may be written here - safe to delete at any time, never backed up.
"""

import shutil
from pathlib import Path

from awf.paths import scratch_dir


def scratch_path(repo_root: Path, run_id: str) -> Path:
    return scratch_dir(repo_root, run_id)


def create_scratch_dir(repo_root: Path, run_id: str) -> Path:
    path = scratch_path(repo_root, run_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def remove_scratch_dir(repo_root: Path, run_id: str) -> None:
    shutil.rmtree(scratch_path(repo_root, run_id), ignore_errors=True)
