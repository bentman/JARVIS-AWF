import json
import shutil
import sqlite3

from awf.adapters.copilot_guard_hook import evaluate_pre_tool_use
from awf.db.bootstrap import init_db


def _copy_capability(repo_root, tmp_repo, name: str) -> None:
    source = repo_root / "config" / "app_registry" / "capabilities" / name / "1.0.0.yaml"
    target = tmp_repo / "config" / "app_registry" / "capabilities" / name / "1.0.0.yaml"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def test_copilot_pre_tool_use_hook_calls_guard_and_records_decision(monkeypatch, tmp_path, repo_root):
    tmp_repo = tmp_path / "repo"
    _copy_capability(repo_root, tmp_repo, "fs_write")
    db_path = tmp_repo / "data" / "awf_db" / "awf.db"
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO runs (run_id, workflow_ref, status, input_json, budget_json, created_at, updated_at) "
            "VALUES ('run-1', 'wf@1.0.0#sha256:abc', 'RUNNING', '{}', '{}', 't', 't')"
        )
        conn.execute(
            "INSERT INTO steps (step_id, run_id, node_id, attempt, status, input_json, started_at) "
            "VALUES ('step-1', 'run-1', 'agent', 1, 'RUNNING', '{}', 't')"
        )
        conn.commit()
    finally:
        conn.close()

    monkeypatch.setenv("AWF_REPO_ROOT", str(tmp_repo))
    monkeypatch.setenv("AWF_RUN_ID", "run-1")
    monkeypatch.setenv("AWF_STEP_ID", "step-1")
    monkeypatch.setenv("AWF_ACTOR", "copilot")
    monkeypatch.setenv("AWF_ROLE", "builder")
    monkeypatch.setenv("AWF_AGENT_ALLOWLIST", json.dumps(["fs_write@1.0.0"]))

    response = evaluate_pre_tool_use({"toolName": "edit", "toolArgs": {"file": "demo.py"}})

    assert response == {"permissionDecision": "allow"}
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute("SELECT new_status, reason_code, payload_json FROM events").fetchone()
    finally:
        conn.close()
    assert row[0] == "allow"
    assert row[1] == "approval_never"
    payload = json.loads(row[2])
    assert payload["capability_ref"] == "fs_write@1.0.0"
    assert payload["copilot_tool_name"] == "edit"
    assert payload["copilot_tool_args_type"] == "object"


def test_copilot_pre_tool_use_hook_denies_unmapped_tool(monkeypatch, tmp_path):
    tmp_repo = tmp_path / "repo"
    init_db(tmp_repo / "data" / "awf_db" / "awf.db")
    monkeypatch.setenv("AWF_REPO_ROOT", str(tmp_repo))
    monkeypatch.setenv("AWF_RUN_ID", "run-1")
    monkeypatch.setenv("AWF_AGENT_ALLOWLIST", json.dumps([]))

    response = evaluate_pre_tool_use({"toolName": "unknown_tool", "toolArgs": {}})

    assert response["permissionDecision"] == "deny"
    assert "no AWF capability mapping" in response["permissionDecisionReason"]
