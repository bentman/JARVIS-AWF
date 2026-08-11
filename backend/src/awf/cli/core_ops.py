"""Core operations shared by the `awf` CLI (Section 16.1) and the
`awf serve --stdio` JSON-RPC endpoint (Section 16.3).

The protocol adds no authority (Section 16.3): both surfaces call exactly
these functions, so a mutation made over JSON-RPC passes through the same
Capability Guard / durability / worktree-commit paths as the CLI.
"""

import hashlib
import json
import os
import shlex
import shutil
import sqlite3
import subprocess
import sys
from dataclasses import asdict, is_dataclass
from pathlib import Path

import yaml

from awf.adapters.antigravity_cli import invoke as antigravity_invoke
from awf.adapters.claude_code import invoke as claude_code_invoke
from awf.adapters.cline_cli import invoke as cline_invoke
from awf.adapters.codex_cli import invoke as codex_invoke
from awf.adapters.copilot_cli import invoke as copilot_invoke
from awf.authoring import workflow as workflow_authoring
from awf.clock import utc_now_rfc3339
from awf.engine.recovery import scan_incomplete_runs
from awf.engine.run import create_run
from awf.envfile import get_env_value
from awf.gates.gate_node import make_trifecta_gate_executor
from awf.ids import uuid7
from awf.improvement import proposals as improvement_proposals
from awf.isolation.scratch import create_scratch_dir, remove_scratch_dir, scratch_path
from awf.isolation.worktree import create_worktree, remove_worktree, worktree_path
from awf.paths import artifacts_dir, env_path
from awf.paths import db_path as resolve_db_path
from awf.registry import index as registry_index
from awf.registry.agent_manifest import load_agent_manifest
from awf.registry.capability_record import load_capability_record, parse_capability_record
from awf.registry.index import latest_version
from awf.registry.kinds import (
    AGENTS,
    CAPABILITIES,
    KINDS,
    MCP,
    MEMORY_PROFILES,
    MODEL_PROFILES,
    PERSONAS,
    SEMANTIC_MEMORIES,
    SKILLS,
    VOICE_PROFILES,
    WORKFLOWS,
    UnknownRegistryKindError,
    version_names,
)
from awf.registry.kinds import by_key as kind_by_key
from awf.registry.kinds import object_path as kind_object_path
from awf.registry.mcp_server import load_mcp_server, parse_mcp_server
from awf.registry.memory_profile import load_memory_profile, parse_memory_profile
from awf.registry.model_profile import load_model_profile, parse_model_profile
from awf.registry.persona import load_persona, parse_persona
from awf.registry.resolve import CONFIG_ROOT, DATA_ROOT, resolve_registry_object
from awf.registry.semantic_memory import load_semantic_memory, parse_semantic_memory
from awf.registry.skill import directory_digest, load_skill
from awf.registry.voice_profile import load_voice_profile, parse_voice_profile
from awf.secrets.store import list_secret_names, set_secret
from awf.workflow.approval import make_approval_node_executor
from awf.workflow.definition import load_workflow, parse_workflow
from awf.workflow.engine import make_activity_node_executor, make_agent_node_executor, run_workflow_definition
from awf.workflow.handoff import make_handoff_node_executor
from awf.workflow.io_schema import InputValidationError, validate_input
from awf.workflow.loop_node import make_loop_node_executor
from awf.workflow.map_node import make_map_node_executor
from awf.workflow.subworkflow import make_subworkflow_node_executor

ADAPTER_REGISTRY = {
    "claude-code": claude_code_invoke,
    "codex": codex_invoke,
    "antigravity": antigravity_invoke,
    "copilot": copilot_invoke,
    "cline": cline_invoke,
}


class CoreOpError(RuntimeError):
    pass


def _cpu_fallback_profile_id(profile_id: str) -> str:
    os_name, arch, _suffix = profile_id.rsplit("-", 2)
    return f"{os_name}-{arch}-cpu"


def _artifact_binary_present(repo_root: Path, profile_id: str, artifact) -> bool:
    from awf.llm.discovery import binary_path

    path = binary_path(repo_root, profile_id, artifact)
    return path.is_file() and path.stat().st_size > 0


def _select_managed_llm_artifact(repo_root: Path, server, profile_id: str, *, allow_cpu_fallback: bool = True):
    from awf.llm.servers import artifact_for

    artifact = artifact_for(server, profile_id)
    if artifact is not None and _artifact_binary_present(repo_root, profile_id, artifact):
        return profile_id, artifact

    if allow_cpu_fallback:
        cpu_profile_id = _cpu_fallback_profile_id(profile_id)
        cpu_artifact = artifact_for(server, cpu_profile_id)
        if cpu_artifact is not None and _artifact_binary_present(repo_root, cpu_profile_id, cpu_artifact):
            return cpu_profile_id, cpu_artifact

    return profile_id, artifact


def _repo_python_executable(repo_root: Path) -> tuple[str, str] | None:
    candidates = [
        ("windows-venv", repo_root / "backend" / ".venv" / "Scripts" / "python.exe"),
        ("linux-venv", repo_root / "backend" / ".venv" / "bin" / "python"),
    ]
    for marker, candidate in candidates:
        if candidate.is_file():
            return marker, str(candidate)
    return None


def _is_python_command(command_name: str) -> bool:
    normalized = command_name.replace("\\", "/").lower()
    return normalized in {
        "python",
        "python.exe",
        "py",
        "python3",
        "python3.12",
        "python3.13",
        "python3.14",
        "backend/.venv/bin/python",
        "backend/.venv/scripts/python.exe",
    }


def _check_command_args(repo_root: Path, command: str) -> list[str] | None:
    stripped = command.strip().lower()
    if stripped == "true":
        return None
    if stripped == "false":
        return ["__awf_false__"]
    args = shlex.split(command)
    if args and _is_python_command(args[0]):
        selected = _repo_python_executable(repo_root)
        if selected is not None:
            _marker, venv_python = selected
            args[0] = venv_python
    return args


def _make_check_fn(node: dict, worktree: Path, repo_root: Path):
    command = node.get("checkCommand")
    if not command:
        raise CoreOpError(f"gate node '{node['id']}' has no checkCommand")

    def check_fn() -> bool:
        args = _check_command_args(repo_root, command)
        if args is None:
            return True
        if args == ["__awf_false__"]:
            return False
        result = subprocess.run(args, cwd=worktree, capture_output=True, text=True)
        return result.returncode == 0

    return check_fn


def _risk_from_node_field(node: dict) -> str | None:
    risk = node.get("risk_class") or node.get("riskClass")
    return risk if risk in {"R2", "R3"} else None


def _capability_for_node(repo_root: Path, node: dict):
    declared = node.get("capability")
    if declared:
        try:
            path, _source = resolve_registry_object(repo_root, "capabilities", declared["name"], declared["version"])
            return load_capability_record(path)
        except Exception:
            return None
    if node.get("type") == "activity" and node.get("function"):
        try:
            path, _source = resolve_registry_object(repo_root, "capabilities", node["function"], "1.0.0")
            return load_capability_record(path)
        except Exception:
            return None
    return None


def _high_risk_reason_for_node(repo_root: Path, node: dict) -> str | None:
    if node.get("guardBypassed"):
        return f"{node['id']}:guard_bypassed"
    risk = _risk_from_node_field(node)
    if risk:
        return f"{node['id']}:declared_{risk}"
    capability = _capability_for_node(repo_root, node)
    if capability is None:
        return None
    if capability.risk_class in {"R2", "R3"}:
        return f"{node['id']}:{capability.ref}:{capability.risk_class}"
    if capability.approval == "per-invocation":
        return f"{node['id']}:{capability.ref}:approval_per_invocation"
    return None


def _effective_gate_tier(repo_root: Path, workflow, gate_node: dict) -> tuple[str, str | None]:
    explicit_tier = gate_node.get("tier")
    if explicit_tier == "high-risk":
        return "high-risk", f"{gate_node['id']}:explicit_high_risk"
    gate_reason = _high_risk_reason_for_node(repo_root, gate_node)
    if gate_reason:
        return "high-risk", gate_reason
    for node in workflow.nodes:
        if node["id"] == gate_node["id"]:
            break
        reason = _high_risk_reason_for_node(repo_root, node)
        if reason:
            return "high-risk", reason
    return explicit_tier or "default", None


def _resolve_named_review_profile(node: dict, repo_root: Path, field_name: str):
    review_ref = node.get(field_name)
    if not review_ref:
        return None, None
    name, _, version = review_ref.partition("@")
    path, _source = resolve_registry_object(repo_root, "model-profiles", name, version)
    profile = load_model_profile(path)
    try:
        secret_key = get_env_value(env_path(repo_root), "AWF_SECRET_KEY").encode("ascii")
    except (FileNotFoundError, KeyError):
        secret_key = None
    return profile, secret_key


def _resolve_review_profile(node: dict, repo_root: Path):
    # A gate node MAY declare `reviewProfile: name@version` (a `purpose:
    # judge` Model Profile, Section 11) to add a real LLM-driven review
    # Finding, routed through the Model Gateway, alongside the deterministic
    # check - the Verifier's other, previously-unbuilt obligation half.
    return _resolve_named_review_profile(node, repo_root, "reviewProfile")


def _resolve_adversary_review_profile(node: dict, repo_root: Path):
    # A gate node MAY declare `adversaryReviewProfile: name@version` (a
    # `purpose: adversary` Model Profile, Section 11) for the high-risk
    # tier's LLM-driven adversary Finding - `reviewProfile`'s counterpart
    # for the Adversary role instead of the Verifier's.
    return _resolve_named_review_profile(node, repo_root, "adversaryReviewProfile")


def _make_run_child(worktree: Path, artifacts_root: Path, repo_root: Path):
    # A child workflow shares the parent's worktree (it's still the same
    # Run's dedicated workspace) but gets its own scratch dir and its own
    # real `runs` row, executed to completion through the same durable
    # engine as any top-level Run before this node's Step is considered
    # done. Used by `subworkflow`, `map`, and `loop`.
    def run_child(conn: sqlite3.Connection, workflow_ref: str, input_data: dict) -> tuple[str, dict]:
        import json

        child_workflow = _resolve_workflow(repo_root, workflow_ref)
        child_run_id = uuid7()
        create_run(conn, run_id=child_run_id, workflow_ref=child_workflow.ref, input_json=json.dumps(input_data))
        child_scratch_dir = create_scratch_dir(repo_root, child_run_id)

        try:
            child_executors = _build_node_executors(
                child_workflow, worktree, artifacts_root, repo_root, child_scratch_dir, input_data
            )
            result = _run_workflow_safely(
                conn, run_id=child_run_id, workflow=child_workflow, node_executors=child_executors
            )
        except Exception as exc:
            conn.execute(
                "UPDATE runs SET status = 'FAILED', updated_at = ? WHERE run_id = ?",
                (utc_now_rfc3339(), child_run_id),
            )
            conn.commit()
            result = {"status": "FAILED", "error": str(exc)}

        remove_scratch_dir(repo_root, child_run_id)
        return child_run_id, result

    return run_child


def _make_run_map_item(artifacts_root: Path, repo_root: Path):
    # Unlike `_make_run_child` (shared worktree, single connection - fine
    # for `subworkflow`/`loop`, which never run concurrently with anything
    # else), a `map` item may run concurrently with its siblings: it gets
    # its own isolated worktree (branched from the parent's current HEAD)
    # and its own `sqlite3.Connection`, since neither is safe to share
    # across threads. `map_node.py` merges each successful item's commits
    # back into the parent worktree itself, in order, once every item has
    # finished - this function only runs one item to completion.
    def run_map_item(parent_head: str, index: int, workflow_ref: str, item) -> tuple[str, Path, dict]:
        import json

        from awf.db.connection import get_connection

        db_path = resolve_db_path(repo_root)
        item_conn = get_connection(db_path)
        try:
            child_workflow = _resolve_workflow(repo_root, workflow_ref)
            child_run_id = uuid7()
            create_run(
                item_conn,
                run_id=child_run_id,
                workflow_ref=child_workflow.ref,
                input_json=json.dumps({"item": item, "index": index}),
            )
            item_worktree = create_worktree(repo_root, child_run_id, base_ref=parent_head)
            item_scratch_dir = create_scratch_dir(repo_root, child_run_id)
            try:
                item_executors = _build_node_executors(
                    child_workflow,
                    item_worktree,
                    artifacts_root,
                    repo_root,
                    item_scratch_dir,
                    {"item": item, "index": index},
                )
                result = _run_workflow_safely(
                    item_conn, run_id=child_run_id, workflow=child_workflow, node_executors=item_executors
                )
            except Exception as exc:
                item_conn.execute(
                    "UPDATE runs SET status = 'FAILED', updated_at = ? WHERE run_id = ?",
                    (utc_now_rfc3339(), child_run_id),
                )
                item_conn.commit()
                result = {"status": "FAILED", "error": str(exc)}
            remove_scratch_dir(repo_root, child_run_id)
            return child_run_id, item_worktree, result
        finally:
            item_conn.close()

    return run_map_item


def _build_node_executors(
    workflow,
    worktree: Path,
    artifacts_root: Path,
    repo_root: Path,
    run_scratch_dir: Path,
    workflow_input: dict | None = None,
) -> dict:
    run_child = _make_run_child(worktree, artifacts_root, repo_root)
    run_map_item = _make_run_map_item(artifacts_root, repo_root)
    executors = {
        "agent": make_agent_node_executor(ADAPTER_REGISTRY, worktree, repo_root, workflow_input),
        "activity": make_activity_node_executor(repo_root=repo_root, worktree_path=worktree, workflow_input=workflow_input),
        "approval": make_approval_node_executor(),
        "subworkflow": make_subworkflow_node_executor(run_child),
        "map": make_map_node_executor(run_map_item, worktree_path=worktree, repo_root=repo_root),
        "loop": make_loop_node_executor(run_child),
    }
    for node in workflow.nodes:
        if node["type"] == "gate":
            tier, tier_reason = _effective_gate_tier(repo_root, workflow, node)
            review_profile, review_secret_key = _resolve_review_profile(node, repo_root)
            adversary_review_profile, adversary_review_secret_key = _resolve_adversary_review_profile(node, repo_root)
            executors["gate"] = make_trifecta_gate_executor(
                check_fn=_make_check_fn(node, worktree, repo_root),
                check_summary=node.get("check", node["id"]),
                artifacts_root=artifacts_root,
                tier=tier,
                cache_sandbox_dir=run_scratch_dir,
                guard_bypassed=node.get("guardBypassed", False),
                review_profile=review_profile,
                review_secret_key=review_secret_key,
                adversary_review_profile=adversary_review_profile,
                adversary_review_secret_key=adversary_review_secret_key,
                worktree_path=worktree,
                tier_reason=tier_reason,
            )
        elif node["type"] == "handoff":
            executors["handoff"] = make_handoff_node_executor(ADAPTER_REGISTRY, worktree)
    return executors


def _resolve_workflow(repo_root: Path, workflow_ref: str, conn: sqlite3.Connection | None = None):
    name, _, version = workflow_ref.partition("@")
    if not version:
        version = latest_version(repo_root, "workflows", name)
    path, _source = resolve_registry_object(repo_root, "workflows", name, version, conn=conn)
    return load_workflow(path)


def _retain_worktree_for_improvement(workflow_ref: str, input_data: dict) -> bool:
    return workflow_ref.startswith("self-improvement@") or input_data.get("retainWorktreeForImprovement") is True


def _cleanup_run_workspace(repo_root: Path, run_id: str, result: dict, *, retain_worktree: bool = False) -> None:
    # Cache state is ephemeral by design (Section 7/10.4) - reclaim it once
    # a Run reaches a terminal state. FAILED keeps its worktree/scratch dir
    # around for post-mortem inspection; only SUCCEEDED is cleaned up here.
    if result.get("status") == "SUCCEEDED" and not retain_worktree:
        remove_worktree(repo_root, run_id)
        remove_scratch_dir(repo_root, run_id)


def _run_workflow_safely(conn: sqlite3.Connection, *, run_id: str, workflow, node_executors: dict) -> dict:
    # A structural error (an unbuilt node type, a workflow YAML missing a
    # required field like `onFail`) can be raised before any Step exists to
    # record it - the Run itself still MUST NOT be left RUNNING forever, so
    # this is the outermost boundary: no exception reaches the caller.
    try:
        return run_workflow_definition(conn, run_id=run_id, workflow=workflow, node_executors=node_executors)
    except Exception as exc:
        conn.execute(
            "UPDATE runs SET status = 'FAILED', updated_at = ? WHERE run_id = ?",
            (utc_now_rfc3339(), run_id),
        )
        conn.commit()
        return {"status": "FAILED", "error": str(exc)}


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


def _run_outcome_from_parts(run: dict, steps: list[dict], artifacts: list[dict], approvals: list[dict]) -> dict:
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
    if pending_approvals:
        next_action = f"Review {len(pending_approvals)} pending approval(s) with `awf approvals`."
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
    return {
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


def op_run_outcome(conn: sqlite3.Connection, *, run_id: str) -> dict:
    run_row = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    if run_row is None:
        raise CoreOpError(f"no such run: {run_id}")
    run = dict(run_row)
    steps = [dict(row) for row in conn.execute("SELECT * FROM steps WHERE run_id = ? ORDER BY started_at", (run_id,))]
    artifacts = [dict(row) for row in conn.execute("SELECT * FROM artifacts WHERE run_id = ? ORDER BY created_at", (run_id,))]
    approvals = [dict(row) for row in conn.execute("SELECT * FROM approvals WHERE run_id = ? ORDER BY requested_at", (run_id,))]
    return _run_outcome_from_parts(run, steps, artifacts, approvals)


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


def op_run_start(repo_root: Path, conn: sqlite3.Connection, *, workflow_ref: str, input_data: dict) -> dict:
    import json

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
    _cleanup_run_workspace(
        repo_root,
        run_id,
        result,
        retain_worktree=_retain_worktree_for_improvement(workflow.ref, input_data),
    )
    return {"run_id": run_id, **result, "outcome": op_run_outcome(conn, run_id=run_id)}


def op_run_status(conn: sqlite3.Connection, *, run_id: str) -> dict:
    run_row = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    if run_row is None:
        raise CoreOpError(f"no such run: {run_id}")
    steps = conn.execute("SELECT * FROM steps WHERE run_id = ? ORDER BY started_at", (run_id,)).fetchall()
    return {**dict(run_row), "steps": [dict(row) for row in steps], "outcome": op_run_outcome(conn, run_id=run_id)}


def op_run_list(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT run_id, workflow_ref, status, created_at, updated_at FROM runs ORDER BY created_at"
    ).fetchall()
    return [{**dict(row), "outcome": op_run_outcome(conn, run_id=row["run_id"])} for row in rows]


def op_run_resume(repo_root: Path, conn: sqlite3.Connection) -> list[dict]:
    results = []
    for run_id in scan_incomplete_runs(conn):
        run_row = conn.execute("SELECT workflow_ref FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        input_row = conn.execute("SELECT input_json FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        try:
            input_data = json.loads(input_row["input_json"]) if input_row is not None else {}
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


def op_approval_list(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT * FROM approvals WHERE status = 'pending' ORDER BY requested_at").fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["preview"] = _machine_action_preview_for_step(conn, step_id=row["step_id"])
        result.append(item)
    return result


def _machine_action_preview_for_step(conn: sqlite3.Connection, *, step_id: str) -> dict | None:
    import json

    rows = conn.execute(
        "SELECT payload_json FROM events "
        "WHERE step_id = ? AND reason_code IN ("
        "'machine_action_waiting_approval', 'machine_action_allowed', 'machine_action_denied', "
        "'machine_action_executed'"
        ") ORDER BY occurred_at DESC",
        (step_id,),
    ).fetchall()
    for row in rows:
        try:
            payload = json.loads(row["payload_json"] or "{}")
        except json.JSONDecodeError:
            continue
        action = payload.get("machine_action")
        if action:
            return {"machine_action": action, "machine_action_digest": payload.get("machine_action_digest")}
    return None


def op_approval_detail(conn: sqlite3.Connection, *, approval_id: str) -> dict:
    row = conn.execute("SELECT * FROM approvals WHERE approval_id = ?", (approval_id,)).fetchone()
    if row is None:
        raise CoreOpError(f"no such approval: {approval_id}")
    preview = _machine_action_preview_for_step(conn, step_id=row["step_id"])
    return {"approval": dict(row), "preview": preview}


def op_machine_action_preview(conn: sqlite3.Connection, *, approval_id: str) -> dict:
    detail = op_approval_detail(conn, approval_id=approval_id)
    if detail["preview"] is None:
        raise CoreOpError(f"approval {approval_id} has no machine action preview")
    return detail["preview"]


def _decide_approval(conn: sqlite3.Connection, *, approval_id: str, status: str, reason: str | None) -> dict:
    row = conn.execute("SELECT * FROM approvals WHERE approval_id = ?", (approval_id,)).fetchone()
    if row is None:
        raise CoreOpError(f"no such approval: {approval_id}")
    if row["status"] != "pending":
        raise CoreOpError(f"approval {approval_id} is not pending (status={row['status']})")
    conn.execute(
        "UPDATE approvals SET status = ?, reason = ?, decided_at = ? WHERE approval_id = ?",
        (status, reason, utc_now_rfc3339(), approval_id),
    )
    conn.commit()
    return {"approval_id": approval_id, "status": status, "reason": reason}


def op_approval_approve(
    conn: sqlite3.Connection, *, approval_id: str, channel: str = "manual", risk_class: str | None = None
) -> dict:
    # `channel="manual"` (CLI/TUI click-equivalent, the existing default) is
    # unrestricted. `channel="voice"` (Section 16.4) MUST NOT grant an R2+
    # approval from voice alone - enforced here, in the core, not only by
    # the GUI's own TypeScript copy of this same rule, so no frontend can
    # bypass it by skipping its own check.
    if channel == "voice":
        row = conn.execute("SELECT risk_class FROM approvals WHERE approval_id = ?", (approval_id,)).fetchone()
        if row is None:
            raise CoreOpError(f"no such approval: {approval_id}")
        stored_risk_class = row["risk_class"]
        if risk_class is not None and stored_risk_class is not None and risk_class != stored_risk_class:
            raise CoreOpError(
                f"risk_class={risk_class!r} does not match this approval's real risk_class={stored_risk_class!r} "
                "- a caller may not claim a different risk class than the one recorded when this approval was requested"
            )
        # An approval whose node never declared `riskClass` has no value to
        # check against - the safe default is R2 (never auto-grantable
        # from voice alone), not R0/R1, since trusting an absent value as
        # low-risk would bypass the rule below.
        effective_risk_class = risk_class or stored_risk_class or "R2"
        from awf.gates.voice_approval import attempt_voice_approval

        decision = attempt_voice_approval(
            conn, approval_id=approval_id, risk_class=effective_risk_class, voice_confirmed=True
        )
        if not decision["decided"]:
            return {
                "approval_id": approval_id,
                "status": "pending",
                "requires_on_screen_confirmation": True,
            }
        return decision
    return _decide_approval(conn, approval_id=approval_id, status="approved", reason=None)


def op_approval_reject(conn: sqlite3.Connection, *, approval_id: str, reason: str) -> dict:
    return _decide_approval(conn, approval_id=approval_id, status="rejected", reason=reason)


def op_artifact_list(conn: sqlite3.Connection, *, run_id: str) -> list[dict]:
    rows = conn.execute("SELECT * FROM artifacts WHERE run_id = ? ORDER BY created_at", (run_id,)).fetchall()
    return [dict(row) for row in rows]


def op_artifact_read(conn: sqlite3.Connection, *, artifact_id: str, artifacts_root: Path) -> dict:
    row = conn.execute("SELECT * FROM artifacts WHERE artifact_id = ?", (artifact_id,)).fetchone()
    if row is None:
        raise CoreOpError(f"no such artifact: {artifact_id}")
    content = (artifacts_root / row["relative_path"]).read_text()
    return {**dict(row), "content": content}


def op_improvement_prepare(
    repo_root: Path, conn: sqlite3.Connection, *, run_id: str, summary: str | None = None
) -> dict:
    try:
        return improvement_proposals.prepare(repo_root, conn, run_id=run_id, summary=summary)
    except improvement_proposals.ImprovementProposalError as exc:
        raise CoreOpError(str(exc)) from exc


def op_improvement_get(conn: sqlite3.Connection, *, improvement_id: str) -> dict:
    try:
        return improvement_proposals.get(conn, improvement_id=improvement_id)
    except improvement_proposals.ImprovementProposalError as exc:
        raise CoreOpError(str(exc)) from exc


def op_improvement_list(conn: sqlite3.Connection, *, status: str | None = None) -> list[dict]:
    return improvement_proposals.list_(conn, status=status)


def op_improvement_mark_ready(
    repo_root: Path,
    conn: sqlite3.Connection,
    *,
    improvement_id: str,
    verdict_artifact_id: str,
    validation_artifact_ids: list[str],
) -> dict:
    try:
        return improvement_proposals.mark_ready(
            repo_root,
            conn,
            improvement_id=improvement_id,
            verdict_artifact_id=verdict_artifact_id,
            validation_artifact_ids=validation_artifact_ids,
        )
    except improvement_proposals.ImprovementProposalError as exc:
        raise CoreOpError(str(exc)) from exc


def op_improvement_request_merge(repo_root: Path, conn: sqlite3.Connection, *, improvement_id: str) -> dict:
    try:
        return improvement_proposals.request_merge(repo_root, conn, improvement_id=improvement_id)
    except improvement_proposals.ImprovementProposalError as exc:
        raise CoreOpError(str(exc)) from exc


def op_improvement_merge(
    repo_root: Path, conn: sqlite3.Connection, *, improvement_id: str, approval_id: str
) -> dict:
    try:
        return improvement_proposals.merge(repo_root, conn, improvement_id=improvement_id, approval_id=approval_id)
    except improvement_proposals.ImprovementProposalError as exc:
        raise CoreOpError(str(exc)) from exc


def op_improvement_reject(
    repo_root: Path, conn: sqlite3.Connection, *, improvement_id: str, reason: str | None = None
) -> dict:
    try:
        return improvement_proposals.reject(repo_root, conn, improvement_id=improvement_id, reason=reason)
    except improvement_proposals.ImprovementProposalError as exc:
        raise CoreOpError(str(exc)) from exc


def op_registry_list(repo_root: Path, *, kind: str, conn: sqlite3.Connection | None = None) -> list[dict]:
    registry_kind = kind_by_key(kind)
    roots = (("data", repo_root / DATA_ROOT), ("config", repo_root / CONFIG_ROOT))
    if registry_kind.data_only:
        # Section 9.3: this kind has no config/app_registry/ counterpart -
        # anything under config/app_registry/<kind>/ (e.g. reference examples,
        # ADR-0001) is never a real, resolvable registry object and MUST NOT
        # be listed as if it were one.
        roots = roots[:1]
    results = []
    for source_name, root in roots:
        kind_dir = root / kind
        if not kind_dir.is_dir():
            continue
        for name_dir in sorted(p for p in kind_dir.iterdir() if p.is_dir()):
            for version in version_names(name_dir, registry_kind):
                row = {"source": source_name, "kind": kind, "name": name_dir.name, "version": version}
                if conn is not None:
                    indexed = registry_index.index_row(conn, kind, name_dir.name, version)
                    row["trust_status"] = indexed["trust_status"] if indexed else None
                    row["digest"] = indexed["digest"] if indexed else None
                results.append(row)
    return results


_OBJECT_LOADERS = {
    WORKFLOWS: load_workflow,
    AGENTS: load_agent_manifest,
    CAPABILITIES: load_capability_record,
    MCP: load_mcp_server,
    SKILLS: load_skill,
    VOICE_PROFILES: load_voice_profile,
    MODEL_PROFILES: load_model_profile,
    PERSONAS: load_persona,
    MEMORY_PROFILES: load_memory_profile,
    SEMANTIC_MEMORIES: load_semantic_memory,
}


def _load_registry_object(repo_root: Path, registry_kind, path: Path):
    if registry_kind is VOICE_PROFILES:
        return load_voice_profile(repo_root, path)
    return _OBJECT_LOADERS[registry_kind](path)


def op_registry_get(repo_root: Path, conn: sqlite3.Connection, *, kind: str, name: str, version: str) -> dict:
    import dataclasses

    registry_kind = kind_by_key(kind)
    path, source = resolve_registry_object(repo_root, kind, name, version, conn=conn)

    indexed = registry_index.index_row(conn, kind, name, version)
    digest = indexed["digest"] if indexed else registry_index.compute_digest(path, registry_kind)
    trust_status = indexed["trust_status"] if indexed else None
    obj = dataclasses.asdict(_load_registry_object(repo_root, registry_kind, path))

    return {
        "kind": kind,
        "name": name,
        "version": version,
        "source": source,
        "content": path.read_text(),
        "digest": digest,
        "trust_status": trust_status,
        "object": obj,
    }


def _skill_md_path(path: Path) -> Path | None:
    # Skills are directory-shaped (<name>/<version>/SKILL.md, Section 9.3),
    # not a single file like every other kind - `path` may point at either
    # the SKILL.md file itself or its containing version directory.
    if path.name == "SKILL.md":
        return path
    if path.is_dir() and (path / "SKILL.md").is_file():
        return path / "SKILL.md"
    return None


def _kind_from_path_position(path: Path) -> str | None:
    # Both registry roots are `<root>/<kind>/<name>/...` (CONFIG_ROOT ends in
    # "app_registry", DATA_ROOT ends in "registry"), so the segment
    # immediately after either anchor is the kind - unambiguous whenever the
    # path is actually under one of them.
    parts = path.parts
    for anchor in ("app_registry", "registry"):
        if anchor in parts:
            index = parts.index(anchor)
            if index + 1 < len(parts):
                candidate = parts[index + 1]
                try:
                    kind_by_key(candidate)
                    return candidate
                except UnknownRegistryKindError:
                    continue
    return None


def _resolve_validate_publish_kind(path: Path, kind: str | None) -> str:
    if kind is not None:
        return kind
    derived = _kind_from_path_position(path)
    if derived is None:
        raise CoreOpError(f"{path}: cannot determine registry kind from its path; pass kind explicitly")
    return derived


def op_registry_validate(path: Path, *, kind: str | None = None) -> dict:
    registry_kind = kind_by_key(_resolve_validate_publish_kind(path, kind))

    if registry_kind is SKILLS:
        skill_md_path = _skill_md_path(path)
        if skill_md_path is None:
            raise CoreOpError(f"{path}: not a Skill (expected a SKILL.md file or its containing directory)")
        skill = load_skill(skill_md_path)
        return {"kind": "Skill", "ref": skill.ref, "valid": True}

    if registry_kind is AGENTS:
        manifest = load_agent_manifest(path)
        return {"kind": "AgentManifest", "ref": manifest.ref, "valid": True}

    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict):
        raise CoreOpError(f"{path}: must be a YAML mapping")

    if registry_kind is WORKFLOWS:
        workflow = parse_workflow(raw)
        return {"kind": "Workflow", "ref": workflow.ref, "valid": True}
    if registry_kind is CAPABILITIES:
        record = parse_capability_record(raw)
        return {"kind": "CapabilityRecord", "ref": record.ref, "valid": True}
    if registry_kind is MCP:
        server = parse_mcp_server(raw)
        return {"kind": "McpServer", "ref": server.ref, "valid": True}
    if registry_kind is MODEL_PROFILES:
        profile = parse_model_profile(raw)
        return {"kind": "ModelProfile", "ref": profile.ref, "valid": True}
    if registry_kind is PERSONAS:
        persona = parse_persona(raw)
        return {"kind": "Persona", "ref": persona.ref, "valid": True}
    if registry_kind is MEMORY_PROFILES:
        profile = parse_memory_profile(raw)
        return {"kind": "MemoryProfile", "ref": profile.ref, "valid": True}
    if registry_kind is SEMANTIC_MEMORIES:
        memory = parse_semantic_memory(raw)
        return {"kind": "SemanticMemory", "ref": memory.ref, "valid": True}
    if registry_kind is VOICE_PROFILES:
        profile = parse_voice_profile(raw)
        return {"kind": "VoiceProfile", "ref": profile.ref, "valid": True}
    raise CoreOpError(f"{path}: registry validate does not support kind '{registry_kind.key}'")


def op_registry_publish(repo_root: Path, conn: sqlite3.Connection, *, path: Path, kind: str) -> dict:
    registry_kind = kind_by_key(kind)

    if registry_kind is SKILLS:
        skill_md_path = _skill_md_path(path)
        if skill_md_path is None:
            raise CoreOpError(f"{path}: not a Skill (expected a SKILL.md file or its containing directory)")
        skill = load_skill(skill_md_path)
        skill_dir = skill_md_path.parent
        digest = directory_digest(skill_dir)
        target_dir = kind_object_path(repo_root / DATA_ROOT / "skills" / skill.name, SKILLS, skill.version).parent
        if target_dir.is_dir():
            shutil.rmtree(target_dir)
        target_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(skill_dir, target_dir)

        conn.execute(
            "INSERT INTO registry_index (kind, name, version, digest, source, path, trust_status, indexed_at) "
            "VALUES ('skills', ?, ?, ?, 'data', ?, 'local', ?) "
            "ON CONFLICT(kind, name, version) DO UPDATE SET "
            "digest=excluded.digest, path=excluded.path, indexed_at=excluded.indexed_at",
            (skill.name, skill.version, digest, str(target_dir.relative_to(repo_root)), utc_now_rfc3339()),
        )
        conn.commit()
        return {
            "kind": "skills",
            "name": skill.name,
            "version": skill.version,
            "digest": digest,
            "path": str(target_dir),
        }

    if registry_kind is AGENTS:
        manifest = load_agent_manifest(path)
        name, version = manifest.name, manifest.version
    else:
        raw = yaml.safe_load(path.read_text())
        if not isinstance(raw, dict):
            raise CoreOpError(f"{path}: must be a YAML mapping")

        if registry_kind is WORKFLOWS:
            workflow = parse_workflow(raw)
            name, version = workflow.metadata.name, workflow.metadata.version
        elif registry_kind is CAPABILITIES:
            record = parse_capability_record(raw)
            name, version = record.identity.name, record.identity.version
        elif registry_kind is MCP:
            server = parse_mcp_server(raw)
            name, version = server.name, server.version
        elif registry_kind is MODEL_PROFILES:
            profile = parse_model_profile(raw)
            name, version = profile.name, profile.version
        elif registry_kind is PERSONAS:
            persona = parse_persona(raw)
            name, version = persona.name, persona.version
        elif registry_kind is MEMORY_PROFILES:
            profile = parse_memory_profile(raw)
            name, version = profile.metadata.name, profile.metadata.version
        elif registry_kind is SEMANTIC_MEMORIES:
            memory = parse_semantic_memory(raw)
            name, version = memory.metadata.name, memory.metadata.version
        elif registry_kind is VOICE_PROFILES:
            profile = parse_voice_profile(raw)
            persona_name, sep, persona_version = profile.persona_ref.partition("@")
            if not sep or not persona_name or not persona_version:
                raise CoreOpError(
                    f"{path}: voice profile persona_ref must be '<name>@<version>', got {profile.persona_ref!r}"
                )
            resolve_registry_object(repo_root, "personas", persona_name, persona_version, conn=conn)
            name, version = profile.name, profile.version
        else:
            raise CoreOpError(f"{path}: registry publish does not support kind '{kind}'")

    payload = path.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    target_dir = repo_root / DATA_ROOT / kind / name
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = kind_object_path(target_dir, registry_kind, version)
    target_path.write_bytes(payload)

    conn.execute(
        "INSERT INTO registry_index (kind, name, version, digest, source, path, trust_status, indexed_at) "
        "VALUES (?, ?, ?, ?, 'data', ?, 'local', ?) "
        "ON CONFLICT(kind, name, version) DO UPDATE SET "
        "digest=excluded.digest, path=excluded.path, indexed_at=excluded.indexed_at",
        (kind, name, version, digest, str(target_path.relative_to(repo_root)), utc_now_rfc3339()),
    )
    conn.commit()
    return {"kind": kind, "name": name, "version": version, "digest": digest, "path": str(target_path)}


def op_registry_reindex(repo_root: Path, conn: sqlite3.Connection) -> dict:
    return registry_index.reindex(repo_root, conn)


_TRUST_STATUSES = ("local", "trusted", "quarantined", "blocked")


def op_registry_trust(conn: sqlite3.Connection, *, kind: str, name: str, version: str, status: str) -> dict:
    kind_by_key(kind)  # validates the kind, raises UnknownRegistryKindError otherwise
    if status not in _TRUST_STATUSES:
        raise CoreOpError(f"status must be one of {_TRUST_STATUSES}, got {status!r}")
    row = registry_index.set_trust_status(conn, kind, name, version, status)
    if row is None:
        raise CoreOpError(f"{kind}/{name}@{version} is not indexed; run 'awf registry reindex' or publish it first")
    return row


def op_registry_retire(conn: sqlite3.Connection, *, kind: str, name: str, version: str) -> dict:
    return op_registry_trust(conn, kind=kind, name=name, version=version, status="blocked")


def op_workflow_author_draft(
    repo_root: Path,
    conn: sqlite3.Connection,
    *,
    objective: str,
    name: str | None = None,
    version: str | None = None,
    profile_ref: str = workflow_authoring.DEFAULT_AUTHOR_PROFILE,
) -> dict:
    try:
        return workflow_authoring.author_workflow_draft(
            repo_root,
            conn,
            objective=objective,
            name=name,
            version=version,
            profile_ref=profile_ref,
        )
    except workflow_authoring.ProposalError as exc:
        raise CoreOpError(str(exc)) from exc


def op_proposal_get(repo_root: Path, conn: sqlite3.Connection, *, proposal_id: str) -> dict:
    try:
        return workflow_authoring.get_proposal(repo_root, conn, proposal_id=proposal_id)
    except workflow_authoring.ProposalError as exc:
        raise CoreOpError(str(exc)) from exc


def op_proposal_update(
    repo_root: Path,
    conn: sqlite3.Connection,
    *,
    proposal_id: str,
    content: str,
    summary: str | None = None,
) -> dict:
    try:
        return workflow_authoring.update_proposal(
            repo_root,
            conn,
            proposal_id=proposal_id,
            content=content,
            summary=summary,
        )
    except workflow_authoring.ProposalError as exc:
        raise CoreOpError(str(exc)) from exc


def op_proposal_publish(
    repo_root: Path,
    conn: sqlite3.Connection,
    *,
    proposal_id: str,
    digest: str,
) -> dict:
    try:
        proposal = workflow_authoring.get_proposal(repo_root, conn, proposal_id=proposal_id)
    except workflow_authoring.ProposalError as exc:
        raise CoreOpError(str(exc)) from exc
    if proposal["status"] != "draft":
        raise CoreOpError(f"proposal {proposal_id} is not draft (status={proposal['status']})")
    if proposal["draft_digest"] != digest:
        raise CoreOpError(
            f"proposal {proposal_id} draft digest mismatch: expected {proposal['draft_digest']}, got {digest}"
        )
    draft_path = repo_root / proposal["draft_path"]
    actual_digest = hashlib.sha256(draft_path.read_bytes()).hexdigest()
    if actual_digest != digest:
        raise CoreOpError(
            f"proposal {proposal_id} draft file digest mismatch: expected {digest}, actual {actual_digest}"
        )
    published = op_registry_publish(repo_root, conn, path=draft_path, kind=proposal["kind"])
    try:
        marked = workflow_authoring.mark_published(
            repo_root,
            conn,
            proposal_id=proposal_id,
            published_digest=published["digest"],
        )
    except workflow_authoring.ProposalError as exc:
        raise CoreOpError(str(exc)) from exc
    return {"proposal": marked, "published": published}


def op_proposal_reject(
    repo_root: Path,
    conn: sqlite3.Connection,
    *,
    proposal_id: str,
    reason: str | None = None,
) -> dict:
    try:
        return workflow_authoring.reject_proposal(repo_root, conn, proposal_id=proposal_id, reason=reason)
    except workflow_authoring.ProposalError as exc:
        raise CoreOpError(str(exc)) from exc


def _split_ref(ref: str) -> tuple[str, str]:
    name, sep, version = ref.partition("@")
    if not sep or not name or not version:
        raise CoreOpError(f"ref must be '<name>@<version>', got {ref!r}")
    return name, version


def op_memory_search(
    repo_root: Path,
    conn: sqlite3.Connection,
    *,
    query: str,
    profile_ref: str = "default@1.0.0",
) -> dict:
    from awf.memory.context import retrieve_memory_context
    from awf.memory.episodic import search_events
    from awf.memory.semantic import search_semantic_memories

    try:
        semantic = search_semantic_memories(repo_root, conn, query=query, profile_ref=profile_ref)
        episodic = search_events(conn, query=query, limit=20)
        context = retrieve_memory_context(repo_root, conn, query=query, profile_ref=profile_ref)
    except ValueError as exc:
        raise CoreOpError(str(exc)) from exc
    return {"query": query, "profile_ref": profile_ref, "semantic": semantic, "episodic": episodic, "context": context}


def op_memory_get(repo_root: Path, conn: sqlite3.Connection, *, ref: str) -> dict:
    name, version = _split_ref(ref)
    return op_registry_get(repo_root, conn, kind="semantic-memories", name=name, version=version)


def op_memory_propose(repo_root: Path, conn: sqlite3.Connection, *, path: Path, summary: str | None = None) -> dict:
    from awf.memory.proposals import MemoryProposalError, propose_semantic_memory

    try:
        return propose_semantic_memory(repo_root, conn, path=path, summary=summary)
    except MemoryProposalError as exc:
        raise CoreOpError(str(exc)) from exc


def op_memory_publish(repo_root: Path, conn: sqlite3.Connection, *, proposal_id: str, digest: str) -> dict:
    return op_proposal_publish(repo_root, conn, proposal_id=proposal_id, digest=digest)


def op_memory_reject(repo_root: Path, conn: sqlite3.Connection, *, proposal_id: str, reason: str | None = None) -> dict:
    return op_proposal_reject(repo_root, conn, proposal_id=proposal_id, reason=reason)


def op_memory_block(conn: sqlite3.Connection, *, ref: str) -> dict:
    name, version = _split_ref(ref)
    return op_registry_retire(conn, kind="semantic-memories", name=name, version=version)


def op_session_start(
    conn: sqlite3.Connection, *, title: str | None = None, expires_at: str | None = None
) -> dict:
    from awf.memory.sessions import start_session

    return start_session(conn, title=title, expires_at=expires_at)


def op_session_append(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    role: str,
    content: dict,
    summary: str | None = None,
) -> dict:
    from awf.memory.sessions import SessionError, append_entry

    try:
        return append_entry(conn, session_id=session_id, role=role, content=content, summary=summary)
    except SessionError as exc:
        raise CoreOpError(str(exc)) from exc


def op_session_show(conn: sqlite3.Connection, *, session_id: str) -> dict:
    from awf.memory.sessions import SessionError, show_session

    try:
        return show_session(conn, session_id=session_id)
    except SessionError as exc:
        raise CoreOpError(str(exc)) from exc


def op_session_summarize(conn: sqlite3.Connection, *, session_id: str, summary: str | None = None) -> dict:
    from awf.memory.sessions import SessionError, summarize_session

    try:
        return summarize_session(conn, session_id=session_id, summary=summary)
    except SessionError as exc:
        raise CoreOpError(str(exc)) from exc


def op_episodic_search(conn: sqlite3.Connection, *, query: str, run_id: str | None = None) -> list[dict]:
    from awf.memory.episodic import search_events

    return search_events(conn, query=query, run_id=run_id)


def op_episodic_timeline(conn: sqlite3.Connection, *, run_id: str) -> dict:
    from awf.memory.episodic import run_timeline

    try:
        return run_timeline(conn, run_id=run_id)
    except ValueError as exc:
        raise CoreOpError(str(exc)) from exc


def _resolve_voice_profile(repo_root: Path, voice_profile_ref: str | None = None) -> dict:
    from awf.registry.voice_profile import DEFAULT_VOICE_PROFILE_REF

    ref = voice_profile_ref or DEFAULT_VOICE_PROFILE_REF
    name, sep, version = ref.partition("@")
    if not sep or not name or not version:
        raise CoreOpError(f"voice profile ref must be '<name>@<version>', got {ref!r}")
    path, _source = resolve_registry_object(repo_root, "voice-profiles", name, version)
    profile = load_voice_profile(repo_root, path)
    candidates = profile.enabled_candidates_by_priority()
    if not candidates:
        raise CoreOpError(f"voice profile '{profile.ref}' has no enabled TTS candidates")
    candidate = candidates[0]
    return {
        "voice_profile_ref": profile.ref,
        "voice_id": candidate.voice_id,
        "engine": candidate.engine,
        "model": candidate.model,
        "speed": candidate.speed,
        "privacy": {"local_only": profile.privacy.local_only},
        "limits": {"max_seconds_per_utterance": profile.limits.max_seconds_per_utterance},
    }


def op_voice_session_start(conn: sqlite3.Connection, *, title: str | None = None, wake_enabled: bool = False) -> dict:
    from awf.speech.session import start_voice_session

    session = start_voice_session(conn, title=title, wake_enabled=wake_enabled)
    return {
        "voice_session_id": session.voice_session_id,
        "memory_session_id": session.memory_session_id,
        "state": session.state,
    }


def op_voice_session_event(
    conn: sqlite3.Connection,
    *,
    voice_session_id: str,
    frame_type: str,
    payload: dict | None = None,
    turn_id: str | None = None,
) -> dict:
    from awf.speech.session import VoiceFrame, VoiceSessionError, accept_frame

    try:
        session = accept_frame(
            conn,
            voice_session_id=voice_session_id,
            frame=VoiceFrame(frame_type, payload or {}, turn_id=turn_id),
        )
    except VoiceSessionError as exc:
        raise CoreOpError(str(exc)) from exc
    return {
        "voice_session_id": session.voice_session_id,
        "memory_session_id": session.memory_session_id,
        "state": session.state,
    }


def op_voice_session_close(conn: sqlite3.Connection, *, voice_session_id: str, reason: str | None = None) -> dict:
    return op_voice_session_event(
        conn,
        voice_session_id=voice_session_id,
        frame_type="session.closed",
        payload={"reason": reason} if reason else {},
    )


def op_voice_submit_text(
    repo_root: Path,
    conn: sqlite3.Connection,
    *,
    voice_session_id: str,
    text: str,
    workflow_ref: str | None,
    voice_profile_ref: str | None = None,
    turn_id: str | None = None,
) -> dict:
    from awf.speech.session import append_assistant_response, append_operator_utterance, current_voice_session

    if not workflow_ref:
        raise CoreOpError("voice.submitText requires a workflowRef")
    if not text.strip():
        raise CoreOpError("voice.submitText requires non-empty text")

    voice_profile = _resolve_voice_profile(repo_root, voice_profile_ref)
    session = current_voice_session(conn, voice_session_id=voice_session_id)
    if session.state == "transcribing":
        op_voice_session_event(
            conn,
            voice_session_id=voice_session_id,
            frame_type="stt.final",
            payload={"text": text},
            turn_id=turn_id,
        )
    op_voice_session_event(
        conn,
        voice_session_id=voice_session_id,
        frame_type="core.submitted",
        payload={"workflow_ref": workflow_ref},
        turn_id=turn_id,
    )
    append_operator_utterance(conn, voice_session_id=voice_session_id, text=text, turn_id=turn_id)
    run_result = op_run_start(
        repo_root,
        conn,
        workflow_ref=workflow_ref,
        input_data={"objective": text, "voiceSessionId": voice_session_id, "turnId": turn_id},
    )
    response_text = _voice_response_text(workflow_ref, run_result)
    op_voice_session_event(
        conn,
        voice_session_id=voice_session_id,
        frame_type="core.output_text",
        payload={"run_id": run_result["run_id"], "response_text": response_text},
        turn_id=turn_id,
    )
    append_assistant_response(
        conn,
        voice_session_id=voice_session_id,
        text=response_text,
        voice_profile_ref=voice_profile["voice_profile_ref"],
        voice_id=voice_profile["voice_id"],
        turn_id=turn_id,
        run_id=run_result["run_id"],
    )
    return {
        "voice_session_id": voice_session_id,
        "state": "speaking",
        "recognized_text": text,
        "response_text": response_text,
        "run": run_result,
        "voice": voice_profile,
    }


def _voice_response_text(workflow_ref: str, run_result: dict) -> str:
    outputs = run_result.get("outputs")
    if isinstance(outputs, dict) and isinstance(outputs.get("response_text"), str):
        return outputs["response_text"]
    return f"Workflow {workflow_ref} finished with status {run_result.get('status')} (run {run_result.get('run_id')})."


def op_secret_set(repo_root: Path, conn: sqlite3.Connection, *, name: str, value: str) -> dict:
    key = get_env_value(env_path(repo_root), "AWF_SECRET_KEY").encode("ascii")
    set_secret(conn, name, value, key)
    return {"name": name, "status": "set"}


def op_secret_list_names(conn: sqlite3.Connection) -> list[str]:
    return list_secret_names(conn)


def _jsonable(value):
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, Path):
        return str(value)
    return value


def _recent_verdict_artifacts(conn: sqlite3.Connection, *, limit: int = 5) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM artifacts WHERE artifact_type = 'verdict' ORDER BY created_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [dict(row) for row in rows]


def _registry_counts(repo_root: Path, conn: sqlite3.Connection) -> dict[str, int]:
    counts: dict[str, int] = {}
    for registry_kind in KINDS:
        counts[registry_kind.key] = len(op_registry_list(repo_root, kind=registry_kind.key, conn=conn))
    return counts


def op_system_readiness(repo_root: Path) -> dict:
    from awf.hardware.profiler import resolve_hardware_profile_id

    try:
        profile_id, payload = resolve_hardware_profile_id(repo_root)
        return {
            "profile_id": profile_id,
            "inventory": _jsonable(payload.get("inventory")),
            "tokens": _jsonable(payload.get("tokens", [])),
            "readiness": _jsonable(payload.get("readiness", {})),
        }
    except Exception as exc:
        return {
            "profile_id": None,
            "inventory": None,
            "tokens": [],
            "readiness": {},
            "error": str(exc),
        }


def _doctor_check(name: str, status: str, summary: str, *, detail=None, next_action: str | None = None) -> dict:
    return {
        "name": name,
        "status": status,
        "summary": summary,
        "detail": _jsonable(detail or {}),
        "next_action": next_action,
    }


def _doctor_overall(checks: list[dict]) -> str:
    if any(check["status"] == "error" for check in checks):
        return "error"
    if any(check["status"] == "warn" for check in checks):
        return "warn"
    return "ok"


def _command_version(command: str, *args: str) -> tuple[bool, str | None]:
    executable = shutil.which(command)
    if executable is None:
        return False, None
    try:
        result = subprocess.run(
            [executable, *args],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception as exc:
        return True, str(exc)
    output = (result.stdout or result.stderr).strip().splitlines()
    return True, output[0] if output else None


def _doctor_python(repo_root: Path) -> dict:
    selected = _repo_python_executable(repo_root)
    selected_path = selected[1] if selected else None
    current = Path(sys.executable)
    expected = Path(selected_path) if selected_path else None
    in_repo_venv = expected is not None and current.resolve() == expected.resolve()
    version_ok = (3, 12) <= sys.version_info[:2] < (3, 15)
    if not version_ok:
        return _doctor_check(
            "python",
            "error",
            f"Python {sys.version.split()[0]} is outside the supported >=3.12,<3.15 range.",
            detail={"executable": sys.executable, "expected": selected_path},
            next_action="Recreate backend/.venv with Python 3.12, 3.13, or 3.14.",
        )
    if not in_repo_venv:
        return _doctor_check(
            "python",
            "warn",
            "Current Python is supported but is not the repo venv interpreter.",
            detail={"executable": sys.executable, "expected": selected_path},
            next_action="Run commands through backend/.venv/Scripts/python.exe on Windows or backend/.venv/bin/python on Linux.",
        )
    return _doctor_check(
        "python",
        "ok",
        f"Using repo venv Python {sys.version.split()[0]}.",
        detail={"executable": sys.executable, "marker": selected[0] if selected else None},
    )


def _doctor_node(repo_root: Path) -> dict:
    node_present, node_version = _command_version("node", "--version")
    npm_present, npm_version = _command_version("npm", "--version")
    node_modules = repo_root / "frontend" / "node_modules"
    detail = {"node": node_version, "npm": npm_version, "node_modules": str(node_modules)}
    frontend_node_requirement = "Node.js 24 LTS >=24.15.0"
    if not node_present or not npm_present:
        return _doctor_check(
            "frontend",
            "warn",
            "Node.js or npm is not available; CLI/GUI frontends cannot run from this shell.",
            detail=detail,
            next_action=f"Install {frontend_node_requirement} and run `npm --prefix frontend install`.",
        )
    node_parts = None
    if node_version and node_version.startswith("v"):
        try:
            node_parts = tuple(int(part) for part in node_version[1:].split(".")[:3])
        except ValueError:
            node_parts = None
    if node_parts is not None and node_parts < (24, 15, 0):
        return _doctor_check(
            "frontend",
            "warn",
            f"Node.js {node_version} is below the frontend requirement.",
            detail=detail,
            next_action=f"Install {frontend_node_requirement} and rerun `npm --prefix frontend install`.",
        )
    if not node_modules.is_dir():
        return _doctor_check(
            "frontend",
            "warn",
            "Frontend dependencies are not installed.",
            detail=detail,
            next_action="Run `npm --prefix frontend install`.",
        )
    return _doctor_check("frontend", "ok", "Node, npm, and frontend dependencies are present.", detail=detail)


def _doctor_registry(repo_root: Path) -> dict:
    targets = [
        (repo_root / "config" / "app_registry" / "workflows" / "assistant-default" / "1.0.0.yaml", "workflows"),
        (repo_root / "config" / "app_registry" / "capabilities" / "assistant_reply" / "1.0.0.yaml", "capabilities"),
    ]
    results = []
    for path, kind in targets:
        if not path.is_file():
            return _doctor_check(
                "registry",
                "error",
                f"Required default registry object is missing: {path.relative_to(repo_root)}",
                detail={"path": str(path), "kind": kind},
                next_action="Restore the repo-tracked default registry object.",
            )
        try:
            results.append(op_registry_validate(path, kind=kind))
        except Exception as exc:
            return _doctor_check(
                "registry",
                "error",
                f"Default registry object failed validation: {path.relative_to(repo_root)}",
                detail={"path": str(path), "kind": kind, "error": str(exc)},
                next_action="Fix or restore the invalid default registry object.",
            )
    return _doctor_check("registry", "ok", "Default assistant workflow and capability validate.", detail={"validated": results})


def _doctor_database(repo_root: Path) -> dict:
    path = resolve_db_path(repo_root)
    if not path.is_file():
        return _doctor_check(
            "database",
            "error",
            "AWF database has not been bootstrapped.",
            detail={"path": str(path)},
            next_action="Run `awf-setup` from the repo venv.",
        )
    return _doctor_check("database", "ok", "AWF database exists.", detail={"path": str(path)})


def _doctor_env(repo_root: Path) -> dict:
    path = env_path(repo_root)
    if not path.is_file():
        return _doctor_check(
            "env",
            "error",
            ".env is missing.",
            detail={"path": str(path)},
            next_action="Run `awf-setup` to generate local secrets.",
        )
    try:
        secret = get_env_value(path, "AWF_SECRET_KEY")
    except Exception as exc:
        return _doctor_check(
            "env",
            "error",
            ".env does not contain a usable AWF_SECRET_KEY.",
            detail={"error": str(exc)},
            next_action="Regenerate .env with `awf-setup` or restore the correct local key.",
        )
    if not secret or secret == "<your-secret-key-here>":
        return _doctor_check(
            "env",
            "error",
            ".env still contains a placeholder secret key.",
            next_action="Run `awf-setup` or replace AWF_SECRET_KEY with a generated local key.",
        )
    return _doctor_check("env", "ok", ".env contains a local AWF secret key.")


def _doctor_paths(repo_root: Path) -> dict:
    cache_temp = repo_root / "cache" / "temp"
    cache_sandbox = repo_root / "cache" / "sandbox"
    missing = [str(path.relative_to(repo_root)) for path in (cache_temp, cache_sandbox) if not path.is_dir()]
    if missing:
        return _doctor_check(
            "local_paths",
            "warn",
            "Some local cache directories are missing.",
            detail={"missing": missing, "platform": os.name},
            next_action="Run `awf-setup`; Windows operators should use cache/temp for temp-heavy commands.",
        )
    return _doctor_check(
        "local_paths",
        "ok",
        "Local cache and sandbox paths exist.",
        detail={"cache_temp": str(cache_temp), "cache_sandbox": str(cache_sandbox), "platform": os.name},
    )


def _doctor_agent_clis() -> dict:
    commands = {
        "codex": ("codex", "--version"),
        "claude-code": ("claude", "--version"),
        "antigravity": ("antigravity", "--version"),
        "copilot": ("gh", "--version"),
        "cline": ("cline", "--version"),
    }
    found = {}
    for adapter, command in commands.items():
        present, version = _command_version(*command)
        found[adapter] = {"present": present, "version": version}
    if any(item["present"] for item in found.values()):
        return _doctor_check("agent_clis", "ok", "At least one implementation agent CLI is visible.", detail=found)
    return _doctor_check(
        "agent_clis",
        "warn",
        "No implementation agent CLI is visible; first-run assistant still works.",
        detail=found,
        next_action="Install and authenticate Codex, Claude Code, Antigravity, GitHub Copilot CLI, or Cline before running implementation workflows.",
    )


def _doctor_speech(readiness: dict) -> dict:
    results = readiness.get("readiness", {}) if isinstance(readiness, dict) else {}
    speech = {name: result for name, result in results.items() if name in {"stt", "tts", "vad", "wake"}}
    if not speech:
        return _doctor_check(
            "speech",
            "warn",
            "Speech readiness is unavailable.",
            detail=readiness,
            next_action="Run `awf-speech models verify`; run `awf-speech models sync` if artifacts are missing.",
        )
    if all(result.get("ready") for result in speech.values()):
        return _doctor_check("speech", "ok", "Speech readiness checks are ready.", detail=speech)
    return _doctor_check(
        "speech",
        "warn",
        "One or more speech functions are not ready.",
        detail=speech,
        next_action="Run `awf-speech models verify`, then `awf-speech models sync` for missing artifacts.",
    )


def op_system_doctor(repo_root: Path) -> dict:
    readiness = op_system_readiness(repo_root)
    checks = [
        _doctor_python(repo_root),
        _doctor_env(repo_root),
        _doctor_database(repo_root),
        _doctor_paths(repo_root),
        _doctor_registry(repo_root),
        _doctor_node(repo_root),
        _doctor_agent_clis(),
        _doctor_speech(readiness),
    ]
    next_actions = [check["next_action"] for check in checks if check.get("next_action")]
    return {
        "status": _doctor_overall(checks),
        "checks": checks,
        "readiness": readiness,
        "next_actions": next_actions,
        "first_run_command": 'awf run assistant-default@1.0.0 --objective "check the system"',
    }


def _control_error(exc: Exception) -> dict:
    return {"error": str(exc)}


def op_control_center_summary(repo_root: Path, conn: sqlite3.Connection) -> dict:
    try:
        llm_servers = op_llm_servers(repo_root)
    except Exception as exc:
        llm_servers = _control_error(exc)
    try:
        llm_status = op_llm_serve(repo_root, conn, action="status")
    except Exception as exc:
        llm_status = _control_error(exc)
    readiness = op_system_readiness(repo_root)
    doctor = op_system_doctor(repo_root)
    improvements = op_improvement_list(conn)
    return {
        "runs": op_run_list(conn),
        "approvals": op_approval_list(conn),
        "improvements": improvements,
        "recent_verdicts": _recent_verdict_artifacts(conn),
        "registry_counts": _registry_counts(repo_root, conn),
        "llm": {
            "servers": llm_servers,
            "status": llm_status,
        },
        "readiness": readiness,
        "doctor": doctor,
    }


def op_control_center_run_detail(repo_root: Path, conn: sqlite3.Connection, *, run_id: str) -> dict:
    status = op_run_status(conn, run_id=run_id)
    artifacts = op_artifact_list(conn, run_id=run_id)
    timeline = op_episodic_timeline(conn, run_id=run_id)
    improvements = [proposal for proposal in op_improvement_list(conn) if proposal.get("run_id") == run_id]
    verdicts = [artifact for artifact in artifacts if artifact.get("artifact_type") == "verdict"]
    return {
        "run": status,
        "outcome": op_run_outcome(conn, run_id=run_id),
        "artifacts": artifacts,
        "timeline": timeline,
        "improvements": improvements,
        "verdicts": verdicts,
    }


def op_llm_servers(repo_root: Path) -> dict:
    from awf.hardware.profiler import resolve_hardware_profile_id
    from awf.llm.discovery import binary_path, local_models
    from awf.llm.selector import current_selection
    from awf.llm.servers import artifact_for, load_servers
    from awf.llm.sidecar import probe

    default_id, servers = load_servers(repo_root)
    profile_id, _ = resolve_hardware_profile_id(repo_root)
    selection = current_selection(repo_root)
    models = local_models(repo_root)

    server_reports = {}
    for s_id, s in servers.items():
        h = probe(s)
        art = artifact_for(s, profile_id)
        bin_p = binary_path(repo_root, profile_id, art) if art else None

        server_reports[s_id] = {
            "managed": s.managed,
            "base_url": s.base_url,
            "provider": s.provider,
            "reachable": h.reachable,
            "reachability_reason": h.reason,
            "declared_artifact": art.profile_id if art else None,
            "binary_present": bin_p.is_file() if bin_p else False,
            "binary_path": str(bin_p) if bin_p else None,
            "local_models_available": [m.name for m in models] if s.managed else [],
        }

    return {
        "default_server": default_id,
        "host_profile_id": profile_id,
        "current_selection": asdict(selection) if selection else None,
        "servers": server_reports,
    }


def op_llm_models(repo_root: Path) -> dict:
    from awf.llm.discovery import local_models
    from awf.llm.servers import load_servers
    from awf.llm.sidecar import probe

    models = local_models(repo_root)
    res: dict[str, object] = {
        "local_models": [
            {
                "name": m.name,
                "primary": str(m.primary),
                "files": [str(f) for f in m.files],
            }
            for m in models
        ]
    }

    try:
        _, servers = load_servers(repo_root)
        if "ollama" in servers:
            ollama_s = servers["ollama"]
            h = probe(ollama_s)
            if h.reachable:
                import json
                import urllib.request

                url = f"{ollama_s.base_url.rstrip('/')}/api/tags"
                try:
                    with urllib.request.urlopen(url, timeout=2.0) as resp:
                        tags_data = json.loads(resp.read().decode())
                        res["ollama_models"] = tags_data.get("models", [])
                except Exception as exc:
                    res["ollama_models_error"] = str(exc)
    except Exception:
        pass

    return res


def op_llm_acquire(repo_root: Path) -> dict:
    from awf.hardware.profiler import resolve_hardware_profile_id
    from awf.llm.discovery import acquire_binary
    from awf.llm.servers import artifact_for, load_servers

    profile_id, _ = resolve_hardware_profile_id(repo_root)
    _, servers = load_servers(repo_root)

    llama_s = servers.get("llama-server")
    if llama_s is None:
        raise CoreOpError("llama-server is not declared in config/llm/servers.yaml")

    art = artifact_for(llama_s, profile_id)
    if art is not None and art.archive == "manual":
        cpu_profile_id = _cpu_fallback_profile_id(profile_id)
        cpu_art = artifact_for(llama_s, cpu_profile_id)
        if cpu_art is not None and cpu_art.archive != "manual":
            profile_id, art = cpu_profile_id, cpu_art
    if art is None:
        raise CoreOpError(f"No artifact declared for canonical profile ID '{profile_id}'")

    try:
        return acquire_binary(repo_root, profile_id, art)
    except Exception as exc:
        raise CoreOpError(f"Failed to acquire binary for '{profile_id}': {exc}") from exc


def op_llm_select(
    repo_root: Path,
    conn: sqlite3.Connection,
    *,
    server_id: str,
    model: str | None = None,
    allow_remote: bool = False,
) -> dict:
    from awf.llm.selector import select
    from awf.llm.servers import LlmServerError

    try:
        return select(repo_root, conn, server_id=server_id, model=model, allow_remote=allow_remote)
    except LlmServerError as exc:
        raise CoreOpError(str(exc)) from exc


def op_llm_serve(repo_root: Path, conn: sqlite3.Connection, *, action: str) -> dict:
    from dataclasses import asdict

    from awf.hardware.profiler import resolve_hardware_profile_id
    from awf.llm.discovery import local_models, model_by_name
    from awf.llm.selector import current_selection
    from awf.llm.servers import load_servers
    from awf.llm.sidecar import start, status, stop

    default_id, servers = load_servers(repo_root)
    sel = current_selection(repo_root)

    if sel is not None and sel.server_id in servers:
        server = servers[sel.server_id]
        model_name = sel.model
    else:
        server = servers[default_id]
        model_name = None

    if action == "stop":
        st = stop(conn=conn, repo_root=repo_root)
        return asdict(st)

    if action == "status":
        st = status(server, repo_root=repo_root)
        return asdict(st)

    if action == "start":
        profile_id, _ = resolve_hardware_profile_id(repo_root)
        if server.managed:
            profile_id, art = _select_managed_llm_artifact(repo_root, server, profile_id)
        else:
            art = None

        model = None
        if model_name:
            try:
                model = model_by_name(repo_root, model_name)
            except Exception:
                pass
        if model is None:
            avail = local_models(repo_root)
            if avail:
                model = avail[0]

        st = start(repo_root, server, art, model, conn=conn, detach=True)
        return asdict(st)

    raise CoreOpError(f"Unknown serve action '{action}'. Valid: start, stop, status")
