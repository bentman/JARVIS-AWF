import io
import json

from awf.db.bootstrap import init_db
from awf.db.connection import get_connection
from awf.engine.run import create_run
from awf.events.writer import write_event
from awf.server.stdio import handle_line, serve_stdio


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


def test_events_subscribe_returns_event_snapshot(tmp_path):
    repo_root, conn = make_repo(tmp_path)
    create_run(conn, run_id="run-1", workflow_ref="demo@1.0.0")
    write_event(conn, run_id="run-1", new_status="RUNNING", actor="test", reason_code="demo")

    response = send(
        repo_root,
        conn,
        {"jsonrpc": "2.0", "id": 4, "method": "awf/events.subscribe", "params": {"runId": "run-1"}},
    )

    assert response["result"]["streaming"] is False
    assert any(event["reason_code"] == "demo" for event in response["result"]["events"])


def test_serve_stdio_accepts_multiple_requests_in_one_stream(tmp_path):
    repo_root, conn = make_repo(tmp_path)
    create_run(conn, run_id="run-1", workflow_ref="demo@1.0.0")
    conn.close()
    in_stream = io.StringIO(
        "\n".join(
            [
                json.dumps({"jsonrpc": "2.0", "id": 1, "method": "awf/run.status", "params": {"runId": "run-1"}}),
                json.dumps({"jsonrpc": "2.0", "id": 2, "method": "awf/events.subscribe", "params": {"runId": "run-1"}}),
                "",
            ]
        )
    )
    out_stream = io.StringIO()

    serve_stdio(repo_root, in_stream=in_stream, out_stream=out_stream)

    responses = [json.loads(line) for line in out_stream.getvalue().splitlines()]
    assert {response["id"] for response in responses} == {1, 2}
    assert any(response["id"] == 1 and response["result"]["run_id"] == "run-1" for response in responses)
    assert any(response["id"] == 2 and response["result"]["streaming"] is False for response in responses)


def test_control_center_methods_over_jsonrpc(tmp_path, monkeypatch):
    repo_root, conn = make_repo(tmp_path)
    create_run(conn, run_id="run-1", workflow_ref="demo@1.0.0")
    monkeypatch.setattr("awf.cli.core_ops.op_llm_servers", lambda _repo_root: {"servers": {}})
    monkeypatch.setattr("awf.cli.core_ops.op_llm_serve", lambda _repo_root, _conn, *, action: {"state": "stopped"})
    monkeypatch.setattr(
        "awf.cli.core_ops.op_system_readiness",
        lambda _repo_root: {"profile_id": "linux-x64-cpu", "readiness": {}},
    )
    monkeypatch.setattr(
        "awf.cli.core_ops.op_system_doctor",
        lambda _repo_root: {"status": "ok", "checks": [], "next_actions": []},
    )

    summary = send(repo_root, conn, {"jsonrpc": "2.0", "id": 41, "method": "awf/control.summary", "params": {}})
    detail = send(
        repo_root,
        conn,
        {"jsonrpc": "2.0", "id": 42, "method": "awf/control.runDetail", "params": {"runId": "run-1"}},
    )
    readiness = send(repo_root, conn, {"jsonrpc": "2.0", "id": 43, "method": "awf/system.readiness", "params": {}})
    doctor = send(repo_root, conn, {"jsonrpc": "2.0", "id": 44, "method": "awf/system.doctor", "params": {}})

    assert summary["result"]["runs"][0]["run_id"] == "run-1"
    assert detail["result"]["run"]["run_id"] == "run-1"
    assert readiness["result"]["profile_id"] == "linux-x64-cpu"
    assert doctor["result"]["status"] == "ok"


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

    response = send(
        repo_root, conn, {"jsonrpc": "2.0", "id": 7, "method": "awf/proposal.get", "params": {"proposalId": "p1"}}
    )

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


def test_skill_invoke_over_jsonrpc(tmp_path, monkeypatch):
    repo_root, conn = make_repo(tmp_path)
    skill_dir = repo_root / "config" / "app_registry" / "skills" / "demo-skill" / "1.0.0"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("---\nname: demo-skill\ndescription: Demo.\n---\n\nDo the demo thing.\n")
    profile_dir = repo_root / "config" / "app_registry" / "model-profiles" / "resident-mind"
    profile_dir.mkdir(parents=True)
    (profile_dir / "1.0.0.yaml").write_text(
        "\n".join(
            [
                "name: resident-mind",
                "version: 1.0.0",
                "purpose: general-reasoning",
                "privacy: {maximum_data_class: internal, local_only: true}",
                "candidates:",
                "  - {provider: openai, model: local-model, priority: 1, enabled: true, api_base: 'http://127.0.0.1:8080/v1'}",
                "fallback: {mode: none, allow_quality_degrade: false}",
                "limits: {max_input_tokens_per_call: 8192, max_output_tokens_per_call: 1024, max_cost_usd_per_call: 0.0}",
                "",
            ]
        )
    )
    monkeypatch.setattr("awf.cli.core_ops.complete", lambda *args, **kwargs: "skill response")

    response = send(
        repo_root,
        conn,
        {
            "jsonrpc": "2.0",
            "id": 9,
            "method": "awf/skill.invoke",
            "params": {"ref": "demo-skill@1.0.0", "input": "use it"},
        },
    )

    assert response["result"]["ref"] == "demo-skill@1.0.0"
    assert response["result"]["response_text"] == "skill response"
