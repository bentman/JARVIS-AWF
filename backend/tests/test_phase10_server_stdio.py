import io
import json

import pytest

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

    response = send(repo_root, conn, {"jsonrpc": "2.0", "id": 1, "method": "awf/run.status", "params": {"runId": "run-1"}})

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
        repo_root, conn,
        {"jsonrpc": "2.0", "id": 5, "method": "awf/approval.approve", "params": {"approvalId": "ap-1"}},
    )

    assert response["result"]["status"] == "approved"
