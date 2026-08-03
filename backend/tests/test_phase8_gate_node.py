import json

from awf.db.bootstrap import init_db
from awf.db.connection import get_connection
from awf.engine.run import create_run
from awf.gates.gate_node import make_trifecta_gate_executor
from awf.workflow.definition import parse_workflow
from awf.workflow.engine import run_workflow_definition


def make_conn(tmp_path):
    db_path = tmp_path / "awf.db"
    init_db(db_path)
    conn = get_connection(db_path)
    create_run(conn, run_id="run-1", workflow_ref="demo@1.0.0")
    return conn


def read_artifact_json(conn, artifacts_root, artifact_id):
    row = conn.execute("SELECT relative_path FROM artifacts WHERE artifact_id = ?", (artifact_id,)).fetchone()
    return json.loads((artifacts_root / row["relative_path"]).read_bytes())


def make_workflow(max_repairs=3):
    return parse_workflow(
        {
            "apiVersion": "awf/v1",
            "kind": "Workflow",
            "metadata": {"name": "demo", "version": "1.0.0", "digest": "sha256:abc"},
            "spec": {
                "inputSchema": {},
                "outputSchema": {},
                "budgets": {"maxRepairIterations": max_repairs},
                "nodes": [
                    {"id": "produce", "type": "agent", "next": "check"},
                    {"id": "check", "type": "gate", "next": None, "onFail": "repair"},
                    {"id": "repair", "type": "agent", "next": "check"},
                ],
                "outputs": {},
            },
        }
    )


def test_default_tier_gate_produces_verdict_and_finding_artifacts(tmp_path):
    conn = make_conn(tmp_path)
    workflow = make_workflow()
    artifacts_root = tmp_path / "artifacts"

    def agent_executor(conn, run_id, step_id, node):
        return {"ok": True}

    gate_executor = make_trifecta_gate_executor(
        check_fn=lambda: True, check_summary="demo check", artifacts_root=artifacts_root,
    )

    result = run_workflow_definition(
        conn, run_id="run-1", workflow=workflow,
        node_executors={"agent": agent_executor, "gate": gate_executor},
    )

    assert result["status"] == "SUCCEEDED"
    assert result["repairs_used"] == 0
    verdict_row = conn.execute(
        "SELECT * FROM artifacts WHERE artifact_id = ?", (result["verdict_artifact_id"],)
    ).fetchone()
    assert verdict_row["artifact_type"] == "verdict"
    verdict_content = read_artifact_json(conn, artifacts_root, result["verdict_artifact_id"])
    assert verdict_content["passed"] is True
    assert verdict_content["reason"] == "no high/critical findings"

    finding_rows = conn.execute("SELECT * FROM artifacts WHERE artifact_type = 'finding'").fetchall()
    assert len(finding_rows) == 1
    finding_content = read_artifact_json(conn, artifacts_root, finding_rows[0]["artifact_id"])
    assert finding_content["severity"] == "low"
    assert finding_content["category"] == "correctness"


def test_gate_fails_then_repairs_then_passes_produces_two_verdicts(tmp_path):
    conn = make_conn(tmp_path)
    workflow = make_workflow()
    artifacts_root = tmp_path / "artifacts"
    check_results = iter([False, True])

    def agent_executor(conn, run_id, step_id, node):
        return {"ok": True}

    gate_executor = make_trifecta_gate_executor(
        check_fn=lambda: next(check_results), check_summary="demo check", artifacts_root=artifacts_root,
    )

    result = run_workflow_definition(
        conn, run_id="run-1", workflow=workflow,
        node_executors={"agent": agent_executor, "gate": gate_executor},
    )

    assert result["status"] == "SUCCEEDED"
    assert result["repairs_used"] == 1
    verdict_rows = conn.execute(
        "SELECT * FROM artifacts WHERE artifact_type = 'verdict' ORDER BY rowid"
    ).fetchall()
    assert len(verdict_rows) == 2
    first_verdict = read_artifact_json(conn, artifacts_root, verdict_rows[0]["artifact_id"])
    second_verdict = read_artifact_json(conn, artifacts_root, verdict_rows[1]["artifact_id"])
    assert first_verdict["passed"] is False
    assert second_verdict["passed"] is True


def test_high_risk_tier_safety_gate_bypass_fails_immediately_without_consuming_budget(tmp_path):
    conn = make_conn(tmp_path)
    workflow = make_workflow(max_repairs=3)
    artifacts_root = tmp_path / "artifacts"

    def agent_executor(conn, run_id, step_id, node):
        return {"ok": True}

    gate_executor = make_trifecta_gate_executor(
        check_fn=lambda: True,
        check_summary="demo check",
        artifacts_root=artifacts_root,
        tier="high-risk",
        guard_bypassed=True,
    )

    result = run_workflow_definition(
        conn, run_id="run-1", workflow=workflow,
        node_executors={"agent": agent_executor, "gate": gate_executor},
    )

    assert result["status"] == "FAILED"
    assert result["repairs_used"] == 0  # terminal failure does not consume the budget
    row = conn.execute("SELECT status FROM runs WHERE run_id = 'run-1'").fetchone()
    assert row["status"] == "FAILED"

    verdict_content = read_artifact_json(conn, artifacts_root, result["verdict_artifact_id"])
    assert verdict_content["passed"] is False

    bypass_findings = [
        f for f in verdict_content["findings"] if f["category"] == "safety_gate_bypass"
    ]
    assert len(bypass_findings) == 1
    assert bypass_findings[0]["severity"] == "critical"
    assert bypass_findings[0]["role"] == "adversary"
