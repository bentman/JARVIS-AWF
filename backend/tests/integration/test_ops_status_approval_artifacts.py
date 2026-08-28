import pytest
from backend.tests.support import make_awf_repo, seed_approval, seed_run_step

from awf.gates.artifacts import write_finding_artifact
from awf.gates.schema import Finding
from awf.ops.approval import op_approval_approve, op_approval_list, op_approval_reject
from awf.ops.artifact import op_artifact_list, op_artifact_read
from awf.ops.control import op_control_center_run_detail, op_control_center_summary
from awf.ops.run import _cleanup_run_workspace, op_run_list, op_run_outcome, op_run_status
from awf.ops.shared import CoreOpError
from awf.ops.system import op_secret_list_names, op_secret_set, op_system_doctor, op_system_readiness


def test_run_status_and_list_reflect_real_rows(tmp_path):
    _repo_root, conn = make_awf_repo(tmp_path)
    seed_run_step(conn)
    conn.execute(
        "UPDATE runs SET status = 'SUCCEEDED', output_json = ? WHERE run_id = ?",
        ('{"outputs": {"response_text": "Run completed usefully."}}', "run-1"),
    )
    conn.commit()

    status = op_run_status(conn, run_id="run-1")
    assert status["run_id"] == "run-1"
    assert len(status["steps"]) == 1
    assert status["outcome"]["response_text"] == "Run completed usefully."
    assert [row["run_id"] for row in op_run_list(conn)] == ["run-1"]
    assert op_run_list(conn)[0]["outcome"]["next_action"] == "No operator action required."


def test_terminal_failed_run_removes_scratch_but_keeps_worktree(tmp_path):
    repo_root = tmp_path / "repo"
    scratch = repo_root / "cache" / "sandbox" / "run-1"
    worktree = repo_root / "cache" / "worktrees" / "run-1"
    scratch.mkdir(parents=True)
    worktree.mkdir(parents=True)
    (scratch / "auth.json").write_text("temporary credential copy", encoding="utf-8")
    (worktree / "debug.txt").write_text("keep failed worktree", encoding="utf-8")

    _cleanup_run_workspace(repo_root, "run-1", {"status": "FAILED"})

    assert not scratch.exists()
    assert worktree.exists()


def test_run_status_raises_for_unknown_run(tmp_path):
    _repo_root, conn = make_awf_repo(tmp_path)
    with pytest.raises(CoreOpError):
        op_run_status(conn, run_id="does-not-exist")
    with pytest.raises(CoreOpError):
        op_run_outcome(conn, run_id="does-not-exist")


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
    assert (
        '"summary": "ok"'
        in op_artifact_read(conn, artifact_id=artifact_id, artifacts_root=repo_root / "data" / "artifacts")["content"]
    )


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
    calls = {"readiness": 0}

    def llm_servers(_repo_root, *, host_profile_id=None, probe_timeout_seconds=2.0):
        assert host_profile_id == "linux-x64-cpu"
        assert probe_timeout_seconds == 0.25
        return {"default_server": "llama-server", "servers": {}}

    def readiness(_repo_root):
        calls["readiness"] += 1
        return {"profile_id": "linux-x64-cpu", "readiness": {}}

    def doctor(_repo_root, *, readiness=None, quick=False):
        assert readiness == {"profile_id": "linux-x64-cpu", "readiness": {}}
        assert quick is True
        return {"status": "ok", "checks": [], "next_actions": []}

    monkeypatch.setattr("awf.ops.control.op_llm_servers", llm_servers)
    monkeypatch.setattr(
        "awf.ops.control.op_llm_serve",
        lambda _repo_root, _conn, *, action, **kwargs: {
            "state": "stopped",
            "action": action,
            "probe_timeout_seconds": kwargs["probe_timeout_seconds"],
        },
    )
    monkeypatch.setattr("awf.ops.control.op_system_readiness", readiness)
    monkeypatch.setattr("awf.ops.control.op_system_doctor", doctor)

    summary = op_control_center_summary(repo_root, conn)

    assert calls["readiness"] == 1
    assert summary["runs"][0]["run_id"] == "run-1"
    assert summary["approvals"][0]["approval_id"] == "ap-1"
    assert summary["llm"]["status"]["state"] == "stopped"
    assert summary["llm"]["status"]["probe_timeout_seconds"] == 0.25
    assert summary["readiness"]["profile_id"] == "linux-x64-cpu"
    assert summary["doctor"]["status"] == "ok"
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
    assert detail["outcome"]["evidence"][0]["artifact_id"] == verdict_id
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


def test_system_doctor_reports_operator_next_actions(tmp_path, monkeypatch):
    repo_root, _conn = make_awf_repo(tmp_path)
    (repo_root / ".env").write_text("AWF_SECRET_KEY=local-key\n", encoding="utf-8")
    (repo_root / "cache" / "sandbox").mkdir(parents=True)
    (repo_root / "cache" / "temp").mkdir(parents=True)
    workflow_dir = repo_root / "config" / "app_registry" / "workflows" / "assistant-default"
    workflow_dir.mkdir(parents=True)
    (workflow_dir / "1.0.0.yaml").write_text(
        "apiVersion: awf/v1\nkind: Workflow\n"
        "metadata: {name: assistant-default, version: 1.0.0, digest: 'sha256:demo'}\n"
        "spec:\n"
        "  inputSchema: {type: object, properties: {objective: {type: string}}, required: [objective]}\n"
        "  outputSchema: {type: object, properties: {response_text: {type: string}}, required: [response_text]}\n"
        "  budgets: {}\n"
        "  nodes: [{id: reply, type: activity, function: assistant_reply, args: {objective: '{{ input.objective }}'}, next: null}]\n"
        "  outputs: {response_text: '{{ engine.reply_response_text }}'}\n",
        encoding="utf-8",
    )
    capability_dir = repo_root / "config" / "app_registry" / "capabilities" / "assistant_reply"
    capability_dir.mkdir(parents=True)
    (capability_dir / "1.0.0.yaml").write_text(
        "identity: {type: activity, provider: awf, name: assistant_reply, version: 1.0.0}\n"
        "schema: {input: schemas/assistant_reply.input.json, output: schemas/assistant_reply.output.json}\n"
        "effects: {operation: execute, reversible: true, idempotent: true, external_side_effect: false}\n"
        "risk_class: R0\n"
        "approval: never\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "awf.ops.system.op_system_readiness",
        lambda _repo_root: {
            "profile_id": "linux-x64-cpu",
            "tokens": [],
            "readiness": {"stt": {"device": "cpu", "ready": True, "reason": "available"}},
        },
    )
    monkeypatch.setattr(
        "awf.ops.registry.op_registry_validate", lambda path, kind=None: {"path": str(path), "kind": kind}
    )
    monkeypatch.setattr("awf.ops.system._command_version", lambda command, *args: (False, None))

    report = op_system_doctor(repo_root)

    assert report["status"] == "warn"
    assert report["first_run_command"].startswith("awf run assistant-default")
    assert any("Node.js" in action for action in report["next_actions"])


def test_system_doctor_accepts_node_24_lts_frontend_floor(tmp_path, monkeypatch):
    repo_root, _conn = make_awf_repo(tmp_path)
    (repo_root / "frontend" / "node_modules").mkdir(parents=True)

    def version(command, *args):
        if command == "node":
            return True, "v24.19.0"
        if command == "npm":
            return True, "11.6.2"
        return False, None

    monkeypatch.setattr("awf.ops.system._command_version", version)

    report = op_system_doctor(repo_root)
    check = next(item for item in report["checks"] if item["name"] == "frontend")

    assert check["status"] == "ok"
    assert "Node.js" not in " ".join(report["next_actions"])


def test_system_doctor_warns_below_node_24_lts_frontend_floor(tmp_path, monkeypatch):
    repo_root, _conn = make_awf_repo(tmp_path)
    (repo_root / "frontend" / "node_modules").mkdir(parents=True)

    def version(command, *args):
        if command == "node":
            return True, "v24.14.0"
        if command == "npm":
            return True, "11.6.2"
        return False, None

    monkeypatch.setattr("awf.ops.system._command_version", version)

    report = op_system_doctor(repo_root)
    check = next(item for item in report["checks"] if item["name"] == "frontend")

    assert check["status"] == "warn"
    assert check["next_action"] == "Install Node.js 24 LTS >=24.15.0 and rerun `npm --prefix frontend install`."
