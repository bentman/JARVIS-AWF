"""Test-session-only SQLite speedup, repo-relative path fixtures, and
host-capability availability fixtures shared across `unit/`, `integration/`,
and `runtime/`.

Every test database is a throwaway file under `tmp_path`, discarded at the
end of its own test - none of them need `fsync`-backed crash durability
(that's a production guarantee, Section 13.2, exercised by
`test_phase4_durable_execution.py::test_mid_run_crash_and_resume...`, which
runs in a separate `subprocess.run` process that imports its own unpatched
`sqlite3` module, so this has no effect on that test).

Without this, every `conn.commit()` pays a disk fsync (~90-100ms on this
host), which dominates the wall-clock time of most of the suite - the DB
work in a typical test is microseconds; the fsync isn't.
"""

import sqlite3
from pathlib import Path

import pytest

_real_connect = sqlite3.connect


def _fast_connect(*args, **kwargs):
    conn = _real_connect(*args, **kwargs)
    conn.execute("PRAGMA synchronous=OFF")
    conn.execute("PRAGMA journal_mode=MEMORY")
    return conn


sqlite3.connect = _fast_connect

# backend/tests/conftest.py -> tests -> backend -> <repo root>. Fixed
# regardless of how deep a test module sits under tests/, unlike a module's
# own `Path(__file__).resolve().parents[N]`.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def repo_root() -> Path:
    return _REPO_ROOT


@pytest.fixture
def fixtures_dir() -> Path:
    return _FIXTURES_DIR


@pytest.fixture
def models_present():
    """Callable fixture: `models_present("wake/hey_jarvis_v0.1.onnx", ...)`
    -> `True` only when every given path under `models/` exists."""

    def _check(*relative_paths: str) -> bool:
        return all((_REPO_ROOT / "models" / relative).exists() for relative in relative_paths)

    return _check


@pytest.fixture
def gpu_available() -> bool:
    """`True` only when a live GPU utilization sample succeeds."""
    from awf.hardware.gpu_sampler import GpuSamplerUnavailable, sample_gpu_utilization

    try:
        sample_gpu_utilization()
    except GpuSamplerUnavailable:
        return False
    return True


@pytest.fixture
def repo_file_present():
    """Callable fixture: `repo_file_present("data/registry/skills/...")` ->
    bool, for optional local fixtures not guaranteed to be checked out."""

    def _check(relative_path: str) -> bool:
        return (_REPO_ROOT / relative_path).is_file()

    return _check
