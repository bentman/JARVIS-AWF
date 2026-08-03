"""Test-session-only SQLite speedup.

Every test database is a throwaway file under `tmp_path`, discarded at the
end of its own test - none of them need `fsync`-backed crash durability
(that's a production guarantee, Section 13.2, and it's exercised for real by
`test_phase4_durable_execution.py::test_mid_run_crash_and_resume...`, which
runs in a genuinely separate `subprocess.run` process that imports its own
unpatched `sqlite3` module, so this has no effect on that test).

Without this, every `conn.commit()` pays a real disk fsync (~90-100ms on
this host), which dominates the wall-clock time of most of the suite - the
DB work in a typical test is microseconds; the fsync isn't.
"""

import sqlite3

_real_connect = sqlite3.connect


def _fast_connect(*args, **kwargs):
    conn = _real_connect(*args, **kwargs)
    conn.execute("PRAGMA synchronous=OFF")
    conn.execute("PRAGMA journal_mode=MEMORY")
    return conn


sqlite3.connect = _fast_connect
