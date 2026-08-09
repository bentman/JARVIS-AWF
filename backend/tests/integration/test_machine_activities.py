import json
import sys
from email.message import Message

import pytest

from awf.cli.core_ops import op_approval_approve, op_approval_detail
from awf.db.bootstrap import init_db
from awf.db.connection import get_connection
from awf.engine.run import create_run, create_step
from awf.machine.activities import MachineActivityError, run_machine_activity
from awf.registry.capability_record import CapabilityRecord, Effects, Identity


@pytest.fixture
def conn(tmp_path):
    db_path = tmp_path / "awf.db"
    init_db(db_path)
    connection = get_connection(db_path)
    create_run(connection, run_id="run-1", workflow_ref="machine@1.0.0")
    return connection


@pytest.fixture
def machine_root(tmp_path):
    repo_root = tmp_path / "repo"
    worktree = tmp_path / "worktree"
    repo_root.mkdir()
    worktree.mkdir()
    return repo_root, worktree


def _capability(name: str, operation: str, risk_class: str, approval: str, constraints: dict) -> CapabilityRecord:
    return CapabilityRecord(
        identity=Identity(type="activity", provider="awf", name=name, version="1.0.0"),
        schema_input="",
        schema_output="",
        effects=Effects(operation=operation, reversible=True, idempotent=False, external_side_effect=False),
        risk_class=risk_class,
        approval=approval,
        constraints=constraints,
    )


def test_fs_read_and_write_are_bounded_to_the_run_worktree(conn, machine_root):
    repo_root, worktree = machine_root
    create_step(conn, step_id="step-write", run_id="run-1", node_id="write")
    write_capability = _capability(
        "fs_write",
        "update",
        "R1",
        "never",
        {"filesystem": {"allowedRoots": ["worktree"], "allowedGlobs": ["notes/**"]}},
    )

    output = run_machine_activity(
        conn,
        repo_root=repo_root,
        worktree_path=worktree,
        run_id="run-1",
        step_id="step-write",
        node={"id": "write", "function": "fs_write", "args": {"path": "notes/a.txt", "content": "hello\n"}},
        capability=write_capability,
    )

    assert (worktree / "notes" / "a.txt").read_text() == "hello\n"
    assert output["path"] == str(worktree / "notes" / "a.txt")

    create_step(conn, step_id="step-read", run_id="run-1", node_id="read")
    read_capability = _capability(
        "fs_read",
        "read",
        "R0",
        "never",
        {"filesystem": {"allowedRoots": ["worktree"], "allowedGlobs": ["notes/**"], "maxBytes": 1024}},
    )
    read_output = run_machine_activity(
        conn,
        repo_root=repo_root,
        worktree_path=worktree,
        run_id="run-1",
        step_id="step-read",
        node={"id": "read", "function": "fs_read", "args": {"path": "notes/a.txt"}},
        capability=read_capability,
    )

    assert read_output["content"] == "hello\n"
    event = conn.execute(
        "SELECT payload_json FROM events WHERE reason_code = 'machine_action_executed' AND step_id = 'step-read'"
    ).fetchone()
    assert "fs_read" in event["payload_json"]


def test_fs_delete_moves_to_worktree_trash(conn, machine_root):
    repo_root, worktree = machine_root
    target = worktree / "notes" / "delete-me.txt"
    target.parent.mkdir()
    target.write_text("remove\n")
    create_step(conn, step_id="step-delete", run_id="run-1", node_id="delete")
    capability = _capability(
        "fs_delete",
        "delete",
        "R1",
        "never",
        {"filesystem": {"allowedRoots": ["worktree"], "allowedGlobs": ["notes/**"]}},
    )

    output = run_machine_activity(
        conn,
        repo_root=repo_root,
        worktree_path=worktree,
        run_id="run-1",
        step_id="step-delete",
        node={"id": "delete", "function": "fs_delete", "args": {"path": "notes/delete-me.txt"}},
        capability=capability,
    )

    assert not target.exists()
    assert output["reversible"] is True
    assert output["trash_path"].startswith(str(worktree / ".awf-trash"))


def test_fs_write_rejects_content_over_policy_max_bytes(conn, machine_root):
    repo_root, worktree = machine_root
    create_step(conn, step_id="step-write-too-large", run_id="run-1", node_id="write-too-large")
    capability = _capability(
        "fs_write",
        "update",
        "R1",
        "never",
        {"filesystem": {"allowedRoots": ["worktree"], "allowedGlobs": ["notes/**"], "maxBytes": 4}},
    )

    with pytest.raises(MachineActivityError, match="content exceeds maxBytes"):
        run_machine_activity(
            conn,
            repo_root=repo_root,
            worktree_path=worktree,
            run_id="run-1",
            step_id="step-write-too-large",
            node={"id": "write", "function": "fs_write", "args": {"path": "notes/a.txt", "content": "hello"}},
            capability=capability,
        )

    assert not (worktree / "notes" / "a.txt").exists()
    row = conn.execute("SELECT status, failure_class FROM steps WHERE step_id = 'step-write-too-large'").fetchone()
    assert dict(row) == {"status": "FAILED", "failure_class": "POLICY_DENIED"}


def test_command_run_executes_approved_absolute_command_and_captures_output(conn, machine_root):
    repo_root, worktree = machine_root
    create_step(conn, step_id="step-command", run_id="run-1", node_id="command")
    capability = _capability(
        "command_run",
        "execute",
        "R1",
        "never",
        {
            "command": {
                "executable": sys.executable,
                "allowedArgs": [["-c", "*"]],
                "cwdRoot": "worktree",
                "timeoutSeconds": 5,
                "maxOutputBytes": 1024,
            }
        },
    )

    output = run_machine_activity(
        conn,
        repo_root=repo_root,
        worktree_path=worktree,
        run_id="run-1",
        step_id="step-command",
        node={
            "id": "command",
            "function": "command_run",
            "args": {"argv": [sys.executable, "-c", "print('ok')"]},
        },
        capability=capability,
    )

    assert output == {"returncode": 0, "stdout": "ok\n", "stderr": ""}


def test_network_fetch_validates_policy_and_can_retain_body_artifact(conn, machine_root, monkeypatch):
    repo_root, worktree = machine_root
    create_step(conn, step_id="step-network", run_id="run-1", node_id="network")

    class FakeResponse:
        status = 200
        headers = Message()

        def __init__(self):
            self.headers["content-type"] = "text/plain"

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def geturl(self):
            return "https://example.com/doc"

        def read(self, _limit):
            return b"network-ok"

    class FakeOpener:
        def open(self, request, timeout):
            assert request.full_url == "https://example.com/doc"
            assert timeout == 5
            return FakeResponse()

    monkeypatch.setattr("awf.machine.activities.build_opener", lambda *_handlers: FakeOpener())
    capability = _capability(
        "network_fetch",
        "communicate",
        "R1",
        "never",
        {
            "network": {
                "allowedHosts": ["example.com"],
                "allowedMethods": ["GET"],
                "timeoutSeconds": 5,
                "maxResponseBytes": 1024,
                "retainBodyAsArtifact": True,
            }
        },
    )

    output = run_machine_activity(
        conn,
        repo_root=repo_root,
        worktree_path=worktree,
        run_id="run-1",
        step_id="step-network",
        node={"id": "network", "function": "network_fetch", "args": {"url": "https://example.com/doc"}},
        capability=capability,
    )

    assert output["status"] == 200
    assert output["body_digest"].startswith("sha256:")
    artifact = conn.execute(
        "SELECT artifact_type, media_type FROM artifacts WHERE artifact_id = ?", (output["artifact_id"],)
    ).fetchone()
    assert dict(artifact) == {"artifact_type": "report", "media_type": "text/plain"}


def test_per_invocation_machine_action_creates_preview_and_waits_for_approval(conn, machine_root):
    repo_root, worktree = machine_root
    create_step(conn, step_id="step-approval", run_id="run-1", node_id="write")
    capability = _capability(
        "fs_write",
        "update",
        "R1",
        "per-invocation",
        {"filesystem": {"allowedRoots": ["worktree"]}},
    )
    node = {"id": "write", "function": "fs_write", "args": {"path": "approved.txt", "content": "approved\n"}}

    first = run_machine_activity(
        conn,
        repo_root=repo_root,
        worktree_path=worktree,
        run_id="run-1",
        step_id="step-approval",
        node=node,
        capability=capability,
    )

    assert first["waiting_input"] is True
    approval_id = first["approval_id"]
    detail = op_approval_detail(conn, approval_id=approval_id)
    assert detail["preview"]["machine_action"]["target"]["path"] == str(worktree / "approved.txt")

    op_approval_approve(conn, approval_id=approval_id)
    second = run_machine_activity(
        conn,
        repo_root=repo_root,
        worktree_path=worktree,
        run_id="run-1",
        step_id="step-approval",
        node=node,
        capability=capability,
    )

    assert second["sha256"].startswith("sha256:")
    assert (worktree / "approved.txt").read_text() == "approved\n"
    row = conn.execute("SELECT status, output_json FROM steps WHERE step_id = 'step-approval'").fetchone()
    assert row["status"] == "SUCCEEDED"
    assert json.loads(row["output_json"])["path"] == str(worktree / "approved.txt")
