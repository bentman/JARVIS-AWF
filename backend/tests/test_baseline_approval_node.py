import pytest

from awf.cli.core_ops import op_approval_approve, op_approval_reject
from awf.db.bootstrap import init_db
from awf.db.connection import get_connection
from awf.engine.run import create_run, create_step
from awf.workflow.approval import ApprovalRejectedError, make_approval_node_executor
from awf.workflow.definition import parse_workflow
from awf.workflow.engine import run_workflow_definition


@pytest.fixture
def conn(tmp_path):
    db_path = tmp_path / "awf.db"
    init_db(db_path)
    connection = get_connection(db_path)
    create_run(connection, run_id="run-1", workflow_ref="demo@1.0.0")
    create_step(connection, step_id="step-1", run_id="run-1", node_id="approve-deploy")
    return connection


def test_first_call_requests_approval_and_waits(conn):
    executor = make_approval_node_executor()
    output = executor(conn, "run-1", "step-1", {"id": "approve-deploy", "type": "approval"})

    assert output["waiting_input"] is True
    row = conn.execute("SELECT status FROM steps WHERE step_id = 'step-1'").fetchone()
    assert row["status"] == "WAITING_APPROVAL"
    run_row = conn.execute("SELECT status FROM runs WHERE run_id = 'run-1'").fetchone()
    assert run_row["status"] == "WAITING_APPROVAL"

    approval_row = conn.execute("SELECT status, action_digest FROM approvals WHERE step_id = 'step-1'").fetchone()
    assert approval_row["status"] == "pending"
    assert approval_row["action_digest"].startswith("sha256:")


def test_declared_risk_class_is_stored_on_the_approval_row(conn):
    executor = make_approval_node_executor()
    executor(conn, "run-1", "step-1", {"id": "approve-deploy", "type": "approval", "riskClass": "R2"})

    row = conn.execute("SELECT risk_class FROM approvals WHERE step_id = 'step-1'").fetchone()
    assert row["risk_class"] == "R2"


def test_undeclared_risk_class_stores_null_not_a_guessed_default(conn):
    executor = make_approval_node_executor()
    executor(conn, "run-1", "step-1", {"id": "approve-deploy", "type": "approval"})

    row = conn.execute("SELECT risk_class FROM approvals WHERE step_id = 'step-1'").fetchone()
    assert row["risk_class"] is None


def test_still_pending_keeps_waiting_without_reasking(conn):
    executor = make_approval_node_executor()
    first = executor(conn, "run-1", "step-1", {"id": "approve-deploy", "type": "approval"})
    second = executor(conn, "run-1", "step-1", {"id": "approve-deploy", "type": "approval"})

    assert first["approval_id"] == second["approval_id"]
    assert second["waiting_input"] is True
    count = conn.execute("SELECT COUNT(*) AS n FROM approvals WHERE step_id = 'step-1'").fetchone()["n"]
    assert count == 1


def test_approved_decision_completes_the_step(conn):
    executor = make_approval_node_executor()
    requested = executor(conn, "run-1", "step-1", {"id": "approve-deploy", "type": "approval"})

    op_approval_approve(conn, approval_id=requested["approval_id"])
    output = executor(conn, "run-1", "step-1", {"id": "approve-deploy", "type": "approval"})

    assert output["approved"] is True
    row = conn.execute("SELECT status, output_json FROM steps WHERE step_id = 'step-1'").fetchone()
    assert row["status"] == "SUCCEEDED"

    # Replaying after SUCCEEDED returns the cached output, doesn't re-decide.
    replayed = executor(conn, "run-1", "step-1", {"id": "approve-deploy", "type": "approval"})
    assert replayed == output


def test_rejected_decision_fails_the_step_with_approval_rejected(conn):
    executor = make_approval_node_executor()
    requested = executor(conn, "run-1", "step-1", {"id": "approve-deploy", "type": "approval"})

    op_approval_reject(conn, approval_id=requested["approval_id"], reason="not now")

    with pytest.raises(ApprovalRejectedError):
        executor(conn, "run-1", "step-1", {"id": "approve-deploy", "type": "approval"})

    row = conn.execute("SELECT status, failure_class FROM steps WHERE step_id = 'step-1'").fetchone()
    assert row["status"] == "FAILED"
    assert row["failure_class"] == "APPROVAL_REJECTED"


def test_run_workflow_definition_waits_then_resumes_past_a_real_approval(tmp_path):
    db_path = tmp_path / "awf.db"
    init_db(db_path)
    conn = get_connection(db_path)
    create_run(conn, run_id="run-2", workflow_ref="demo@1.0.0")

    workflow = parse_workflow(
        {
            "apiVersion": "awf/v1",
            "kind": "Workflow",
            "metadata": {"name": "demo", "version": "1.0.0", "digest": "sha256:abc"},
            "spec": {
                "inputSchema": {}, "outputSchema": {}, "budgets": {},
                "nodes": [{"id": "confirm", "type": "approval", "next": None}],
                "outputs": {},
            },
        }
    )
    executors = {"approval": make_approval_node_executor()}

    first = run_workflow_definition(conn, run_id="run-2", workflow=workflow, node_executors=executors)
    assert first["status"] == "WAITING_INPUT"
    run_row = conn.execute("SELECT status FROM runs WHERE run_id = 'run-2'").fetchone()
    assert run_row["status"] == "WAITING_APPROVAL"

    approval_id = conn.execute(
        "SELECT approval_id FROM approvals WHERE run_id = 'run-2'"
    ).fetchone()["approval_id"]
    op_approval_approve(conn, approval_id=approval_id)

    second = run_workflow_definition(conn, run_id="run-2", workflow=workflow, node_executors=executors)
    assert second["status"] == "SUCCEEDED"
