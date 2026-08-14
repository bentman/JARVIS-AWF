"""Repository Python executable resolution."""

import sys
from pathlib import Path


def repo_python_executable(repo_root: Path) -> tuple[str, str] | None:
    candidates = [
        ("windows-venv", repo_root / "backend" / ".venv" / "Scripts" / "python.exe"),
        ("linux-venv", repo_root / "backend" / ".venv" / "bin" / "python"),
    ]
    for marker, candidate in candidates:
        if candidate.is_file():
            return marker, str(candidate)
    return None


def repo_python_executable_or_current(repo_root: Path) -> str:
    selected = repo_python_executable(repo_root)
    return selected[1] if selected is not None else sys.executable
