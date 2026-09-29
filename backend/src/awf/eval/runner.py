"""Evaluation runner for proposal verification."""

import json
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

from awf.artifacts import write_artifact
from awf.clock import utc_now_rfc3339
from awf.isolation.worktree import current_head
from awf.paths import artifacts_dir

MAX_OUTPUT_SNIPPET_CHARS = 4000


class EvalRunnerError(RuntimeError):
    pass


def run_evaluation(
    repo_root: Path,
    conn: sqlite3.Connection,
    *,
    run_id: str,
    step_id: str,
    worktree: Path,
    candidate_commit: str | None = None,
    commands: list[list[str]] | None = None,
    timeout_seconds: float = 300.0,
) -> dict:
    if not worktree.is_dir():
        raise EvalRunnerError(f"worktree directory does not exist: {worktree}")

    commit = candidate_commit or current_head(worktree)
    if commands is None:
        commands = [[sys.executable, "-m", "pytest", "backend/tests/unit", "-q"]]

    command_results: list[dict] = []
    overall_passed = True

    for cmd in commands:
        start_time = time.perf_counter()
        try:
            proc = subprocess.run(
                cmd,
                cwd=worktree,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
            exit_code = proc.returncode
            stdout = (proc.stdout or "")[-MAX_OUTPUT_SNIPPET_CHARS:]
            stderr = (proc.stderr or "")[-MAX_OUTPUT_SNIPPET_CHARS:]
        except subprocess.TimeoutExpired as exc:
            exit_code = -1
            stdout = ((exc.stdout or "") if isinstance(exc.stdout, str) else "")[-MAX_OUTPUT_SNIPPET_CHARS:]
            stderr = f"Command timed out after {timeout_seconds} seconds"
        except Exception as exc:
            exit_code = -1
            stdout = ""
            stderr = str(exc)

        duration = round(time.perf_counter() - start_time, 3)
        if exit_code != 0:
            overall_passed = False

        command_results.append(
            {
                "command": cmd,
                "exit_code": exit_code,
                "duration_seconds": duration,
                "stdout_snippet": stdout,
                "stderr_snippet": stderr,
            }
        )

    payload = {
        "run_id": run_id,
        "step_id": step_id,
        "candidate_commit": commit,
        "passed": overall_passed,
        "evaluated_at": utc_now_rfc3339(),
        "commands": command_results,
    }

    payload_bytes = json.dumps(payload, sort_keys=True, indent=2).encode("utf-8")
    artifact_id = write_artifact(
        conn,
        artifacts_root=artifacts_dir(repo_root),
        run_id=run_id,
        step_id=step_id,
        payload=payload_bytes,
        media_type="application/json",
        artifact_type="test-result",
    )

    return {
        "artifact_id": artifact_id,
        "passed": overall_passed,
        "payload": payload,
    }
