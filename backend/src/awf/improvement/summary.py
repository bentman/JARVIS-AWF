"""Summary generation and next action derivation for AWF Improvement Proposals (ADR-0027)."""

from typing import Any


def derive_scope_classification(diff_stats: list[dict[str, Any]]) -> str:
    """Classify improvement scope as 'localized' or 'broad'."""
    file_count = len(diff_stats)
    total_delta = sum(item.get("additions", 0) + item.get("deletions", 0) for item in diff_stats)
    if file_count <= 3 and total_delta <= 100:
        return "localized"
    return "broad"


def generate_human_summary(
    proposal: dict[str, Any],
    diff_stats: list[dict[str, Any]],
    verdict_passed: bool | None = None,
) -> str:
    """Generate a readable, natural-language explanation sentence for the proposal."""
    status = proposal.get("status", "draft")
    if status == "merged":
        target = proposal.get("target_branch") or "target branch"
        return f"Proposal merged into {target}."
    if status == "rejected":
        return "Proposal was rejected and closed."
    if status == "abandoned":
        return "Proposal was abandoned."

    file_count = len(diff_stats)
    total_adds = sum(item.get("additions", 0) for item in diff_stats)
    total_dels = sum(item.get("deletions", 0) for item in diff_stats)

    file_label = f"{file_count} file" if file_count == 1 else f"{file_count} files"
    delta_label = f"(+{total_adds} / -{total_dels} lines)"

    if file_count == 1 and diff_stats:
        location = f" in {diff_stats[0]['path']}"
    elif file_count > 1:
        top_dirs = sorted({p["path"].split("/")[0] for p in diff_stats if "/" in p["path"]})
        if top_dirs:
            location = f" across {', '.join(top_dirs[:2])}"
        else:
            location = ""
    else:
        location = ""

    validation_state = ""
    if verdict_passed is True or proposal.get("verdict_artifact_id"):
        validation_state = " Validation passed."
    elif verdict_passed is False:
        validation_state = " Validation failed."

    summary_note = proposal.get("summary") or ""
    if summary_note and not summary_note.startswith("Improvement from run"):
        note_text = f": {summary_note}."
    else:
        note_text = "."

    next_prompt = ""
    if status == "ready_for_review":
        next_prompt = " Proposal is ready for review."
    elif status == "draft":
        next_prompt = " Proposal is in draft."

    return f"{file_label} changed {delta_label}{location}{note_text}{validation_state}{next_prompt}".strip()


def derive_safety_assessment(
    proposal: dict[str, Any],
    diff_stats: list[dict[str, Any]],
    verdict_passed: bool | None = None,
) -> str:
    """Explain why the proposal is safe to consider (ADR-0027 requirement)."""
    status = proposal.get("status", "draft")
    if status == "merged":
        return "Merged safely via authorized operator approval. Target branch updated, candidate worktree cleaned up."
    if status == "rejected":
        return "Proposal rejected. No modifications were merged into the repository."

    scope = derive_scope_classification(diff_stats)
    file_count = len(diff_stats)
    total_delta = sum(item.get("additions", 0) + item.get("deletions", 0) for item in diff_stats)

    parts = []
    if scope == "localized":
        parts.append(
            f"Localized change ({file_count} {'file' if file_count == 1 else 'files'}, {total_delta} lines changed)."
        )
    else:
        parts.append(f"Broad change ({file_count} files, {total_delta} lines changed).")

    parts.append("Isolated in worktree sandbox without modifying main branch.")

    verdict_id = proposal.get("verdict_artifact_id")
    if verdict_passed is True or verdict_id:
        parts.append(f"Validation passed all gate checks (verdict: {verdict_id or 'verified'}).")
    else:
        parts.append("Awaiting verification gate pass.")

    digest = proposal.get("diff_digest")
    if digest:
        parts.append(f"Cryptographically pinned to diff digest {digest[:18]}...")

    parts.append("Protected by R2 approval gate requiring human operator authorization before merge.")
    return " ".join(parts)


def generate_proposal_review_narrative(
    proposal: dict[str, Any],
    diff_stats: list[dict[str, Any]],
    verdict_passed: bool | None = None,
) -> dict[str, Any]:
    """Generate the structured 5-point operator review model required by ADR-0027."""
    human_summary = generate_human_summary(proposal, diff_stats, verdict_passed=verdict_passed)
    scope = derive_scope_classification(diff_stats)
    safety = derive_safety_assessment(proposal, diff_stats, verdict_passed=verdict_passed)
    next_act = derive_next_action(proposal)

    file_paths = [f.get("path", "") for f in diff_stats if f.get("path")]
    verdict_id = proposal.get("verdict_artifact_id")
    val_status = (
        "PASSED" if (verdict_passed is True or verdict_id) else ("FAILED" if verdict_passed is False else "PENDING")
    )
    val_narrative = (
        f"PASSED — All deterministic verification checks and automated tests passed (verdict: {verdict_id or 'verified'})."
        if val_status == "PASSED"
        else (
            f"FAILED — Validation did not pass all checks (verdict: {verdict_id})."
            if val_status == "FAILED"
            else "PENDING — Awaiting verification verdict."
        )
    )

    return {
        "what_changed": human_summary,
        "where_changed": file_paths,
        "scope_classification": scope,
        "validation_passed": val_status == "PASSED",
        "validation_status": val_status,
        "validation_narrative": val_narrative,
        "verdict_artifact_id": verdict_id,
        "why_safe": safety,
        "next_action": next_act,
    }


def derive_next_action(proposal: dict[str, Any]) -> dict[str, str]:
    """Derive the explicit operator-visible next step for an improvement proposal."""
    status = proposal.get("status", "draft")
    imp_id = proposal.get("improvement_id", "")
    approval = proposal.get("approval")

    # If merge approval is requested or in progress
    if approval is not None:
        appr_status = approval.get("status")
        appr_id = approval.get("approval_id", "")
        if appr_status == "pending":
            return {
                "action": "approve_merge",
                "label": "Approve merge",
                "command": f"awf approve {appr_id}",
                "description": f"Approve the R2 merge gate for proposal {imp_id}.",
            }
        if appr_status == "approved":
            return {
                "action": "merge",
                "label": "Merge improvement",
                "command": f"awf improvement merge {imp_id} {appr_id}",
                "description": "Execute merge into target branch and close candidate worktree.",
            }
        if appr_status == "rejected":
            return {
                "action": "reject",
                "label": "Reject proposal",
                "command": f"awf improvement reject {imp_id}",
                "description": "Merge approval was rejected. Close proposal and discard worktree.",
            }

    if status == "ready_for_review":
        return {
            "action": "request_merge",
            "label": "Request merge approval",
            "command": f"awf improvement request-merge {imp_id}",
            "description": "Request human merge approval for this proposal.",
        }

    if status == "draft":
        verdict_id = proposal.get("verdict_artifact_id") or "<verdict-id>"
        return {
            "action": "mark_ready",
            "label": "Mark proposal ready for review",
            "command": f"awf improvement mark-ready {imp_id} {verdict_id}",
            "description": "Verify validation verdict and advance proposal to ready_for_review.",
        }

    if status == "merged":
        return {
            "action": "none",
            "label": "Proposal merged",
            "command": "",
            "description": "This improvement has been merged successfully into the target branch.",
        }

    if status == "rejected":
        return {
            "action": "none",
            "label": "Proposal rejected",
            "command": "",
            "description": "This improvement proposal has been rejected and closed.",
        }

    return {
        "action": "review",
        "label": "Review proposal",
        "command": f"awf improvement show {imp_id}",
        "description": "Inspect proposal diff and validation details.",
    }
