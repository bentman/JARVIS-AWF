import pytest
from backend.tests.support import make_awf_repo, seed_approval, seed_run_step

from awf.cli.core_ops import (
    CoreOpError,
    op_approval_approve,
    op_approval_list,
    op_approval_reject,
    op_artifact_list,
    op_artifact_read,
    op_control_center_run_detail,
    op_control_center_summary,
    op_run_list,
    op_run_status,
    op_secret_list_names,
    op_secret_set,
    op_system_readiness,
)
from awf.gates.artifacts import write_finding_artifact
from awf.gates.schema import Finding


def test_run_status_and_list_reflect_real_rows(tmp_path):
    _repo_root, conn = make_awf_repo(tmp_path)
    seed_run_step(conn)

    status = op_run_status(conn, run_id="run-1")
    assert status["run_id"] == "run-1"
    assert len(status["steps"]) == 1
    assert [row["run_id"] for row in op_run_list(conn)] == ["run-1"]


def test_run_status_raises_for_unknown_run(tmp_path):
    _repo_root, conn = make_awf_repo(tmp_path)
    with pytest.raises(CoreOpError):
        op_run_status(conn, run_id="does-not-exist")


def test_approval_list_and_decisions(tmp_path):
    _repo_root, conn = make_awf_repo(tmp_path)
    seed_run_step(conn)
    seed_approval(conn, approval_id="ap-1", status="pending")
    seed_approval(conn, approval_id="ap-2", status="approved")

    assert [approval["approval_id"] for approval in op_approval_list(conn)] == ["ap-1"]
    assert op_approval_approve(conn, approval_id="ap-1")["status"] == "approved"
    with pytest.raises(CoreOpError):
        op_approval_reject(conn, approval_id="ap-1", reason="too late")


def test_reject_records_reason_and_unknown_approval_raises(tmp_path):
    _repo_root, conn = make_awf_repo(tmp_path)
    seed_run_step(conn)
    seed_approval(conn)

    assert op_approval_reject(conn, approval_id="ap-1", reason="not safe") == {
        "approval_id": "ap-1",
        "status": "rejected",
        "reason": "not safe",
    }
    with pytest.raises(CoreOpError):
        op_approval_approve(conn, approval_id="missing")


def test_artifact_list_and_read(tmp_path):
    repo_root, conn = make_awf_repo(tmp_path)
    seed_run_step(conn, step_id="s1", node_id="check")
    artifact_id = write_finding_artifact(
        conn,
        artifacts_root=repo_root / "data" / "artifacts",
        run_id="run-1",
        step_id="s1",
        finding=Finding(role="verifier", category="correctness", severity="low", summary="ok"),
    )

    assert [artifact["artifact_id"] for artifact in op_artifact_list(conn, run_id="run-1")] == [artifact_id]
    assert '"summary": "ok"' in op_artifact_read(
        conn, artifact_id=artifact_id, artifacts_root=repo_root / "data" / "artifacts"
    )["content"]


def test_secret_set_and_list_names_roundtrip(tmp_path):
    from cryptography.fernet import Fernet

    repo_root, conn = make_awf_repo(tmp_path)
    (repo_root / ".env").write_text(f"AWF_SECRET_KEY={Fernet.generate_key().decode('ascii')}\n")

    op_secret_set(repo_root, conn, name="api-key", value="sekret")

    assert op_secret_list_names(conn) == ["api-key"]


def test_control_center_summary_aggregates_existing_core_state(tmp_path, monkeypatch):
    repo_root, conn = make_awf_repo(tmp_path)
    seed_run_step(conn)
    seed_approval(conn, risk_class="R2")

    monkeypatch.setattr(
        "awf.cli.core_ops.op_llm_servers",
        lambda _repo_root: {"default_server": "llama-server", "servers": {}},
    )
    monkeypatch.setattr(
        "awf.cli.core_ops.op_llm_serve",
        lambda _repo_root, _conn, *, action: {"state": "stopped", "action": action},
    )
    monkeypatch.setattr(
        "awf.cli.core_ops.op_system_readiness",
        lambda _repo_root: {"profile_id": "linux-x64-cpu", "readiness": {}},
    )

    summary = op_control_center_summary(repo_root, conn)

    assert summary["runs"][0]["run_id"] == "run-1"
    assert summary["approvals"][0]["approval_id"] == "ap-1"
    assert summary["llm"]["status"]["state"] == "stopped"
    assert summary["readiness"]["profile_id"] == "linux-x64-cpu"
    assert "skills" in summary["registry_counts"]


def test_control_center_run_detail_combines_run_artifacts_and_timeline(tmp_path):
    repo_root, conn = make_awf_repo(tmp_path)
    seed_run_step(conn, step_id="s1", node_id="check")
    verdict_id = write_finding_artifact(
        conn,
        artifacts_root=repo_root / "data" / "artifacts",
        run_id="run-1",
        step_id="s1",
        finding=Finding(role="verifier", category="correctness", severity="low", summary="ok"),
    )
    conn.execute("UPDATE artifacts SET artifact_type = 'verdict' WHERE artifact_id = ?", (verdict_id,))
    conn.commit()

    detail = op_control_center_run_detail(repo_root, conn, run_id="run-1")

    assert detail["run"]["run_id"] == "run-1"
    assert detail["artifacts"][0]["artifact_id"] == verdict_id
    assert detail["verdicts"][0]["artifact_id"] == verdict_id
    assert detail["timeline"]["run"]["run_id"] == "run-1"


def test_system_readiness_returns_degraded_payload_when_probe_fails(tmp_path, monkeypatch):
    repo_root, _conn = make_awf_repo(tmp_path)

    def fail(_repo_root):
        raise RuntimeError("probe failed")

    monkeypatch.setattr("awf.hardware.profiler.resolve_hardware_profile_id", fail)

    readiness = op_system_readiness(repo_root)

    assert readiness["profile_id"] is None
    assert readiness["error"] == "probe failed"
