"""run operation implementations."""

import json
import sqlite3
from pathlib import Path

from awf.clock import utc_now_rfc3339
from awf.engine.recovery import reset_interrupted_node_steps, scan_incomplete_runs
from awf.engine.run import create_run
from awf.ids import uuid7
from awf.improvement.proposals import get as get_proposal
from awf.isolation.scratch import create_scratch_dir, scratch_path
from awf.isolation.worktree import create_worktree, worktree_path
from awf.ops.run_execution import (
    DEFAULT_ASSISTANT_WORKFLOW_REF,
    _build_node_executors,
    _check_command_args,
    _cleanup_run_workspace,
    _resolve_workflow,
    _retain_worktree_for_improvement,
    _run_workflow_safely,
)
from awf.ops.shared import CoreOpError
from awf.paths import artifacts_dir
from awf.workflow.io_schema import InputValidationError, validate_input


def _default_response_text(workflow_ref: str, result: dict) -> str:
    status = result.get("status", "UNKNOWN")
    if status == "SUCCEEDED":
        details = []
        if "repairs_used" in result:
            details.append(f"repairs used: {result['repairs_used']}")
        if "hops_used" in result:
            details.append(f"hops used: {result['hops_used']}")
        if result.get("verdict_artifact_id"):
            details.append(f"verdict: {result['verdict_artifact_id']}")
        suffix = f" ({'; '.join(details)})" if details else ""
        return f"Workflow {workflow_ref} succeeded{suffix}."
    if result.get("error"):
        return f"Workflow {workflow_ref} failed: {result['error']}"
    if result.get("reason"):
        return f"Workflow {workflow_ref} finished with status {status}: {result['reason']}"
    return f"Workflow {workflow_ref} finished with status {status}."


def _with_response_text(workflow_ref: str, result: dict) -> dict:
    outputs = result.get("outputs")
    if not isinstance(outputs, dict):
        outputs = {}
    if isinstance(outputs.get("response_text"), str):
        return {**result, "outputs": outputs}
    return {**result, "outputs": {**outputs, "response_text": _default_response_text(workflow_ref, result)}}


def _safe_json_loads(value: str | None, default):
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def _response_text_from_run_record(run: dict, workflow_ref: str) -> str:
    output = _safe_json_loads(run.get("output_json"), {})
    if isinstance(output, dict):
        outputs = output.get("outputs")
        if isinstance(outputs, dict) and isinstance(outputs.get("response_text"), str):
            return outputs["response_text"]
        if isinstance(output.get("error"), str):
            return f"Workflow {workflow_ref} failed: {output['error']}"
        if isinstance(output.get("reason"), str):
            return f"Workflow {workflow_ref} finished with status {run.get('status')}: {output['reason']}"
    return _default_response_text(workflow_ref, {"status": run.get("status", "UNKNOWN")})


def _run_outcome_from_parts(
    run: dict,
    steps: list[dict],
    artifacts: list[dict],
    approvals: list[dict],
    conn: sqlite3.Connection | None = None,
) -> dict:
    status = run.get("status", "UNKNOWN")
    workflow_ref = run.get("workflow_ref", "unknown@0.0.0")
    pending_approvals = [approval for approval in approvals if approval.get("status") == "pending"]
    failed_steps = [step for step in steps if step.get("status") == "FAILED"]
    evidence = [
        {
            "artifact_id": artifact.get("artifact_id"),
            "type": artifact.get("artifact_type"),
            "path": artifact.get("relative_path"),
        }
        for artifact in artifacts
        if artifact.get("artifact_type") in {"verdict", "finding", "test-result", "report"}
    ]
    failures = [
        {
            "step_id": step.get("step_id"),
            "node_id": step.get("node_id"),
            "failure_class": step.get("failure_class"),
            "output": _safe_json_loads(step.get("output_json"), {}),
        }
        for step in failed_steps
    ]
    proposal = None
    if conn is not None and run.get("run_id"):
        try:
            prop_row = conn.execute(
                "SELECT improvement_id FROM improvement_proposals WHERE run_id = ?", (run["run_id"],)
            ).fetchone()
            if prop_row is not None:
                proposal = get_proposal(conn, improvement_id=prop_row["improvement_id"])
        except Exception:
            proposal = None

    if proposal is not None:
        cmd = proposal.get("next_action", {}).get("command")
        label = proposal.get("next_action", {}).get("label") or "Review proposal"
        next_action = f"{label}: {cmd}" if cmd else label
    elif pending_approvals:
        next_action = f"Review {len(pending_approvals)} pending approval(s) with `awf review list`."
    elif status == "FAILED":
        next_action = "Inspect the failed step and artifacts, then rerun or prepare a repair."
    elif status in {"WAITING_INPUT", "WAITING_APPROVAL"}:
        next_action = "Resume after supplying the requested operator input or approval."
    elif status == "SUCCEEDED" and evidence:
        next_action = "Review the evidence artifacts if this result will be used for follow-up work."
    elif status == "SUCCEEDED":
        next_action = "No operator action required."
    else:
        next_action = "Check run status again or resume after a restart."
    out = {
        "run_id": run.get("run_id"),
        "workflow_ref": workflow_ref,
        "status": status,
        "response_text": _response_text_from_run_record(run, workflow_ref),
        "evidence": evidence,
        "artifacts": [
            {
                "artifact_id": artifact.get("artifact_id"),
                "type": artifact.get("artifact_type"),
                "path": artifact.get("relative_path"),
                "complete": bool(artifact.get("complete")),
            }
            for artifact in artifacts
        ],
        "failures": failures,
        "pending_approvals": [
            {
                "approval_id": approval.get("approval_id"),
                "risk_class": approval.get("risk_class"),
                "action_digest": approval.get("action_digest"),
            }
            for approval in pending_approvals
        ],
        "created_at": run.get("created_at"),
        "updated_at": run.get("updated_at"),
        "next_action": next_action,
    }
    if proposal is not None:
        out["proposal"] = proposal
    return out


def _adapt_objective_input(input_data: dict, input_schema: dict) -> dict:
    if "objective" not in input_data or not isinstance(input_data.get("objective"), str):
        return input_data
    required = input_schema.get("required")
    properties = input_schema.get("properties", {})
    if not isinstance(required, list) or len(required) != 1:
        return input_data
    target = required[0]
    if target == "objective":
        return input_data
    target_schema = properties.get(target, {})
    target_type = target_schema.get("type") if isinstance(target_schema, dict) else None
    if target_type not in (None, "string"):
        return input_data
    adapted = {target: input_data["objective"]}
    allows_extra = input_schema.get("additionalProperties", True) is not False
    for key, value in input_data.items():
        if key == "objective":
            continue
        if allows_extra or key in properties:
            adapted[key] = value
    return adapted


def op_run_outcome(conn: sqlite3.Connection, *, run_id: str) -> dict:
    run_row = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    if run_row is None:
        raise CoreOpError(f"no such run: {run_id}")
    run = dict(run_row)
    steps = [dict(row) for row in conn.execute("SELECT * FROM steps WHERE run_id = ? ORDER BY started_at", (run_id,))]
    artifacts = [
        dict(row) for row in conn.execute("SELECT * FROM artifacts WHERE run_id = ? ORDER BY created_at", (run_id,))
    ]
    approvals = [
        dict(row) for row in conn.execute("SELECT * FROM approvals WHERE run_id = ? ORDER BY requested_at", (run_id,))
    ]
    return _run_outcome_from_parts(run, steps, artifacts, approvals, conn=conn)


def op_run_start(repo_root: Path, conn: sqlite3.Connection, *, workflow_ref: str, input_data: dict) -> dict:
    workflow = _resolve_workflow(repo_root, workflow_ref, conn=conn)
    input_data = _adapt_objective_input(input_data, workflow.input_schema)
    try:
        validate_input(input_data, workflow.input_schema)
    except InputValidationError as exc:
        raise CoreOpError(f"input does not match {workflow.ref}'s inputSchema: {exc}") from exc

    run_id = uuid7()
    create_run(conn, run_id=run_id, workflow_ref=workflow.ref, input_json=json.dumps(input_data))

    worktree = create_worktree(repo_root, run_id)
    run_scratch_dir = create_scratch_dir(repo_root, run_id)
    node_executors = _build_node_executors(
        workflow, worktree, artifacts_dir(repo_root), repo_root, run_scratch_dir, input_data
    )

    result = _with_response_text(
        workflow.ref,
        _run_workflow_safely(conn, run_id=run_id, workflow=workflow, node_executors=node_executors),
    )
    conn.execute(
        "UPDATE runs SET output_json = ?, updated_at = ? WHERE run_id = ?",
        (json.dumps(result), utc_now_rfc3339(), run_id),
    )
    conn.commit()

    retain_worktree = _retain_worktree_for_improvement(workflow.ref, input_data)
    if result.get("status") == "SUCCEEDED" and retain_worktree:
        try:
            from awf.improvement.proposals import mark_ready as mark_proposal_ready
            from awf.improvement.proposals import prepare as prepare_proposal

            summary_text = input_data.get("objective") or f"Improvement from run {run_id}"
            prop = prepare_proposal(repo_root, conn, run_id=run_id, summary=summary_text)
            verdict_id = result.get("outputs", {}).get("verdict_artifact_id")
            if verdict_id:
                try:
                    mark_proposal_ready(
                        repo_root,
                        conn,
                        improvement_id=prop["improvement_id"],
                        verdict_artifact_id=verdict_id,
                        validation_artifact_ids=[verdict_id],
                    )
                except Exception:
                    pass
        except Exception:
            pass

    _cleanup_run_workspace(
        repo_root,
        run_id,
        result,
        retain_worktree=retain_worktree,
    )
    return {"run_id": run_id, **result, "outcome": op_run_outcome(conn, run_id=run_id)}


def op_run_status(conn: sqlite3.Connection, *, run_id: str) -> dict:
    run_row = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    if run_row is None:
        raise CoreOpError(f"no such run: {run_id}")
    run = dict(run_row)
    steps = [dict(row) for row in conn.execute("SELECT * FROM steps WHERE run_id = ? ORDER BY started_at", (run_id,))]
    artifacts = [
        dict(row) for row in conn.execute("SELECT * FROM artifacts WHERE run_id = ? ORDER BY created_at", (run_id,))
    ]
    approvals = [
        dict(row) for row in conn.execute("SELECT * FROM approvals WHERE run_id = ? ORDER BY requested_at", (run_id,))
    ]
    outcome = _run_outcome_from_parts(run, steps, artifacts, approvals, conn=conn)
    return {**run, "steps": steps, "outcome": outcome}


def op_run_list(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT * FROM runs ORDER BY created_at").fetchall()
    result = []
    for row in rows:
        run = dict(row)
        run_id = run["run_id"]
        steps = [dict(r) for r in conn.execute("SELECT * FROM steps WHERE run_id = ? ORDER BY started_at", (run_id,))]
        artifacts = [
            dict(r) for r in conn.execute("SELECT * FROM artifacts WHERE run_id = ? ORDER BY created_at", (run_id,))
        ]
        approvals = [
            dict(r) for r in conn.execute("SELECT * FROM approvals WHERE run_id = ? ORDER BY requested_at", (run_id,))
        ]
        outcome = _run_outcome_from_parts(run, steps, artifacts, approvals, conn=conn)
        result.append(
            {
                "run_id": run["run_id"],
                "workflow_ref": run["workflow_ref"],
                "status": run["status"],
                "created_at": run["created_at"],
                "updated_at": run["updated_at"],
                "outcome": outcome,
            }
        )
    return result


def op_run_resume(repo_root: Path, conn: sqlite3.Connection) -> list[dict]:
    results = []
    for run_id in scan_incomplete_runs(conn):
        reset_interrupted_node_steps(conn, run_id)
        run_row = conn.execute("SELECT workflow_ref, input_json FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        try:
            input_data = json.loads(run_row["input_json"]) if run_row is not None and run_row["input_json"] else {}
        except json.JSONDecodeError:
            input_data = {}
        workflow = _resolve_workflow(repo_root, run_row["workflow_ref"], conn=conn)
        worktree = worktree_path(repo_root, run_id)
        run_scratch_dir = scratch_path(repo_root, run_id)
        node_executors = _build_node_executors(
            workflow, worktree, artifacts_dir(repo_root), repo_root, run_scratch_dir, input_data
        )
        result = _with_response_text(
            workflow.ref,
            _run_workflow_safely(conn, run_id=run_id, workflow=workflow, node_executors=node_executors),
        )
        conn.execute(
            "UPDATE runs SET output_json = ?, updated_at = ? WHERE run_id = ?",
            (json.dumps(result), utc_now_rfc3339(), run_id),
        )
        conn.commit()
        _cleanup_run_workspace(
            repo_root,
            run_id,
            result,
            retain_worktree=_retain_worktree_for_improvement(run_row["workflow_ref"], input_data),
        )
        results.append({"run_id": run_id, **result, "outcome": op_run_outcome(conn, run_id=run_id)})
    return results


__all__ = (
    "DEFAULT_ASSISTANT_WORKFLOW_REF",
    "_check_command_args",
    "_cleanup_run_workspace",
    "op_run_list",
    "op_run_outcome",
    "op_run_resume",
    "op_run_start",
    "op_run_status",
)
