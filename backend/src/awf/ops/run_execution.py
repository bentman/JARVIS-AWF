"""Run executor construction and lifecycle helpers."""

import json
import shlex
import sqlite3
import subprocess
import threading
from pathlib import Path

from awf.adapters.antigravity_cli import invoke as antigravity_invoke
from awf.adapters.claude_code import invoke as claude_code_invoke
from awf.adapters.cline_cli import invoke as cline_invoke
from awf.adapters.codex_cli import invoke as codex_invoke
from awf.adapters.copilot_cli import invoke as copilot_invoke
from awf.clock import utc_now_rfc3339
from awf.db.connection import get_connection
from awf.engine.run import create_run
from awf.envfile import get_env_value
from awf.gates.gate_node import make_trifecta_gate_executor
from awf.ids import uuid7
from awf.isolation.scratch import create_scratch_dir, remove_scratch_dir
from awf.isolation.worktree import create_worktree, remove_worktree
from awf.ops.shared import CoreOpError
from awf.paths import db_path as resolve_db_path
from awf.paths import env_path
from awf.pyexec import repo_python_executable
from awf.registry.capability_record import load_capability_record
from awf.registry.index import latest_version
from awf.registry.model_profile import load_model_profile
from awf.registry.resolve import RegistryObjectNotFoundError, resolve_registry_object
from awf.workflow.approval import make_approval_node_executor
from awf.workflow.definition import load_workflow
from awf.workflow.engine import make_activity_node_executor, make_agent_node_executor, run_workflow_definition
from awf.workflow.handoff import make_handoff_node_executor
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

_MAP_ITEM_DB_LOCK = threading.Lock()

DEFAULT_ASSISTANT_WORKFLOW_REF = "assistant-default@1.0.0"


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
        selected = repo_python_executable(repo_root)
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
        timeout = int(node.get("timeoutSeconds", 300))
        try:
            result = subprocess.run(args, cwd=worktree, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return False
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

        child_workflow = _resolve_workflow(repo_root, workflow_ref, conn=conn)
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
    def run_map_item(
        parent_head: str,
        index: int,
        workflow_ref: str,
        item,
        item_conn_override: sqlite3.Connection | None = None,
    ) -> tuple[str, Path, dict]:
        db_path = resolve_db_path(repo_root)
        with _MAP_ITEM_DB_LOCK:
            close_item_conn = item_conn_override is None
            if item_conn_override is None:
                try:
                    item_conn = get_connection(db_path)
                except sqlite3.OperationalError as exc:
                    raise RuntimeError(f"map item {index}: database connection failed: {exc}") from exc
            else:
                item_conn = item_conn_override
            try:
                try:
                    child_workflow = _resolve_workflow(repo_root, workflow_ref, conn=item_conn)
                    child_run_id = uuid7()
                    create_run(
                        item_conn,
                        run_id=child_run_id,
                        workflow_ref=child_workflow.ref,
                        input_json=json.dumps({"item": item, "index": index}),
                    )
                    item_worktree = create_worktree(repo_root, child_run_id, base_ref=parent_head)
                    item_scratch_dir = create_scratch_dir(repo_root, child_run_id)
                except sqlite3.OperationalError as exc:
                    raise RuntimeError(f"map item {index}: child run setup failed: {exc}") from exc
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
                if close_item_conn:
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
        "activity": make_activity_node_executor(
            repo_root=repo_root, worktree_path=worktree, workflow_input=workflow_input
        ),
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
    try:
        if not version:
            version = latest_version(repo_root, "workflows", name)
        path, _source = resolve_registry_object(repo_root, "workflows", name, version, conn=conn)
    except RegistryObjectNotFoundError:
        raise CoreOpError(f"unknown workflow {workflow_ref!r}. {_available_workflows_hint(repo_root, conn)}") from None
    return load_workflow(path)


def _available_workflows_hint(repo_root: Path, conn: sqlite3.Connection | None) -> str:
    from awf.ops.registry import op_registry_list

    refs = sorted(
        {f"{row['name']}@{row['version']}" for row in op_registry_list(repo_root, kind="workflows", conn=conn)}
    )
    if not refs:
        return "No workflows are registered - publish one with `awf registry publish`."
    return "Available workflows: " + ", ".join(refs)


def _retain_worktree_for_improvement(workflow_ref: str, input_data: dict) -> bool:
    return workflow_ref.startswith("self-improvement@") or input_data.get("retainWorktreeForImprovement") is True


def _cleanup_run_workspace(repo_root: Path, run_id: str, result: dict, *, retain_worktree: bool = False) -> None:
    # Cache state is ephemeral by design (Section 7/10.4). Keep failed
    # worktrees for inspection, but never retain scratch state after a
    # terminal run because adapter homes may contain temporary credential
    # links or locked-down copies.
    status = result.get("status")
    if status == "SUCCEEDED" and not retain_worktree:
        remove_worktree(repo_root, run_id)
    if status in {"SUCCEEDED", "FAILED", "CANCELED"}:
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
