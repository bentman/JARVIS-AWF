import json
import shutil
import sys

import pytest
from backend.tests.support import (
    make_git_awf_repo,
    publish_trivial_gate_workflow,
    publish_workflow,
    single_gate_workflow,
)

from awf.ops.run import _check_command_args, op_run_resume, op_run_start
from awf.ops.shared import CoreOpError
from awf.paths import artifacts_dir
from awf.pyexec import repo_python_executable


def test_op_run_start_fails_cleanly_for_an_unknown_activity_name(tmp_path):
    repo_root, conn = make_git_awf_repo(tmp_path)
    publish_workflow(
        repo_root,
        {
            "apiVersion": "awf/v1",
            "kind": "Workflow",
            "metadata": {"name": "bad-activity", "version": "1.0.0", "digest": "sha256:demo"},
            "spec": {
                "inputSchema": {},
                "outputSchema": {},
                "budgets": {},
                "nodes": [{"id": "a", "type": "activity", "function": "not-a-real-activity", "next": None}],
                "outputs": {},
            },
        },
    )

    result = op_run_start(repo_root, conn, workflow_ref="bad-activity@1.0.0", input_data={})

    assert result["status"] == "FAILED"
    assert (
        conn.execute("SELECT status FROM runs WHERE run_id = ?", (result["run_id"],)).fetchone()["status"] == "FAILED"
    )


def test_op_run_start_with_bare_name_pins_and_resume_uses_pin(tmp_path):
    repo_root, conn = make_git_awf_repo(tmp_path)
    publish_workflow(repo_root, single_gate_workflow("resume-demo", "1.0.0", "sha256:v1"))

    started = op_run_start(repo_root, conn, workflow_ref="resume-demo", input_data={})
    assert started["status"] == "SUCCEEDED"
    assert (
        conn.execute("SELECT workflow_ref FROM runs WHERE run_id = ?", (started["run_id"],)).fetchone()["workflow_ref"]
        == "resume-demo@1.0.0"
    )

    publish_workflow(
        repo_root,
        {
            "apiVersion": "awf/v1",
            "kind": "Workflow",
            "metadata": {"name": "resume-demo", "version": "2.0.0", "digest": "sha256:v2"},
            "spec": {
                "inputSchema": {},
                "outputSchema": {},
                "budgets": {},
                "nodes": [{"id": "a", "type": "activity", "function": "not-a-real-activity", "next": None}],
                "outputs": {},
            },
        },
    )
    conn.execute("UPDATE runs SET status = 'RUNNING' WHERE run_id = ?", (started["run_id"],))
    conn.commit()

    assert op_run_resume(repo_root, conn)[0]["status"] == "SUCCEEDED"


def test_op_run_start_validates_inputs_and_outputs(tmp_path):
    repo_root, conn = make_git_awf_repo(tmp_path)
    publish_workflow(
        repo_root,
        {
            "apiVersion": "awf/v1",
            "kind": "Workflow",
            "metadata": {"name": "schema-demo", "version": "1.0.0", "digest": "sha256:demo"},
            "spec": {
                "inputSchema": {"type": "object", "required": ["objective"]},
                "budgets": {},
                "outputSchema": {
                    "type": "object",
                    "properties": {"repairs_used": {"type": "integer"}},
                    "required": ["repairs_used"],
                },
                "nodes": [{"id": "check", "type": "gate", "checkCommand": "true", "next": None}],
                "outputs": {"repairs_used": "{{ engine.repairs_used }}"},
            },
        },
    )

    with pytest.raises(CoreOpError):
        op_run_start(repo_root, conn, workflow_ref="schema-demo@1.0.0", input_data={})

    result = op_run_start(repo_root, conn, workflow_ref="schema-demo@1.0.0", input_data={"objective": "x"})
    assert result["status"] == "SUCCEEDED"
    assert result["outputs"]["repairs_used"] == 0
    assert result["outputs"]["response_text"].startswith(
        "Workflow schema-demo@1.0.0 succeeded (repairs used: 0; verdict:"
    )


def test_op_run_start_preserves_workflow_response_text_output(tmp_path):
    repo_root, conn = make_git_awf_repo(tmp_path)
    publish_workflow(
        repo_root,
        {
            "apiVersion": "awf/v1",
            "kind": "Workflow",
            "metadata": {"name": "response-demo", "version": "1.0.0", "digest": "sha256:demo"},
            "spec": {
                "inputSchema": {},
                "budgets": {},
                "outputSchema": {
                    "type": "object",
                    "properties": {"response_text": {"type": "string"}},
                    "required": ["response_text"],
                },
                "nodes": [{"id": "check", "type": "gate", "checkCommand": "true", "next": None}],
                "outputs": {"response_text": "Custom workflow response."},
            },
        },
    )

    result = op_run_start(repo_root, conn, workflow_ref="response-demo@1.0.0", input_data={})

    assert result["status"] == "SUCCEEDED"
    assert result["outputs"]["response_text"] == "Custom workflow response."


def test_op_run_start_adapts_chat_objective_to_single_string_input(tmp_path):
    repo_root, conn = make_git_awf_repo(tmp_path)
    publish_workflow(
        repo_root,
        {
            "apiVersion": "awf/v1",
            "kind": "Workflow",
            "metadata": {"name": "topic-demo", "version": "1.0.0", "digest": "sha256:demo"},
            "spec": {
                "inputSchema": {
                    "type": "object",
                    "properties": {"topic": {"type": "string"}},
                    "required": ["topic"],
                    "additionalProperties": False,
                },
                "outputSchema": {},
                "budgets": {},
                "nodes": [{"id": "check", "type": "gate", "checkCommand": "true", "next": None}],
                "outputs": {},
            },
        },
    )

    result = op_run_start(
        repo_root,
        conn,
        workflow_ref="topic-demo@1.0.0",
        input_data={"objective": "SQLite WAL", "voiceSessionId": "vs-1", "turnId": "turn-1"},
    )

    assert result["status"] == "SUCCEEDED"
    input_json = conn.execute("SELECT input_json FROM runs WHERE run_id = ?", (result["run_id"],)).fetchone()[
        "input_json"
    ]
    assert json.loads(input_json) == {"topic": "SQLite WAL"}


def test_op_run_start_preserves_allowed_assistant_metadata_when_adapting_objective(tmp_path):
    repo_root, conn = make_git_awf_repo(tmp_path)
    publish_workflow(
        repo_root,
        {
            "apiVersion": "awf/v1",
            "kind": "Workflow",
            "metadata": {"name": "topic-voice-demo", "version": "1.0.0", "digest": "sha256:demo"},
            "spec": {
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "topic": {"type": "string"},
                        "voiceSessionId": {"type": "string"},
                    },
                    "required": ["topic"],
                    "additionalProperties": False,
                },
                "outputSchema": {},
                "budgets": {},
                "nodes": [{"id": "check", "type": "gate", "checkCommand": "true", "next": None}],
                "outputs": {},
            },
        },
    )

    result = op_run_start(
        repo_root,
        conn,
        workflow_ref="topic-voice-demo@1.0.0",
        input_data={"objective": "SQLite WAL", "voiceSessionId": "vs-1", "turnId": "turn-1"},
    )

    assert result["status"] == "SUCCEEDED"
    input_json = conn.execute("SELECT input_json FROM runs WHERE run_id = ?", (result["run_id"],)).fetchone()[
        "input_json"
    ]
    assert json.loads(input_json) == {"topic": "SQLite WAL", "voiceSessionId": "vs-1"}


def test_op_run_start_runs_shipped_default_assistant_workflow(tmp_path, repo_root, monkeypatch):
    test_repo_root, conn = make_git_awf_repo(tmp_path)
    shutil.copytree(
        repo_root / "config" / "app_registry" / "workflows" / "assistant-default",
        test_repo_root / "config" / "app_registry" / "workflows" / "assistant-default",
    )
    shutil.copytree(
        repo_root / "config" / "app_registry" / "capabilities" / "assistant_reply",
        test_repo_root / "config" / "app_registry" / "capabilities" / "assistant_reply",
    )
    shutil.copytree(
        repo_root / "config" / "app_registry" / "model-profiles" / "resident-mind",
        test_repo_root / "config" / "app_registry" / "model-profiles" / "resident-mind",
    )
    monkeypatch.setattr("awf.workflow.activities.complete", lambda *args, **kwargs: "Model says: show failed runs.")

    result = op_run_start(
        test_repo_root,
        conn,
        workflow_ref="assistant-default@1.0.0",
        input_data={"objective": "show failed runs"},
    )

    assert result["status"] == "SUCCEEDED"
    assert result["outputs"]["response_text"] == "Model says: show failed runs."


def test_op_run_start_escalates_risky_gate_to_high_risk_tier(tmp_path):
    repo_root, conn = make_git_awf_repo(tmp_path)
    publish_workflow(
        repo_root,
        {
            "apiVersion": "awf/v1",
            "kind": "Workflow",
            "metadata": {"name": "risky-gate", "version": "1.0.0", "digest": "sha256:demo"},
            "spec": {
                "inputSchema": {},
                "outputSchema": {},
                "budgets": {},
                "nodes": [
                    {
                        "id": "check",
                        "type": "gate",
                        "checkCommand": f'"{sys.executable}" -c pass',
                        "risk_class": "R2",
                        "next": None,
                    }
                ],
                "outputs": {},
            },
        },
    )

    result = op_run_start(repo_root, conn, workflow_ref="risky-gate@1.0.0", input_data={})

    assert result["status"] == "SUCCEEDED"
    verdict_row = conn.execute(
        "SELECT relative_path FROM artifacts WHERE artifact_id = ?", (result["verdict_artifact_id"],)
    ).fetchone()
    verdict = json.loads((artifacts_dir(repo_root) / verdict_row["relative_path"]).read_text())
    assert verdict["tier"] == "high-risk"
    event = conn.execute("SELECT payload_json FROM events WHERE reason_code = 'gate_tier_selected'").fetchone()
    assert event is not None
    assert "check:declared_R2" in event["payload_json"]


def test_repo_python_executable_marks_windows_and_linux_venvs(tmp_path):
    linux_python = tmp_path / "backend" / ".venv" / "bin" / "python"
    linux_python.parent.mkdir(parents=True)
    linux_python.touch()

    assert repo_python_executable(tmp_path) == ("linux-venv", str(linux_python))

    windows_python = tmp_path / "backend" / ".venv" / "Scripts" / "python.exe"
    windows_python.parent.mkdir(parents=True)
    windows_python.touch()

    assert repo_python_executable(tmp_path) == ("windows-venv", str(windows_python))
    assert _check_command_args(tmp_path, 'python3.12 -c "print(1)"') == [str(windows_python), "-c", "print(1)"]
    assert _check_command_args(tmp_path, "backend/.venv/bin/python -m ruff check .") == [
        str(windows_python),
        "-m",
        "ruff",
        "check",
        ".",
    ]


def test_op_run_start_dispatches_composite_child_node_types(tmp_path):
    repo_root, conn = make_git_awf_repo(tmp_path)
    publish_trivial_gate_workflow(repo_root, name="child-ok")
    publish_workflow(
        repo_root,
        {
            "apiVersion": "awf/v1",
            "kind": "Workflow",
            "metadata": {"name": "composite-demo", "version": "1.0.0", "digest": "sha256:demo"},
            "spec": {
                "inputSchema": {},
                "outputSchema": {},
                "budgets": {},
                "nodes": [
                    {
                        "id": "fan-out",
                        "type": "map",
                        "workflowRef": "child-ok@1.0.0",
                        "items": ["a", "b"],
                        "maxItems": 5,
                        "maxConcurrency": 2,
                        "next": "retry",
                    },
                    {
                        "id": "retry",
                        "type": "loop",
                        "workflowRef": "child-ok@1.0.0",
                        "maxIterations": 1,
                        "conditionField": "passed",
                        "next": None,
                    },
                ],
                "outputs": {},
            },
        },
    )

    result = op_run_start(repo_root, conn, workflow_ref="composite-demo@1.0.0", input_data={})

    assert result["status"] == "WAITING_INPUT"
    assert len(conn.execute("SELECT run_id FROM runs WHERE workflow_ref = 'child-ok@1.0.0'").fetchall()) == 3
