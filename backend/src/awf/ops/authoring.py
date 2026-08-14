"""authoring operation implementations."""

import hashlib
import sqlite3
from pathlib import Path

from awf.authoring import workflow as workflow_authoring
from awf.ops.registry import op_registry_publish
from awf.ops.shared import CoreOpError


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
    verification = None
    if proposal["kind"] == "workflows":
        try:
            verification = workflow_authoring.verify_workflow_proposal(repo_root, conn, proposal_id=proposal_id)
        except workflow_authoring.ProposalError as exc:
            raise CoreOpError(str(exc)) from exc
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
    return {"proposal": marked, "published": published, "verification": verification}


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


__all__ = (
    "op_proposal_get",
    "op_proposal_publish",
    "op_proposal_reject",
    "op_proposal_update",
    "op_workflow_author_draft",
)
