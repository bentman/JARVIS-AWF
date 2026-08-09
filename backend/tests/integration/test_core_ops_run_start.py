import pytest
from backend.tests.support import (
    make_git_awf_repo,
    publish_trivial_gate_workflow,
    publish_workflow,
    single_gate_workflow,
)

from awf.cli.core_ops import CoreOpError, op_run_resume, op_run_start


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
    assert conn.execute("SELECT status FROM runs WHERE run_id = ?", (result["run_id"],)).fetchone()["status"] == "FAILED"


def test_op_run_start_with_bare_name_pins_and_resume_uses_pin(tmp_path):
    repo_root, conn = make_git_awf_repo(tmp_path)
    publish_workflow(repo_root, single_gate_workflow("resume-demo", "1.0.0", "sha256:v1"))

    started = op_run_start(repo_root, conn, workflow_ref="resume-demo", input_data={})
    assert started["status"] == "SUCCEEDED"
    assert conn.execute("SELECT workflow_ref FROM runs WHERE run_id = ?", (started["run_id"],)).fetchone()[
        "workflow_ref"
    ] == "resume-demo@1.0.0"

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
    assert result["outputs"] == {"repairs_used": 0}


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
