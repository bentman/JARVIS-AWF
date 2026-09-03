import json

import pytest
from backend.tests.support import make_git_awf_repo, publish_workflow

from awf.engine.executor import StepFailure
from awf.engine.run import create_run
from awf.ops.run import op_run_resume, op_run_start
from awf.workflow.activities import ACTIVITY_REGISTRY, ActivityRegistration


def test_transient_failure_retries_and_succeeds(tmp_path):
    repo_root, conn = make_git_awf_repo(tmp_path)

    calls = []

    def flakey_activity(_conn, _args):
        calls.append(len(calls) + 1)
        if len(calls) == 1:
            raise StepFailure("Temporary rate limit", failure_class="TRANSIENT")
        return {"attempt": len(calls), "succeeded": True}

    ACTIVITY_REGISTRY["test_flakey"] = ActivityRegistration("local", flakey_activity)

    publish_workflow(
        repo_root,
        {
            "apiVersion": "awf/v1",
            "kind": "Workflow",
            "metadata": {"name": "retry-demo", "version": "1.0.0", "digest": "sha256:retry-1"},
            "spec": {
                "inputSchema": {},
                "outputSchema": {},
                "budgets": {"maxRetries": 2, "backoffSeconds": 0.0},
                "nodes": [
                    {
                        "id": "step1",
                        "type": "activity",
                        "function": "test_flakey",
                        "next": None,
                    }
                ],
                "outputs": {},
            },
        },
    )

    result = op_run_start(repo_root, conn, workflow_ref="retry-demo@1.0.0", input_data={})

    assert result["status"] == "SUCCEEDED"
    assert calls == [1, 2]

    # Verify steps table: attempt 1 FAILED with TRANSIENT, attempt 2 SUCCEEDED
    steps = conn.execute(
        "SELECT step_id, attempt, status, failure_class FROM steps WHERE run_id = ? ORDER BY attempt",
        (result["run_id"],),
    ).fetchall()
    assert len(steps) == 2
    assert steps[0]["attempt"] == 1
    assert steps[0]["status"] == "FAILED"
    assert steps[0]["failure_class"] == "TRANSIENT"
    assert steps[1]["attempt"] == 2
    assert steps[1]["status"] == "SUCCEEDED"

    # Verify event logged
    events = conn.execute(
        "SELECT event_id, new_status, reason_code, payload_json FROM events WHERE run_id = ? AND reason_code = 'step_retry_scheduled'",
        (result["run_id"],),
    ).fetchall()
    assert len(events) == 1
    payload = json.loads(events[0]["payload_json"])
    assert payload["failed_attempt"] == 1
    assert payload["next_attempt"] == 2
    assert payload["failure_class"] == "TRANSIENT"


def test_timeout_failure_retries_and_succeeds(tmp_path):
    repo_root, conn = make_git_awf_repo(tmp_path)

    calls = []

    def timeout_activity(_conn, _args):
        calls.append(len(calls) + 1)
        if len(calls) == 1:
            raise StepFailure("Subprocess timed out", failure_class="TIMEOUT")
        return {"attempt": len(calls), "ok": True}

    ACTIVITY_REGISTRY["test_timeout"] = ActivityRegistration("local", timeout_activity)

    publish_workflow(
        repo_root,
        {
            "apiVersion": "awf/v1",
            "kind": "Workflow",
            "metadata": {"name": "timeout-demo", "version": "1.0.0", "digest": "sha256:timeout-1"},
            "spec": {
                "inputSchema": {},
                "outputSchema": {},
                "budgets": {"maxRetries": 1, "backoffSeconds": 0.0},
                "nodes": [
                    {
                        "id": "fetch_step",
                        "type": "activity",
                        "function": "test_timeout",
                        "next": None,
                    }
                ],
                "outputs": {},
            },
        },
    )

    result = op_run_start(repo_root, conn, workflow_ref="timeout-demo@1.0.0", input_data={})

    assert result["status"] == "SUCCEEDED"
    assert calls == [1, 2]

    steps = conn.execute(
        "SELECT attempt, status, failure_class FROM steps WHERE run_id = ? ORDER BY attempt",
        (result["run_id"],),
    ).fetchall()
    assert len(steps) == 2
    assert steps[0]["failure_class"] == "TIMEOUT"
    assert steps[1]["status"] == "SUCCEEDED"


def test_retries_exhausted_fails_run(tmp_path):
    repo_root, conn = make_git_awf_repo(tmp_path)

    calls = []

    def always_failing_activity(_conn, _args):
        calls.append(len(calls) + 1)
        raise StepFailure("Persistent upstream outage", failure_class="TRANSIENT")

    ACTIVITY_REGISTRY["test_always_fail"] = ActivityRegistration("local", always_failing_activity)

    publish_workflow(
        repo_root,
        {
            "apiVersion": "awf/v1",
            "kind": "Workflow",
            "metadata": {"name": "exhaust-demo", "version": "1.0.0", "digest": "sha256:exhaust-1"},
            "spec": {
                "inputSchema": {},
                "outputSchema": {},
                "budgets": {"maxRetries": 2, "backoffSeconds": 0.0},
                "nodes": [
                    {
                        "id": "fail_node",
                        "type": "activity",
                        "function": "test_always_fail",
                        "next": None,
                    }
                ],
                "outputs": {},
            },
        },
    )

    result = op_run_start(repo_root, conn, workflow_ref="exhaust-demo@1.0.0", input_data={})

    assert result["status"] == "FAILED"
    # Attempt 1, Retry 1 (attempt 2), Retry 2 (attempt 3) -> 3 calls total
    assert len(calls) == 3

    steps = conn.execute(
        "SELECT attempt, status, failure_class FROM steps WHERE run_id = ? ORDER BY attempt",
        (result["run_id"],),
    ).fetchall()
    assert len(steps) == 3
    assert all(s["status"] == "FAILED" and s["failure_class"] == "TRANSIENT" for s in steps)

    events = conn.execute(
        "SELECT payload_json FROM events WHERE run_id = ? AND reason_code = 'step_retry_scheduled' ORDER BY occurred_at",
        (result["run_id"],),
    ).fetchall()
    assert len(events) == 2


@pytest.mark.parametrize(
    "exception_factory",
    [
        lambda: StepFailure("Action disallowed", failure_class="POLICY_DENIED"),
        lambda: RuntimeError("Unhandled internal error"),
    ],
)
def test_non_retry_eligible_failure_fails_immediately(tmp_path, exception_factory):
    repo_root, conn = make_git_awf_repo(tmp_path)

    calls = []

    def failing_activity(_conn, _args):
        calls.append(1)
        raise exception_factory()

    ACTIVITY_REGISTRY["test_non_retry_activity"] = ActivityRegistration("local", failing_activity)

    publish_workflow(
        repo_root,
        {
            "apiVersion": "awf/v1",
            "kind": "Workflow",
            "metadata": {"name": "deny-demo", "version": "1.0.0", "digest": "sha256:deny-1"},
            "spec": {
                "inputSchema": {},
                "outputSchema": {},
                "budgets": {"maxRetries": 3, "backoffSeconds": 0.0},
                "nodes": [
                    {
                        "id": "denied_node",
                        "type": "activity",
                        "function": "test_non_retry_activity",
                        "next": None,
                    }
                ],
                "outputs": {},
            },
        },
    )

    result = op_run_start(repo_root, conn, workflow_ref="deny-demo@1.0.0", input_data={})

    assert result["status"] == "FAILED"
    assert len(calls) == 1

    steps = conn.execute("SELECT step_id FROM steps WHERE run_id = ?", (result["run_id"],)).fetchall()
    assert len(steps) == 1

    events = conn.execute(
        "SELECT event_id FROM events WHERE run_id = ? AND reason_code = 'step_retry_scheduled'",
        (result["run_id"],),
    ).fetchall()
    assert len(events) == 0


def test_node_level_retry_override_and_custom_retry_on(tmp_path):
    repo_root, conn = make_git_awf_repo(tmp_path)

    calls = []

    def tool_error_activity(_conn, _args):
        calls.append(len(calls) + 1)
        if len(calls) == 1:
            raise StepFailure("Subtool failed", failure_class="TOOL_ERROR")
        return {"recovered": True}

    ACTIVITY_REGISTRY["test_tool_error"] = ActivityRegistration("local", tool_error_activity)

    publish_workflow(
        repo_root,
        {
            "apiVersion": "awf/v1",
            "kind": "Workflow",
            "metadata": {"name": "override-demo", "version": "1.0.0", "digest": "sha256:override-1"},
            "spec": {
                "inputSchema": {},
                "outputSchema": {},
                "budgets": {"maxRetries": 0},  # Workflow default: 0 retries
                "nodes": [
                    {
                        "id": "custom_retry_node",
                        "type": "activity",
                        "function": "test_tool_error",
                        "retry": {
                            "max_retries": 1,
                            "retry_on": ["TOOL_ERROR"],
                            "backoff_seconds": 0.0,
                            "jitter": False,
                        },
                        "next": None,
                    }
                ],
                "outputs": {},
            },
        },
    )

    result = op_run_start(repo_root, conn, workflow_ref="override-demo@1.0.0", input_data={})

    assert result["status"] == "SUCCEEDED"
    assert calls == [1, 2]


def test_resume_resets_interrupted_node_step(tmp_path):
    repo_root, conn = make_git_awf_repo(tmp_path)

    call_count = 0

    def resume_activity(_conn, _args):
        nonlocal call_count
        call_count += 1
        return {"call": call_count}

    ACTIVITY_REGISTRY["test_resume_activity"] = ActivityRegistration("local", resume_activity)

    publish_workflow(
        repo_root,
        {
            "apiVersion": "awf/v1",
            "kind": "Workflow",
            "metadata": {"name": "resume-retry-demo", "version": "1.0.0", "digest": "sha256:resume-1"},
            "spec": {
                "inputSchema": {},
                "outputSchema": {},
                "budgets": {"maxRetries": 2, "backoffSeconds": 0.0},
                "nodes": [
                    {
                        "id": "work_node",
                        "type": "activity",
                        "function": "test_resume_activity",
                        "next": None,
                    }
                ],
                "outputs": {},
            },
        },
    )

    # Start a run manually in DB to simulate a crash mid-run during RETRY_WAIT
    run_id = "interrupted-run-1"
    create_run(conn, run_id=run_id, workflow_ref="resume-retry-demo@1.0.0")
    conn.execute("UPDATE runs SET status = 'RUNNING' WHERE run_id = ?", (run_id,))
    # Insert an interrupted attempt row in RETRY_WAIT
    conn.execute(
        "INSERT INTO steps (step_id, run_id, node_id, attempt, status, input_json, started_at) "
        "VALUES ('interrupted-run-1:work_node#1', 'interrupted-run-1', 'work_node', 1, 'RETRY_WAIT', '{}', '2026-09-02T00:00:00Z')",
    )
    conn.commit()

    # Now resume the run
    resumed = op_run_resume(repo_root, conn)
    assert len(resumed) == 1
    assert resumed[0]["status"] == "SUCCEEDED"

    # Verify that the interrupted attempt was reset and node started cleanly from attempt 1
    steps = conn.execute(
        "SELECT step_id, attempt, status FROM steps WHERE run_id = ?",
        (run_id,),
    ).fetchall()
    assert len(steps) == 1
    assert steps[0]["attempt"] == 1
    assert steps[0]["status"] == "SUCCEEDED"
