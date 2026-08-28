"""improvement operation implementations."""

import sqlite3
from pathlib import Path

from awf.improvement import proposals as improvement_proposals
from awf.ops.shared import CoreOpError


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


def op_improvement_merge(repo_root: Path, conn: sqlite3.Connection, *, improvement_id: str, approval_id: str) -> dict:
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


__all__ = (
    "op_improvement_get",
    "op_improvement_list",
    "op_improvement_mark_ready",
    "op_improvement_merge",
    "op_improvement_prepare",
    "op_improvement_reject",
    "op_improvement_request_merge",
)
