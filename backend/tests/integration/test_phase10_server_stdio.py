import io
import json

from awf.db.bootstrap import init_db
from awf.db.connection import get_connection
from awf.engine.run import create_run
from awf.server.stdio import handle_line


def make_repo(tmp_path):
    repo_root = tmp_path / "repo"
    (repo_root / "data" / "awf_db").mkdir(parents=True)
    db_path = repo_root / "data" / "awf_db" / "awf.db"
    init_db(db_path)
    conn = get_connection(db_path)
    return repo_root, conn


def send(repo_root, conn, request: dict) -> dict:
    out = io.StringIO()
    handle_line(repo_root, conn, json.dumps(request), out)
    return json.loads(out.getvalue().strip())


def test_run_status_over_jsonrpc(tmp_path):
    repo_root, conn = make_repo(tmp_path)
    create_run(conn, run_id="run-1", workflow_ref="demo@1.0.0")

    response = send(
        repo_root, conn, {"jsonrpc": "2.0", "id": 1, "method": "awf/run.status", "params": {"runId": "run-1"}}
    )

    assert response["id"] == 1
    assert response["result"]["run_id"] == "run-1"


def test_unknown_method_returns_json_rpc_error(tmp_path):
    repo_root, conn = make_repo(tmp_path)

    response = send(repo_root, conn, {"jsonrpc": "2.0", "id": 2, "method": "awf/not.a.real.method", "params": {}})

    assert response["error"]["code"] == -32601


def test_malformed_json_returns_parse_error(tmp_path):
    repo_root, conn = make_repo(tmp_path)
    out = io.StringIO()
    handle_line(repo_root, conn, "{not json", out)
    response = json.loads(out.getvalue().strip())

    assert response["error"]["code"] == -32700


def test_missing_required_param_returns_internal_error_not_crash(tmp_path):
    repo_root, conn = make_repo(tmp_path)

    response = send(repo_root, conn, {"jsonrpc": "2.0", "id": 3, "method": "awf/run.status", "params": {}})

    assert "error" in response
    assert response["id"] == 3


def test_events_subscribe_reports_unsupported(tmp_path):
    repo_root, conn = make_repo(tmp_path)

    response = send(repo_root, conn, {"jsonrpc": "2.0", "id": 4, "method": "awf/events.subscribe", "params": {}})

    assert response["error"]["code"] == -32601


def test_control_center_methods_over_jsonrpc(tmp_path, monkeypatch):
    repo_root, conn = make_repo(tmp_path)
    create_run(conn, run_id="run-1", workflow_ref="demo@1.0.0")
    monkeypatch.setattr("awf.cli.core_ops.op_llm_servers", lambda _repo_root: {"servers": {}})
    monkeypatch.setattr("awf.cli.core_ops.op_llm_serve", lambda _repo_root, _conn, *, action: {"state": "stopped"})
    monkeypatch.setattr(
        "awf.cli.core_ops.op_system_readiness",
        lambda _repo_root: {"profile_id": "linux-x64-cpu", "readiness": {}},
    )

    summary = send(repo_root, conn, {"jsonrpc": "2.0", "id": 41, "method": "awf/control.summary", "params": {}})
    detail = send(
        repo_root,
        conn,
        {"jsonrpc": "2.0", "id": 42, "method": "awf/control.runDetail", "params": {"runId": "run-1"}},
    )
    readiness = send(repo_root, conn, {"jsonrpc": "2.0", "id": 43, "method": "awf/system.readiness", "params": {}})

    assert summary["result"]["runs"][0]["run_id"] == "run-1"
    assert detail["result"]["run"]["run_id"] == "run-1"
    assert readiness["result"]["profile_id"] == "linux-x64-cpu"


def test_llm_status_methods_over_jsonrpc(tmp_path, monkeypatch):
    repo_root, conn = make_repo(tmp_path)
    monkeypatch.setattr("awf.cli.core_ops.op_llm_servers", lambda _repo_root: {"default_server": "llama-server"})
    monkeypatch.setattr("awf.cli.core_ops.op_llm_models", lambda _repo_root: {"local_models": []})
    monkeypatch.setattr("awf.cli.core_ops.op_llm_serve", lambda _repo_root, _conn, *, action: {"state": "stopped"})

    servers = send(repo_root, conn, {"jsonrpc": "2.0", "id": 51, "method": "awf/llm.servers", "params": {}})
    models = send(repo_root, conn, {"jsonrpc": "2.0", "id": 52, "method": "awf/llm.models", "params": {}})
    status = send(repo_root, conn, {"jsonrpc": "2.0", "id": 53, "method": "awf/llm.serveStatus", "params": {}})

    assert servers["result"]["default_server"] == "llama-server"
    assert models["result"]["local_models"] == []
    assert status["result"]["state"] == "stopped"


def test_approval_approve_over_jsonrpc(tmp_path):
    repo_root, conn = make_repo(tmp_path)
    create_run(conn, run_id="run-1", workflow_ref="demo@1.0.0")
    from awf.engine.run import create_step

    create_step(conn, step_id="s1", run_id="run-1", node_id="n1")
    conn.execute(
        "INSERT INTO approvals (approval_id, run_id, step_id, action_digest, status, requested_at) "
        "VALUES ('ap-1', 'run-1', 's1', 'sha256:x', 'pending', '2026-01-01T00:00:00Z')"
    )
    conn.commit()

    response = send(
        repo_root,
        conn,
        {"jsonrpc": "2.0", "id": 5, "method": "awf/approval.approve", "params": {"approvalId": "ap-1"}},
    )

    assert response["result"]["status"] == "approved"


def test_approval_approve_over_jsonrpc_refuses_r2_from_voice_channel(tmp_path):
    repo_root, conn = make_repo(tmp_path)
    create_run(conn, run_id="run-1", workflow_ref="demo@1.0.0")
    from awf.engine.run import create_step

    create_step(conn, step_id="s1", run_id="run-1", node_id="n1")
    conn.execute(
        "INSERT INTO approvals (approval_id, run_id, step_id, action_digest, status, requested_at) "
        "VALUES ('ap-1', 'run-1', 's1', 'sha256:x', 'pending', '2026-01-01T00:00:00Z')"
    )
    conn.commit()

    response = send(
        repo_root,
        conn,
        {
            "jsonrpc": "2.0",
            "id": 6,
            "method": "awf/approval.approve",
            "params": {"approvalId": "ap-1", "channel": "voice", "riskClass": "R2"},
        },
    )

    assert response["result"]["status"] == "pending"
    assert response["result"]["requires_on_screen_confirmation"] is True
    row = conn.execute("SELECT status FROM approvals WHERE approval_id = 'ap-1'").fetchone()
    assert row["status"] == "pending"


def test_proposal_get_over_jsonrpc(tmp_path):
    repo_root, conn = make_repo(tmp_path)
    proposal_path = repo_root / "data" / "proposals" / "workflows" / "p1" / "demo" / "0.1.0.yaml"
    proposal_path.parent.mkdir(parents=True)
    proposal_path.write_text("apiVersion: awf/v1\n", encoding="utf-8")
    conn.execute(
        "INSERT INTO registry_proposals "
        "(proposal_id, kind, name, version, status, draft_digest, draft_path, summary, created_at, updated_at) "
        "VALUES ('p1', 'workflows', 'demo', '0.1.0', 'draft', 'abc', ?, 'summary', 't', 't')",
        (str(proposal_path.relative_to(repo_root)),),
    )
    conn.commit()

    response = send(repo_root, conn, {"jsonrpc": "2.0", "id": 7, "method": "awf/proposal.get", "params": {"proposalId": "p1"}})

    assert response["result"]["proposal_id"] == "p1"
    assert response["result"]["content"] == "apiVersion: awf/v1\n"


def test_memory_search_over_jsonrpc(tmp_path):
    repo_root, conn = make_repo(tmp_path)
    profile = repo_root / "config" / "app_registry" / "memory-profiles" / "default" / "1.0.0.yaml"
    profile.parent.mkdir(parents=True)
    profile.write_text(
        """
apiVersion: awf/v1
kind: MemoryProfile
metadata: {name: default, version: 1.0.0, digest: sha256:test}
spec:
  enabled: true
  maximum_data_class: internal
  retrieval: {maxItems: 10, maxTokens: 2000, includeEpisodic: true, includeSemantic: true, minConfidence: 0.0}
  retention: {activeSessionTtlHours: 24, requireExplicitSemanticPublish: true}
  embedding: {enabled: false, modelProfileRef: null, version: none}
""",
        encoding="utf-8",
    )

    response = send(
        repo_root,
        conn,
        {"jsonrpc": "2.0", "id": 8, "method": "awf/memory.search", "params": {"query": "targeted"}},
    )

    assert response["id"] == 8
    assert response["result"]["semantic"] == []
