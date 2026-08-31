import json

from backend.tests.support import make_awf_repo, publish_workflow, seed_approval, seed_run_step

from awf.clock import utc_now_rfc3339
from awf.gates.artifacts import write_finding_artifact
from awf.gates.schema import Finding
from awf.ops.control import op_control_center_run_detail, op_control_center_summary


def _stable_host(monkeypatch):
    monkeypatch.setattr(
        "awf.ops.control.op_system_readiness",
        lambda _repo_root: {
            "profile_id": "linux-x64-cpu",
            "inventory": None,
            "tokens": [],
            "readiness": {"llm": {"device": "cpu", "ready": True, "reason": "available"}},
        },
    )
    monkeypatch.setattr(
        "awf.ops.control.op_system_doctor",
        lambda _repo_root, *, readiness=None, quick=False: {
            "status": "ok",
            "checks": [],
            "next_actions": [],
            "first_run_command": 'awf run assistant-default@1.0.0 --objective "check the system"',
        },
    )
    monkeypatch.setattr(
        "awf.ops.control.op_llm_servers",
        lambda _repo_root, *, host_profile_id=None, probe_timeout_seconds=0.25: {
            "default_server": "llama-server",
            "servers": {},
        },
    )
    monkeypatch.setattr(
        "awf.ops.control.op_llm_serve",
        lambda _repo_root, _conn, *, action, **kwargs: {"state": "running", "server_id": "llama-server"},
    )


def _kinds(summary):
    return [item["kind"] for item in summary["operator_work_items"]]


def test_operator_work_items_clean_idle_system(tmp_path, monkeypatch):
    _stable_host(monkeypatch)
    repo_root, conn = make_awf_repo(tmp_path)

    summary = op_control_center_summary(repo_root, conn)

    assert _kinds(summary) == ["idle"]
    assert summary["operator_next_actions"][0]["command"].startswith("awf run assistant-default@1.0.0")
    assert summary["operator_work_items"][0]["primary_action"]["kind"] == "workflow.start"


def test_operator_work_items_not_ready_llm_and_readiness(tmp_path, monkeypatch):
    _stable_host(monkeypatch)
    repo_root, conn = make_awf_repo(tmp_path)
    monkeypatch.setattr(
        "awf.ops.control.op_system_readiness",
        lambda _repo_root: {
            "profile_id": "linux-x64-cpu",
            "inventory": None,
            "tokens": [],
            "readiness": {"stt": {"device": "cpu", "ready": False, "reason": "model missing"}},
        },
    )
    monkeypatch.setattr(
        "awf.ops.control.op_llm_serve",
        lambda _repo_root, _conn, *, action, **kwargs: {"state": "stopped", "reason": "no model selected"},
    )

    summary = op_control_center_summary(repo_root, conn)

    assert "readiness" in _kinds(summary)
    assert "llm" in _kinds(summary)
    assert summary["operator_next_actions"][0]["command"] == "awf doctor"


def test_operator_work_items_active_run(tmp_path, monkeypatch):
    _stable_host(monkeypatch)
    repo_root, conn = make_awf_repo(tmp_path)
    seed_run_step(conn)
    conn.execute("UPDATE runs SET status = 'RUNNING' WHERE run_id = 'run-1'")
    conn.commit()

    summary = op_control_center_summary(repo_root, conn)

    assert _kinds(summary) == ["active_run"]
    assert summary["operator_work_items"][0]["command"] == "awf status run-1"


def test_operator_work_items_waiting_approval(tmp_path, monkeypatch):
    _stable_host(monkeypatch)
    repo_root, conn = make_awf_repo(tmp_path)
    seed_run_step(conn)
    seed_approval(conn, risk_class="R2")
    conn.execute("UPDATE runs SET status = 'WAITING_APPROVAL' WHERE run_id = 'run-1'")
    conn.commit()

    summary = op_control_center_summary(repo_root, conn)

    assert _kinds(summary)[:2] == ["approval", "active_run"]
    assert summary["operator_work_items"][0]["approval_id"] == "ap-1"
    assert summary["operator_work_items"][0]["primary_action"]["kind"] == "approval.review"


def test_operator_work_items_failed_run_with_failed_step(tmp_path, monkeypatch):
    _stable_host(monkeypatch)
    repo_root, conn = make_awf_repo(tmp_path)
    seed_run_step(conn)
    conn.execute("UPDATE runs SET status = 'FAILED' WHERE run_id = 'run-1'")
    conn.execute(
        "UPDATE steps SET status = 'FAILED', failure_class = 'TOOL_ERROR', output_json = ? WHERE step_id = 's1'",
        (json.dumps({"error": "boom"}),),
    )
    conn.commit()

    summary = op_control_center_summary(repo_root, conn)

    assert _kinds(summary) == ["failed_run"]
    assert "Failed run" in summary["operator_work_items"][0]["title"]


def test_operator_work_items_ready_improvement_proposal(tmp_path, monkeypatch):
    _stable_host(monkeypatch)
    repo_root, conn = make_awf_repo(tmp_path)
    seed_run_step(conn)
    artifact_id = write_finding_artifact(
        conn,
        artifacts_root=repo_root / "data" / "artifacts",
        run_id="run-1",
        step_id="s1",
        finding=Finding(role="verifier", category="correctness", severity="low", summary="ok"),
    )
    now = utc_now_rfc3339()
    conn.execute(
        "INSERT INTO improvement_proposals "
        "(improvement_id, run_id, target_repo, target_branch, base_commit, candidate_branch, candidate_commit, "
        "diff_digest, patch_artifact_id, status, summary, changed_paths_json, verdict_artifact_id, "
        "validation_artifact_ids_json, created_at, updated_at) "
        "VALUES ('imp-1', 'run-1', '.', 'main', 'a', 'candidate', 'b', 'sha256:diff', ?, "
        "'ready_for_review', 'Ready proposal', '[]', ?, '[]', ?, ?)",
        (artifact_id, artifact_id, now, now),
    )
    conn.commit()

    summary = op_control_center_summary(repo_root, conn)

    assert "improvement" in _kinds(summary)
    assert summary["operator_work_items"][0]["improvement_id"] == "imp-1"


def test_operator_work_items_completed_run_with_evidence_and_detail_timeline(tmp_path, monkeypatch):
    _stable_host(monkeypatch)
    repo_root, conn = make_awf_repo(tmp_path)
    seed_run_step(conn)
    artifact_id = write_finding_artifact(
        conn,
        artifacts_root=repo_root / "data" / "artifacts",
        run_id="run-1",
        step_id="s1",
        finding=Finding(role="verifier", category="correctness", severity="low", summary="ok"),
    )
    conn.execute("UPDATE artifacts SET artifact_type = 'verdict' WHERE artifact_id = ?", (artifact_id,))
    conn.execute("UPDATE runs SET status = 'SUCCEEDED' WHERE run_id = 'run-1'")
    conn.commit()

    summary = op_control_center_summary(repo_root, conn)
    detail = op_control_center_run_detail(repo_root, conn, run_id="run-1")

    assert "completed_evidence" in _kinds(summary)
    assert any(
        item["kind"] == "artifact" and item["artifact_id"] == artifact_id for item in detail["operator_timeline"]
    )
    assert detail["operator_next_actions"][0]["command"] == "awf status run-1"


def test_operator_start_options_include_workflow_schema(tmp_path, monkeypatch):
    _stable_host(monkeypatch)
    repo_root, conn = make_awf_repo(tmp_path)
    publish_workflow(
        repo_root,
        {
            "apiVersion": "awf/v1",
            "kind": "Workflow",
            "metadata": {"name": "guided", "version": "1.0.0", "digest": "sha256:guided"},
            "spec": {
                "inputSchema": {
                    "type": "object",
                    "properties": {"objective": {"type": "string"}, "dry_run": {"type": "boolean"}},
                    "required": ["objective"],
                },
                "outputSchema": {},
                "budgets": {},
                "nodes": [{"id": "check", "type": "gate", "checkCommand": "true", "next": None}],
                "outputs": {},
            },
        },
    )

    summary = op_control_center_summary(repo_root, conn)

    option = next(item for item in summary["operator_start_options"] if item["workflow_ref"] == "guided@1.0.0")
    assert option["primary_action"]["kind"] == "workflow.start"
    assert option["input_schema_summary"]["fields"] == [
        {"name": "objective", "type": "string", "required": True, "enum": None, "description": None, "default": None},
        {"name": "dry_run", "type": "boolean", "required": False, "enum": None, "description": None, "default": None},
    ]
