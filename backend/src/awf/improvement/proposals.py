"""Durable Improvement Proposal operations (ADR-0022)."""

import hashlib
import json
import sqlite3
from pathlib import Path

from awf.clock import utc_now_rfc3339
from awf.engine.run import create_step
from awf.events.writer import write_event
from awf.ids import uuid7
from awf.improvement.diff import (
    changed_paths,
    current_branch,
    diff_bytes,
    diff_digest,
    git_text,
    merge_base,
    parse_patch_diff_previews,
    write_patch_artifact,
)
from awf.improvement.summary import (
    derive_next_action,
    derive_safety_assessment,
    derive_scope_classification,
    generate_human_summary,
    generate_proposal_review_narrative,
)
from awf.isolation.worktree import branch_name, current_head, merge_branch, remove_worktree, worktree_path
from awf.paths import REPO_ROOT, artifacts_dir

MERGE_NODE_ID = "improvement.merge"


class ImprovementProposalError(RuntimeError):
    pass


def _event(
    conn: sqlite3.Connection, improvement_id: str, event_type: str, payload: dict, *, actor: str = "awf"
) -> None:
    conn.execute(
        "INSERT INTO improvement_proposal_events "
        "(event_id, improvement_id, event_type, occurred_at, actor, payload_json) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (uuid7(), improvement_id, event_type, utc_now_rfc3339(), actor, json.dumps(payload, sort_keys=True)),
    )
    conn.commit()


def _proposal_row(conn: sqlite3.Connection, improvement_id: str) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM improvement_proposals WHERE improvement_id = ?", (improvement_id,)).fetchone()
    if row is None:
        raise ImprovementProposalError(f"no such improvement proposal: {improvement_id}")
    return row


def _latest_step_id(conn: sqlite3.Connection, run_id: str) -> str:
    row = conn.execute(
        "SELECT step_id FROM steps WHERE run_id = ? ORDER BY started_at DESC, step_id DESC LIMIT 1",
        (run_id,),
    ).fetchone()
    if row is None:
        raise ImprovementProposalError(f"run {run_id} has no steps to attach improvement artifacts")
    return row["step_id"]


def _merge_step_id(run_id: str, improvement_id: str) -> str:
    return f"{run_id}:improvement-merge:{improvement_id}"


def _merge_action_payload(row: sqlite3.Row) -> dict:
    return {
        "kind": "improvement_merge",
        "improvement_id": row["improvement_id"],
        "run_id": row["run_id"],
        "target_branch": row["target_branch"],
        "base_commit": row["base_commit"],
        "candidate_branch": row["candidate_branch"],
        "candidate_commit": row["candidate_commit"],
        "diff_digest": row["diff_digest"],
        "verdict_artifact_id": row["verdict_artifact_id"],
        "validation_artifact_ids": json.loads(row["validation_artifact_ids_json"]),
    }


def merge_action_digest(row: sqlite3.Row) -> str:
    payload = json.dumps(_merge_action_payload(row), sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _serialize(row: sqlite3.Row, conn: sqlite3.Connection, repo_root: Path | None = None) -> dict:
    data = dict(row)
    data["changed_paths"] = json.loads(data.pop("changed_paths_json"))
    data["validation_artifact_ids"] = json.loads(data.pop("validation_artifact_ids_json"))
    data["events"] = [
        dict(event)
        for event in conn.execute(
            "SELECT * FROM improvement_proposal_events WHERE improvement_id = ? ORDER BY occurred_at, event_id",
            (row["improvement_id"],),
        ).fetchall()
    ]
    approval = conn.execute(
        "SELECT * FROM approvals WHERE step_id = ? ORDER BY requested_at DESC LIMIT 1",
        (_merge_step_id(row["run_id"], row["improvement_id"]),),
    ).fetchone()
    data["approval"] = dict(approval) if approval is not None else None
    data["merge_action_digest"] = merge_action_digest(row)

    # Extract diff statistics and compact preview lines
    diff_stats: list[dict] = []
    root = repo_root or REPO_ROOT
    patch_art_id = data.get("patch_artifact_id")
    if patch_art_id:
        art_row = conn.execute("SELECT relative_path FROM artifacts WHERE artifact_id = ?", (patch_art_id,)).fetchone()
        if art_row is not None:
            patch_file = artifacts_dir(root) / art_row["relative_path"]
            if patch_file.is_file():
                try:
                    patch_text = patch_file.read_text(encoding="utf-8", errors="replace")
                    diff_stats = parse_patch_diff_previews(patch_text)
                except Exception:
                    diff_stats = []

    if not diff_stats:
        for p in data["changed_paths"]:
            added_str = str(p.get("added", "0"))
            deleted_str = str(p.get("deleted", "0"))
            is_bin = added_str == "-" or deleted_str == "-"
            diff_stats.append(
                {
                    "path": p.get("path", ""),
                    "additions": int(added_str) if not is_bin and added_str.isdigit() else 0,
                    "deletions": int(deleted_str) if not is_bin and deleted_str.isdigit() else 0,
                    "is_binary": is_bin,
                    "preview_lines": [],
                    "truncated": False,
                    "total_lines": 0,
                }
            )

    data["diff_stats"] = diff_stats
    data["scope_classification"] = derive_scope_classification(diff_stats)
    data["human_summary"] = generate_human_summary(data, diff_stats)
    data["safety_assessment"] = derive_safety_assessment(data, diff_stats)
    data["proposal_review"] = generate_proposal_review_narrative(data, diff_stats)
    data["next_action"] = derive_next_action(data)
    return data


def prepare(repo_root: Path, conn: sqlite3.Connection, *, run_id: str, summary: str | None = None) -> dict:
    run = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    if run is None:
        raise ImprovementProposalError(f"no such run: {run_id}")
    if run["status"] != "SUCCEEDED":
        raise ImprovementProposalError(f"run {run_id} is not SUCCEEDED (status={run['status']})")

    worktree = worktree_path(repo_root, run_id)
    if not worktree.is_dir():
        raise ImprovementProposalError(f"run {run_id} worktree is not available at {worktree}")

    target_branch = current_branch(repo_root)
    if not target_branch:
        raise ImprovementProposalError("target repository is in detached HEAD state")
    candidate_branch = current_branch(worktree) or branch_name(run_id)
    candidate_commit = current_head(worktree)
    base_commit = merge_base(repo_root, target_branch, candidate_commit)
    patch = diff_bytes(repo_root, base_commit, candidate_commit)
    if not patch:
        raise ImprovementProposalError("candidate diff is empty")
    digest = diff_digest(patch)
    paths = changed_paths(repo_root, base_commit, candidate_commit)
    step_id = _latest_step_id(conn, run_id)
    patch_artifact_id = write_patch_artifact(
        conn, artifacts_root=artifacts_dir(repo_root), run_id=run_id, step_id=step_id, payload=patch
    )
    now = utc_now_rfc3339()
    existing = conn.execute("SELECT improvement_id FROM improvement_proposals WHERE run_id = ?", (run_id,)).fetchone()
    if existing is None:
        improvement_id = uuid7()
        conn.execute(
            "INSERT INTO improvement_proposals "
            "(improvement_id, run_id, target_repo, target_branch, base_commit, candidate_branch, candidate_commit, "
            "diff_digest, patch_artifact_id, status, summary, changed_paths_json, verdict_artifact_id, "
            "validation_artifact_ids_json, created_at, updated_at) "
            "VALUES (?, ?, '.', ?, ?, ?, ?, ?, ?, 'draft', ?, ?, NULL, '[]', ?, ?)",
            (
                improvement_id,
                run_id,
                target_branch,
                base_commit,
                candidate_branch,
                candidate_commit,
                digest,
                patch_artifact_id,
                summary or f"Improvement from run {run_id}",
                json.dumps(paths, sort_keys=True),
                now,
                now,
            ),
        )
        conn.commit()
        _event(conn, improvement_id, "created", {"diff_digest": digest, "patch_artifact_id": patch_artifact_id})
    else:
        improvement_id = existing["improvement_id"]
        conn.execute(
            "UPDATE improvement_proposals SET target_branch = ?, base_commit = ?, candidate_branch = ?, "
            "candidate_commit = ?, diff_digest = ?, patch_artifact_id = ?, status = 'draft', summary = ?, "
            "changed_paths_json = ?, verdict_artifact_id = NULL, validation_artifact_ids_json = '[]', updated_at = ? "
            "WHERE improvement_id = ?",
            (
                target_branch,
                base_commit,
                candidate_branch,
                candidate_commit,
                digest,
                patch_artifact_id,
                summary or f"Improvement from run {run_id}",
                json.dumps(paths, sort_keys=True),
                now,
                improvement_id,
            ),
        )
        conn.commit()
        _event(conn, improvement_id, "updated", {"diff_digest": digest, "patch_artifact_id": patch_artifact_id})
    return get(conn, improvement_id=improvement_id)


def get(conn: sqlite3.Connection, *, improvement_id: str) -> dict:
    return _serialize(_proposal_row(conn, improvement_id), conn)


def list_(conn: sqlite3.Connection, *, status: str | None = None, run_id: str | None = None) -> list[dict]:
    clauses = []
    params: list[object] = []
    if status is not None:
        clauses.append("status = ?")
        params.append(status)
    if run_id is not None:
        clauses.append("run_id = ?")
        params.append(run_id)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        f"SELECT * FROM improvement_proposals {where} ORDER BY created_at, improvement_id", params
    ).fetchall()
    return [_serialize(row, conn) for row in rows]


def _verdict_passed(repo_root: Path, conn: sqlite3.Connection, *, run_id: str, artifact_id: str) -> bool:
    row = conn.execute("SELECT * FROM artifacts WHERE artifact_id = ?", (artifact_id,)).fetchone()
    if row is None:
        raise ImprovementProposalError(f"no such verdict artifact: {artifact_id}")
    if row["run_id"] != run_id or row["artifact_type"] != "verdict":
        raise ImprovementProposalError(f"artifact {artifact_id} is not this run's verdict")
    payload = (artifacts_dir(repo_root) / row["relative_path"]).read_text(encoding="utf-8")
    try:
        verdict = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ImprovementProposalError(f"verdict artifact {artifact_id} is not JSON") from exc
    return bool(verdict.get("passed"))


def mark_ready(
    repo_root: Path,
    conn: sqlite3.Connection,
    *,
    improvement_id: str,
    verdict_artifact_id: str,
    validation_artifact_ids: list[str],
) -> dict:
    row = _proposal_row(conn, improvement_id)
    if row["status"] not in {"draft", "ready_for_review"}:
        raise ImprovementProposalError(f"proposal {improvement_id} cannot be marked ready from {row['status']}")
    if not _verdict_passed(repo_root, conn, run_id=row["run_id"], artifact_id=verdict_artifact_id):
        raise ImprovementProposalError(f"verdict artifact {verdict_artifact_id} did not pass")
    now = utc_now_rfc3339()
    conn.execute(
        "UPDATE improvement_proposals SET status = 'ready_for_review', verdict_artifact_id = ?, "
        "validation_artifact_ids_json = ?, updated_at = ? WHERE improvement_id = ?",
        (verdict_artifact_id, json.dumps(validation_artifact_ids, sort_keys=True), now, improvement_id),
    )
    conn.commit()
    _event(
        conn,
        improvement_id,
        "ready_for_review",
        {"verdict_artifact_id": verdict_artifact_id, "validation_artifact_ids": validation_artifact_ids},
    )
    return get(conn, improvement_id=improvement_id)


def request_merge(repo_root: Path, conn: sqlite3.Connection, *, improvement_id: str) -> dict:
    row = _proposal_row(conn, improvement_id)
    if row["status"] != "ready_for_review":
        raise ImprovementProposalError(f"proposal {improvement_id} is not ready_for_review (status={row['status']})")
    _recheck_identities(repo_root, row)
    step_id = _merge_step_id(row["run_id"], improvement_id)
    create_step(
        conn,
        step_id=step_id,
        run_id=row["run_id"],
        node_id=MERGE_NODE_ID,
        input_json=json.dumps(_merge_action_payload(row)),
    )
    digest = merge_action_digest(row)
    existing = conn.execute("SELECT * FROM approvals WHERE step_id = ?", (step_id,)).fetchone()
    if existing is not None:
        if existing["action_digest"] != digest:
            raise ImprovementProposalError("existing merge approval digest does not match current proposal")
        return {"approval": dict(existing), "proposal": get(conn, improvement_id=improvement_id)}

    approval_id = uuid7()
    now = utc_now_rfc3339()
    conn.execute(
        "INSERT INTO approvals (approval_id, run_id, step_id, action_digest, status, requested_at, risk_class) "
        "VALUES (?, ?, ?, ?, 'pending', ?, 'R2')",
        (approval_id, row["run_id"], step_id, digest, now),
    )
    conn.execute("UPDATE steps SET status = 'WAITING_APPROVAL', started_at = ? WHERE step_id = ?", (now, step_id))
    conn.commit()
    write_event(
        conn,
        run_id=row["run_id"],
        step_id=step_id,
        new_status="WAITING_APPROVAL",
        actor="awf",
        reason_code="improvement_merge_approval_requested",
        payload_json=json.dumps(
            {"approval_id": approval_id, "improvement_id": improvement_id, "merge_action_digest": digest}
        ),
    )
    _event(conn, improvement_id, "merge_requested", {"approval_id": approval_id, "merge_action_digest": digest})
    approval = conn.execute("SELECT * FROM approvals WHERE approval_id = ?", (approval_id,)).fetchone()
    return {"approval": dict(approval), "proposal": get(conn, improvement_id=improvement_id)}


def _recheck_identities(repo_root: Path, row: sqlite3.Row) -> None:
    worktree = worktree_path(repo_root, row["run_id"])
    if not worktree.is_dir():
        raise ImprovementProposalError(f"candidate worktree is not available at {worktree}")
    target_head = git_text(["rev-parse", row["target_branch"]], repo_root)
    if target_head != row["base_commit"]:
        raise ImprovementProposalError("target branch moved since proposal review")
    candidate_commit = current_head(worktree)
    if candidate_commit != row["candidate_commit"]:
        raise ImprovementProposalError("candidate commit changed since proposal review")
    patch = diff_bytes(repo_root, row["base_commit"], row["candidate_commit"])
    if diff_digest(patch) != row["diff_digest"]:
        raise ImprovementProposalError("candidate diff digest changed since proposal review")
    dirty = git_text(["status", "--porcelain"], repo_root)
    if dirty:
        raise ImprovementProposalError("target repository has uncommitted changes")


def merge(repo_root: Path, conn: sqlite3.Connection, *, improvement_id: str, approval_id: str) -> dict:
    row = _proposal_row(conn, improvement_id)
    approval = conn.execute("SELECT * FROM approvals WHERE approval_id = ?", (approval_id,)).fetchone()
    if approval is None:
        raise ImprovementProposalError(f"no such approval: {approval_id}")
    if approval["step_id"] != _merge_step_id(row["run_id"], improvement_id):
        raise ImprovementProposalError(f"approval {approval_id} is not for improvement {improvement_id}")
    if approval["status"] != "approved":
        raise ImprovementProposalError(f"approval {approval_id} is not approved (status={approval['status']})")
    if approval["action_digest"] != merge_action_digest(row):
        raise ImprovementProposalError("approved merge action digest does not match current proposal")
    _recheck_identities(repo_root, row)
    try:
        merge_branch(repo_root, row["candidate_branch"], message=f"Merge improvement {improvement_id}")
    except Exception as exc:
        _event(conn, improvement_id, "merge_failed", {"error": str(exc)})
        raise ImprovementProposalError(str(exc)) from exc
    merge_commit = git_text(["rev-parse", "HEAD"], repo_root)
    now = utc_now_rfc3339()
    conn.execute(
        "UPDATE improvement_proposals SET status = 'merged', merge_commit = ?, decided_at = ?, closed_at = ?, updated_at = ? "
        "WHERE improvement_id = ?",
        (merge_commit, now, now, now, improvement_id),
    )
    conn.execute(
        "UPDATE steps SET status = 'SUCCEEDED', output_json = ?, ended_at = ? WHERE step_id = ?",
        (
            json.dumps({"merged": True, "merge_commit": merge_commit, "improvement_id": improvement_id}),
            now,
            approval["step_id"],
        ),
    )
    conn.commit()
    _event(conn, improvement_id, "merged", {"approval_id": approval_id, "merge_commit": merge_commit})
    remove_worktree(repo_root, row["run_id"])
    return get(conn, improvement_id=improvement_id)


def reject(repo_root: Path, conn: sqlite3.Connection, *, improvement_id: str, reason: str | None = None) -> dict:
    row = _proposal_row(conn, improvement_id)
    if row["status"] in {"merged", "rejected", "abandoned"}:
        raise ImprovementProposalError(f"proposal {improvement_id} is already closed (status={row['status']})")
    now = utc_now_rfc3339()
    conn.execute(
        "UPDATE improvement_proposals SET status = 'rejected', decided_at = ?, closed_at = ?, updated_at = ? "
        "WHERE improvement_id = ?",
        (now, now, now, improvement_id),
    )
    conn.commit()
    _event(conn, improvement_id, "rejected", {"reason": reason})
    remove_worktree(repo_root, row["run_id"])
    return get(conn, improvement_id=improvement_id)
