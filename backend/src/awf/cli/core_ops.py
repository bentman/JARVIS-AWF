"""Core operations shared by the `awf` CLI (Section 16.1) and the
`awf serve --stdio` JSON-RPC endpoint (Section 16.3).

The protocol adds no authority (Section 16.3): both surfaces call exactly
these functions, so a mutation made over JSON-RPC passes through the same
Capability Guard / durability / worktree-commit paths as the CLI.
"""

import hashlib
import shlex
import sqlite3
import subprocess
from pathlib import Path

import yaml

from awf.adapters.antigravity_cli import invoke as antigravity_invoke
from awf.adapters.claude_code import invoke as claude_code_invoke
from awf.adapters.codex_cli import invoke as codex_invoke
from awf.adapters.copilot_cli import invoke as copilot_invoke
from awf.clock import utc_now_rfc3339
from awf.engine.recovery import scan_incomplete_runs
from awf.engine.run import create_run
from awf.envfile import get_env_value
from awf.gates.gate_node import make_trifecta_gate_executor
from awf.ids import uuid7
from awf.isolation.scratch import create_scratch_dir, remove_scratch_dir, scratch_path
from awf.isolation.worktree import create_worktree, remove_worktree, worktree_path
from awf.registry.capability_record import parse_capability_record
from awf.registry.model_profile import load_model_profile, parse_model_profile
from awf.registry.resolve import CONFIG_ROOT, DATA_ROOT, resolve_registry_object
from awf.secrets.store import list_secret_names, set_secret
from awf.workflow.approval import make_approval_node_executor
from awf.workflow.definition import load_workflow, parse_workflow
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
}


class CoreOpError(RuntimeError):
    pass


def _artifacts_root(repo_root: Path) -> Path:
    return repo_root / "data" / "artifacts"


def _make_check_fn(node: dict, worktree: Path):
    command = node.get("checkCommand")
    if not command:
        raise CoreOpError(f"gate node '{node['id']}' has no checkCommand")

    def check_fn() -> bool:
        result = subprocess.run(shlex.split(command), cwd=worktree, capture_output=True, text=True)
        return result.returncode == 0

    return check_fn


def _resolve_review_profile(node: dict, repo_root: Path):
    # A gate node MAY declare `reviewProfile: name@version` (a `purpose:
    # judge` Model Profile, Section 11) to add a real LLM-driven review
    # Finding, routed through the Model Gateway, alongside the deterministic
    # check - the Verifier's other, previously-unbuilt obligation half.
    review_ref = node.get("reviewProfile")
    if not review_ref:
        return None, None
    name, _, version = review_ref.partition("@")
    path, _source = resolve_registry_object(repo_root, "model-profiles", name, version)
    profile = load_model_profile(path)
    try:
        secret_key = get_env_value(repo_root / ".env", "AWF_SECRET_KEY").encode("ascii")
    except (FileNotFoundError, KeyError):
        secret_key = None
    return profile, secret_key


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
                child_workflow, worktree, artifacts_root, repo_root, child_scratch_dir
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


def _build_node_executors(
    workflow, worktree: Path, artifacts_root: Path, repo_root: Path, run_scratch_dir: Path
) -> dict:
    run_child = _make_run_child(worktree, artifacts_root, repo_root)
    executors = {
        "agent": make_agent_node_executor(ADAPTER_REGISTRY, worktree, repo_root),
        "activity": make_activity_node_executor(),
        "approval": make_approval_node_executor(),
        "subworkflow": make_subworkflow_node_executor(run_child),
        "map": make_map_node_executor(run_child),
        "loop": make_loop_node_executor(run_child),
    }
    for node in workflow.nodes:
        if node["type"] == "gate":
            # A node MAY declare `tier: high-risk` (Section 12.2's trigger
            # list still has to be checked by the caller/workflow author -
            # nothing here infers it automatically) to reach the full
            # Trifecta Adversary pass instead of Builder+Verifier only.
            review_profile, review_secret_key = _resolve_review_profile(node, repo_root)
            executors["gate"] = make_trifecta_gate_executor(
                check_fn=_make_check_fn(node, worktree),
                check_summary=node.get("check", node["id"]),
                artifacts_root=artifacts_root,
                tier=node.get("tier", "default"),
                cache_sandbox_dir=run_scratch_dir,
                guard_bypassed=node.get("guardBypassed", False),
                review_profile=review_profile,
                review_secret_key=review_secret_key,
            )
        elif node["type"] == "handoff":
            executors["handoff"] = make_handoff_node_executor(ADAPTER_REGISTRY, worktree)
    return executors


def _resolve_workflow(repo_root: Path, workflow_ref: str):
    name, _, version = workflow_ref.partition("@")
    if not version:
        raise CoreOpError(f"workflow ref must be 'name@version', got: {workflow_ref!r}")
    path, _source = resolve_registry_object(repo_root, "workflows", name, version)
    return load_workflow(path)


def _cleanup_run_workspace(repo_root: Path, run_id: str, result: dict) -> None:
    # Cache state is ephemeral by design (Section 7/10.4) - reclaim it once
    # a Run reaches a terminal state. FAILED keeps its worktree/scratch dir
    # around for post-mortem inspection; only SUCCEEDED is cleaned up here.
    if result.get("status") == "SUCCEEDED":
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


def op_run_start(repo_root: Path, conn: sqlite3.Connection, *, workflow_ref: str, input_data: dict) -> dict:
    import json

    workflow = _resolve_workflow(repo_root, workflow_ref)
    run_id = uuid7()
    create_run(conn, run_id=run_id, workflow_ref=workflow.ref, input_json=json.dumps(input_data))

    worktree = create_worktree(repo_root, run_id)
    run_scratch_dir = create_scratch_dir(repo_root, run_id)
    node_executors = _build_node_executors(workflow, worktree, _artifacts_root(repo_root), repo_root, run_scratch_dir)

    result = _run_workflow_safely(conn, run_id=run_id, workflow=workflow, node_executors=node_executors)
    _cleanup_run_workspace(repo_root, run_id, result)
    return {"run_id": run_id, **result}


def op_run_status(conn: sqlite3.Connection, *, run_id: str) -> dict:
    run_row = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    if run_row is None:
        raise CoreOpError(f"no such run: {run_id}")
    steps = conn.execute(
        "SELECT * FROM steps WHERE run_id = ? ORDER BY started_at", (run_id,)
    ).fetchall()
    return {**dict(run_row), "steps": [dict(row) for row in steps]}


def op_run_list(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT run_id, workflow_ref, status, created_at, updated_at FROM runs ORDER BY created_at"
    ).fetchall()
    return [dict(row) for row in rows]


def op_run_resume(repo_root: Path, conn: sqlite3.Connection) -> list[dict]:
    results = []
    for run_id in scan_incomplete_runs(conn):
        run_row = conn.execute("SELECT workflow_ref FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        workflow = _resolve_workflow(repo_root, run_row["workflow_ref"])
        worktree = worktree_path(repo_root, run_id)
        run_scratch_dir = scratch_path(repo_root, run_id)
        node_executors = _build_node_executors(
            workflow, worktree, _artifacts_root(repo_root), repo_root, run_scratch_dir
        )
        result = _run_workflow_safely(conn, run_id=run_id, workflow=workflow, node_executors=node_executors)
        _cleanup_run_workspace(repo_root, run_id, result)
        results.append({"run_id": run_id, **result})
    return results


def op_approval_list(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM approvals WHERE status = 'pending' ORDER BY requested_at"
    ).fetchall()
    return [dict(row) for row in rows]


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
        if risk_class is None:
            raise CoreOpError("channel='voice' requires risk_class to evaluate the voice-approval rule")
        from awf.gates.voice_approval import attempt_voice_approval

        decision = attempt_voice_approval(
            conn, approval_id=approval_id, risk_class=risk_class, voice_confirmed=True
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
    rows = conn.execute(
        "SELECT * FROM artifacts WHERE run_id = ? ORDER BY created_at", (run_id,)
    ).fetchall()
    return [dict(row) for row in rows]


def op_artifact_read(conn: sqlite3.Connection, *, artifact_id: str, artifacts_root: Path) -> dict:
    row = conn.execute("SELECT * FROM artifacts WHERE artifact_id = ?", (artifact_id,)).fetchone()
    if row is None:
        raise CoreOpError(f"no such artifact: {artifact_id}")
    content = (artifacts_root / row["relative_path"]).read_text()
    return {**dict(row), "content": content}


def op_registry_list(repo_root: Path, *, kind: str) -> list[dict]:
    # Skills are published as <name>/<version>/SKILL.md (Section 9.3), not
    # <name>/<version>.yaml like every other kind.
    is_skill = kind == "skills"
    results = []
    for source_name, root in (("data", repo_root / DATA_ROOT), ("config", repo_root / CONFIG_ROOT)):
        kind_dir = root / kind
        if not kind_dir.is_dir():
            continue
        for name_dir in sorted(p for p in kind_dir.iterdir() if p.is_dir()):
            if is_skill:
                versions = sorted(p.name for p in name_dir.iterdir() if (p / "SKILL.md").is_file())
            else:
                versions = sorted(p.stem for p in name_dir.glob("*.yaml"))
            for version in versions:
                results.append(
                    {"source": source_name, "kind": kind, "name": name_dir.name, "version": version}
                )
    return results


def op_registry_get(repo_root: Path, *, kind: str, name: str, version: str) -> dict:
    path, source = resolve_registry_object(repo_root, kind, name, version)
    return {"kind": kind, "name": name, "version": version, "source": source, "content": path.read_text()}


def op_registry_validate(path: Path) -> dict:
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict):
        raise CoreOpError(f"{path}: must be a YAML mapping")

    if raw.get("kind") == "Workflow":
        workflow = parse_workflow(raw)
        return {"kind": "Workflow", "ref": workflow.ref, "valid": True}
    if "identity" in raw and "risk_class" in raw:
        record = parse_capability_record(raw)
        return {"kind": "CapabilityRecord", "ref": record.ref, "valid": True}
    if "candidates" in raw and "privacy" in raw:
        parse_model_profile(raw)
        return {"kind": "ModelProfile", "valid": True}
    raise CoreOpError(f"{path}: unrecognized registry object shape")


def op_registry_publish(repo_root: Path, conn: sqlite3.Connection, *, path: Path) -> dict:
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict):
        raise CoreOpError(f"{path}: must be a YAML mapping")

    if raw.get("kind") == "Workflow":
        workflow = parse_workflow(raw)
        kind, name, version = "workflows", workflow.metadata.name, workflow.metadata.version
    elif "identity" in raw and "risk_class" in raw:
        record = parse_capability_record(raw)
        kind, name, version = "capabilities", record.identity.name, record.identity.version
    else:
        raise CoreOpError(
            f"{path}: registry publish only supports Workflow and Capability Record objects "
            "(kinds with self-describing name/version) in this phase"
        )

    payload = path.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    target_dir = repo_root / DATA_ROOT / kind / name
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / f"{version}.yaml"
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


def op_secret_set(repo_root: Path, conn: sqlite3.Connection, *, name: str, value: str) -> dict:
    key = get_env_value(repo_root / ".env", "AWF_SECRET_KEY").encode("ascii")
    set_secret(conn, name, value, key)
    return {"name": name, "status": "set"}


def op_secret_list_names(conn: sqlite3.Connection) -> list[str]:
    return list_secret_names(conn)
