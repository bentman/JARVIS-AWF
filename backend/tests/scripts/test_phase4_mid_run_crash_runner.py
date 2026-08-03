"""Standalone script that simulates a real mid-Run process kill (Section 13.2).

Invoked as a subprocess (not imported) so "start" can genuinely terminate the
process via os._exit before Step 2 persists - a real crash, not a simulated one.

Usage:
    python test_phase4_mid_run_crash_runner.py start  <db_path> <counter_path>
    python test_phase4_mid_run_crash_runner.py resume <db_path> <counter_path>
"""

import os
import sys
from pathlib import Path

from awf.db.bootstrap import init_db
from awf.db.connection import get_connection
from awf.engine.executor import run_workflow
from awf.engine.recovery import scan_incomplete_runs
from awf.engine.run import create_run, create_step

RUN_ID = "run-crash-1"


def _step1(_input: dict, counter_path: Path) -> dict:
    n = (int(counter_path.read_text()) if counter_path.exists() else 0) + 1
    counter_path.write_text(str(n))
    return {"count": n}


def _step2_crash(_input: dict) -> dict:
    os._exit(137)  # a real, unrecoverable crash mid-Step - no cleanup runs


def _step2_clean(_input: dict) -> dict:
    return {"done": True}


def main() -> None:
    mode = sys.argv[1]
    db_path = Path(sys.argv[2])
    counter_path = Path(sys.argv[3])

    if mode == "start":
        init_db(db_path)
        conn = get_connection(db_path)
        create_run(conn, run_id=RUN_ID, workflow_ref="noop-2step@1.0.0")
        create_step(conn, step_id="step-1", run_id=RUN_ID, node_id="n1")
        create_step(conn, step_id="step-2", run_id=RUN_ID, node_id="n2")

        steps = [
            ("step-1", lambda payload: _step1(payload, counter_path), {}),
            ("step-2", _step2_crash, {}),
        ]
        run_workflow(conn, run_id=RUN_ID, steps=steps)
        raise AssertionError("unreachable: _step2_crash must have terminated the process")

    elif mode == "resume":
        conn = get_connection(db_path)
        incomplete = scan_incomplete_runs(conn)
        assert incomplete == [RUN_ID], incomplete

        steps = [
            ("step-1", lambda payload: _step1(payload, counter_path), {}),
            ("step-2", _step2_clean, {}),
        ]
        run_workflow(conn, run_id=RUN_ID, steps=steps)
        print("RESUME_OK")

    else:
        raise SystemExit(f"unknown mode: {mode!r}")


if __name__ == "__main__":
    main()
