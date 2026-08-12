"""Workflow authoring proposal pipeline (ADR-0019)."""

import copy
import hashlib
import json
import sqlite3
from pathlib import Path

import jsonschema
import yaml

from awf.clock import utc_now_rfc3339
from awf.cognition.envelope import PromptEnvelope, PromptSegment
from awf.cognition.render import render_chat
from awf.gateway.client import complete_structured
from awf.ids import uuid7
from awf.paths import proposals_dir
from awf.registry.kinds import WORKFLOWS, version_names
from awf.registry.model_profile import load_model_profile
from awf.registry.resolve import CONFIG_ROOT, DATA_ROOT, resolve_registry_object
from awf.workflow.definition import parse_workflow

DEFAULT_AUTHOR_PROFILE = "resident-mind@1.0.0"
DEFAULT_DRAFT_VERSION = "0.1.0"

WORKFLOW_AUTHORING_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["summary", "workflow"],
    "properties": {
        "summary": {"type": "string", "minLength": 1},
        "workflow": {
            "type": "object",
            "additionalProperties": True,
            "required": ["apiVersion", "kind", "metadata", "spec"],
            "properties": {
                "apiVersion": {"const": "awf/v1"},
                "kind": {"const": "Workflow"},
                "metadata": {
                    "type": "object",
                    "additionalProperties": True,
                    "required": ["name", "version", "digest"],
                    "properties": {
                        "name": {"type": "string", "minLength": 1},
                        "version": {"type": "string", "minLength": 1},
                        "digest": {"type": "string", "minLength": 1},
                    },
                },
                "spec": {"type": "object"},
            },
        },
    },
}


class ProposalError(RuntimeError):
    pass


def _proposal_path(repo_root: Path, proposal_id: str, name: str, version: str) -> Path:
    return proposals_dir(repo_root) / "workflows" / proposal_id / name / f"{version}.yaml"


def _event(conn: sqlite3.Connection, proposal_id: str, event_type: str, payload: dict, *, actor: str = "operator") -> None:
    conn.execute(
        "INSERT INTO registry_proposal_events "
        "(event_id, proposal_id, event_type, occurred_at, actor, payload_json) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (uuid7(), proposal_id, event_type, utc_now_rfc3339(), actor, json.dumps(payload, sort_keys=True)),
    )


def _workflow_bytes(raw: dict) -> bytes:
    return yaml.safe_dump(raw, sort_keys=False).encode("utf-8")


def _set_workflow_metadata_digest(raw: dict) -> dict:
    normalized = copy.deepcopy(raw)
    metadata = normalized.setdefault("metadata", {})
    metadata["digest"] = ""
    digest = hashlib.sha256(_workflow_bytes(normalized)).hexdigest()
    normalized["metadata"]["digest"] = f"sha256:{digest}"
    return normalized


def _prepare_workflow(raw: dict, *, name: str | None, version: str | None) -> tuple[dict, bytes, str]:
    if not isinstance(raw, dict):
        raise ProposalError("generated workflow must be a mapping")
    normalized = copy.deepcopy(raw)
    metadata = normalized.setdefault("metadata", {})
    if name is not None:
        metadata["name"] = name
    if version is not None:
        metadata["version"] = version
    metadata.setdefault("version", DEFAULT_DRAFT_VERSION)
    normalized = _set_workflow_metadata_digest(normalized)
    parse_workflow(normalized)
    content = _workflow_bytes(normalized)
    return normalized, content, hashlib.sha256(content).hexdigest()


def _load_profile(repo_root: Path, profile_ref: str):
    name, sep, version = profile_ref.partition("@")
    if not sep or not name or not version:
        raise ProposalError(f"profile must be '<name>@<version>', got {profile_ref!r}")
    path, _source = resolve_registry_object(repo_root, "model-profiles", name, version)
    return load_model_profile(path)


def _registry_context(repo_root: Path) -> str:
    lines: list[str] = []
    for source, root in (("data", repo_root / DATA_ROOT), ("config", repo_root / CONFIG_ROOT)):
        workflows_dir = root / "workflows"
        if not workflows_dir.is_dir():
            continue
        for name_dir in sorted(path for path in workflows_dir.iterdir() if path.is_dir()):
            versions = ", ".join(version_names(name_dir, WORKFLOWS))
            if versions:
                lines.append(f"- {source}: {name_dir.name} ({versions})")
    return "\n".join(lines) if lines else "- no published workflows found"


def _authoring_envelope(*, objective: str, name: str | None, version: str | None, registry_context: str) -> PromptEnvelope:
    requested_identity = {
        "name": name or "choose a concise kebab-case workflow name",
        "version": version or DEFAULT_DRAFT_VERSION,
    }
    return PromptEnvelope(
        segments=(
            PromptSegment(
                authority="application",
                content_type="instruction",
                trusted=True,
                text=(
                    "Generate one AWF Workflow draft. Return only JSON matching the provided schema. "
                    "The workflow must use apiVersion awf/v1 and kind Workflow."
                ),
            ),
            PromptSegment(
                authority="contract",
                content_type="contract",
                trusted=True,
                text=(
                    "Workflow YAML requires metadata.name, metadata.version, metadata.digest, "
                    "spec.inputSchema, spec.outputSchema, spec.budgets, spec.nodes, and spec.outputs. "
                    "Use existing node shapes only: activity, agent, approval, gate, subworkflow, map, loop, handoff."
                ),
            ),
            PromptSegment(
                authority="retrieval",
                content_type="context",
                trusted=True,
                text=f"Published workflows:\n{registry_context}",
            ),
            PromptSegment(
                authority="user",
                content_type="input",
                trusted=False,
                text=f"Objective: {objective}\nRequested identity: {json.dumps(requested_identity, sort_keys=True)}",
            ),
        )
    )


def author_workflow_draft(
    repo_root: Path,
    conn: sqlite3.Connection,
    *,
    objective: str,
    name: str | None = None,
    version: str | None = None,
    profile_ref: str = DEFAULT_AUTHOR_PROFILE,
) -> dict:
    profile = _load_profile(repo_root, profile_ref)
    envelope = _authoring_envelope(
        objective=objective,
        name=name,
        version=version,
        registry_context=_registry_context(repo_root),
    )
    payload = complete_structured(
        profile,
        render_chat(envelope).messages,
        schema_name="awf_workflow_proposal",
        schema=WORKFLOW_AUTHORING_SCHEMA,
        conn=conn,
    )
    jsonschema.validate(instance=payload, schema=WORKFLOW_AUTHORING_SCHEMA)
    workflow_raw, content, draft_digest = _prepare_workflow(
        payload["workflow"], name=name, version=version or DEFAULT_DRAFT_VERSION
    )
    workflow = parse_workflow(workflow_raw)
    proposal_id = uuid7()
    path = _proposal_path(repo_root, proposal_id, workflow.metadata.name, workflow.metadata.version)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)

    now = utc_now_rfc3339()
    rel_path = path.relative_to(repo_root).as_posix()
    conn.execute(
        "INSERT INTO registry_proposals "
        "(proposal_id, kind, name, version, status, draft_digest, draft_path, summary, created_at, updated_at) "
        "VALUES (?, 'workflows', ?, ?, 'draft', ?, ?, ?, ?, ?)",
        (
            proposal_id,
            workflow.metadata.name,
            workflow.metadata.version,
            draft_digest,
            rel_path,
            payload["summary"],
            now,
            now,
        ),
    )
    _event(
        conn,
        proposal_id,
        "created",
        {"draft_digest": draft_digest, "path": rel_path, "profile_ref": profile_ref},
        actor="resident-mind",
    )
    conn.commit()
    return get_proposal(repo_root, conn, proposal_id=proposal_id)


def get_proposal(repo_root: Path, conn: sqlite3.Connection, *, proposal_id: str) -> dict:
    row = conn.execute("SELECT * FROM registry_proposals WHERE proposal_id = ?", (proposal_id,)).fetchone()
    if row is None:
        raise ProposalError(f"no such proposal: {proposal_id}")
    data = dict(row)
    path = repo_root / data["draft_path"]
    data["content"] = path.read_text(encoding="utf-8")
    data["events"] = [
        dict(event)
        for event in conn.execute(
            "SELECT * FROM registry_proposal_events WHERE proposal_id = ? ORDER BY occurred_at, event_id",
            (proposal_id,),
        ).fetchall()
    ]
    return data


def update_proposal(
    repo_root: Path,
    conn: sqlite3.Connection,
    *,
    proposal_id: str,
    content: str,
    summary: str | None = None,
) -> dict:
    current = get_proposal(repo_root, conn, proposal_id=proposal_id)
    if current["status"] != "draft":
        raise ProposalError(f"proposal {proposal_id} is not draft (status={current['status']})")
    raw = yaml.safe_load(content)
    workflow_raw, draft_content, draft_digest = _prepare_workflow(raw, name=None, version=None)
    workflow = parse_workflow(workflow_raw)
    path = _proposal_path(repo_root, proposal_id, workflow.metadata.name, workflow.metadata.version)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(draft_content)

    old_path = repo_root / current["draft_path"]
    if old_path != path and old_path.exists():
        old_path.unlink()

    now = utc_now_rfc3339()
    conn.execute(
        "UPDATE registry_proposals "
        "SET name = ?, version = ?, draft_digest = ?, draft_path = ?, summary = ?, updated_at = ? "
        "WHERE proposal_id = ?",
        (
            workflow.metadata.name,
            workflow.metadata.version,
            draft_digest,
            path.relative_to(repo_root).as_posix(),
            summary if summary is not None else current["summary"],
            now,
            proposal_id,
        ),
    )
    _event(conn, proposal_id, "updated", {"draft_digest": draft_digest, "path": path.relative_to(repo_root).as_posix()})
    conn.commit()
    return get_proposal(repo_root, conn, proposal_id=proposal_id)


def reject_proposal(
    repo_root: Path, conn: sqlite3.Connection, *, proposal_id: str, reason: str | None = None
) -> dict:
    current = get_proposal(repo_root, conn, proposal_id=proposal_id)
    if current["status"] != "draft":
        raise ProposalError(f"proposal {proposal_id} is not draft (status={current['status']})")
    now = utc_now_rfc3339()
    conn.execute(
        "UPDATE registry_proposals SET status = 'rejected', rejection_reason = ?, decided_at = ?, updated_at = ? "
        "WHERE proposal_id = ?",
        (reason, now, now, proposal_id),
    )
    _event(conn, proposal_id, "rejected", {"reason": reason})
    conn.commit()
    return get_proposal(repo_root, conn, proposal_id=proposal_id)


def verify_workflow_proposal(repo_root: Path, conn: sqlite3.Connection, *, proposal_id: str) -> dict:
    current = get_proposal(repo_root, conn, proposal_id=proposal_id)
    if current["status"] != "draft":
        raise ProposalError(f"proposal {proposal_id} is not draft (status={current['status']})")
    raw = yaml.safe_load(current["content"])
    if not isinstance(raw, dict):
        raise ProposalError("workflow proposal verifier expected a YAML mapping")
    workflow = parse_workflow(raw)
    if workflow.metadata.name != current["name"] or workflow.metadata.version != current["version"]:
        raise ProposalError(
            "workflow proposal verifier rejected draft identity mismatch: "
            f"{workflow.metadata.name}@{workflow.metadata.version} != {current['name']}@{current['version']}"
        )

    checked_capabilities = []
    for node in workflow.nodes:
        if node.get("type") != "activity" or not node.get("function"):
            continue
        capability = node.get("capability") or {"name": node["function"], "version": "1.0.0"}
        name = capability.get("name")
        version = capability.get("version")
        if not name or not version:
            raise ProposalError(f"workflow proposal verifier rejected activity node {node['id']}: invalid capability ref")
        try:
            resolve_registry_object(repo_root, "capabilities", name, version, conn=conn)
        except Exception as exc:
            raise ProposalError(
                f"workflow proposal verifier rejected activity node {node['id']}: {exc}"
            ) from exc
        checked_capabilities.append(f"{name}@{version}")

    result = {
        "verifier": "deterministic-workflow-proposal",
        "status": "passed",
        "checks": {
            "parse_workflow": True,
            "identity_matches_proposal": True,
            "activity_capabilities": checked_capabilities,
        },
    }
    _event(conn, proposal_id, "verified", result, actor="workflow-verifier")
    conn.commit()
    return result


def mark_published(
    repo_root: Path,
    conn: sqlite3.Connection,
    *,
    proposal_id: str,
    published_digest: str,
) -> dict:
    current = get_proposal(repo_root, conn, proposal_id=proposal_id)
    if current["status"] != "draft":
        raise ProposalError(f"proposal {proposal_id} is not draft (status={current['status']})")
    now = utc_now_rfc3339()
    conn.execute(
        "UPDATE registry_proposals "
        "SET status = 'published', published_digest = ?, decided_at = ?, updated_at = ? "
        "WHERE proposal_id = ?",
        (published_digest, now, now, proposal_id),
    )
    _event(conn, proposal_id, "published", {"published_digest": published_digest})
    conn.commit()
    return get_proposal(repo_root, conn, proposal_id=proposal_id)
