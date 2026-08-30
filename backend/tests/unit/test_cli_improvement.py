"""Unit tests for CLI improvement proposal presentation (ADR-0027)."""

from awf.cli.main import (
    _format_approval_detail,
    _format_approvals,
    _format_improvement_list,
    _format_improvement_proposal,
    _format_outcome,
)


def test_format_improvement_proposal_basic():
    proposal = {
        "improvement_id": "imp-001",
        "status": "ready_for_review",
        "human_summary": "1 file changed (+10 / -2 lines) in backend/src/awf/ops/run.py. Validation passed. Ready for review.",
        "target_branch": "main",
        "base_commit": "abcdef123456",
        "candidate_commit": "fedcba654321",
        "diff_digest": "sha256:11223344",
        "verdict_artifact_id": "art-verdict-1",
        "safety_assessment": "Localized change (1 file, 12 lines changed). Isolated in worktree sandbox.",
        "diff_stats": [
            {
                "path": "backend/src/awf/ops/run.py",
                "additions": 10,
                "deletions": 2,
                "preview_lines": ["@@ -1,5 +1,6 @@", "+# new line"],
                "truncated": False,
            }
        ],
        "next_action": {
            "action": "request_merge",
            "label": "Request merge approval",
            "command": "awf improvement request-merge imp-001",
            "description": "Request human merge approval for this proposal.",
        },
    }
    formatted = _format_improvement_proposal(proposal)
    assert "AWF IMPROVEMENT PROPOSAL REVIEW: imp-001" in formatted
    assert "Status: READY_FOR_REVIEW [Localized]" in formatted
    assert "1. WHAT CHANGED:" in formatted
    assert "2. WHERE IT CHANGED:" in formatted
    assert "3. VALIDATION STATUS:\n  PASSED" in formatted
    assert "4. WHY IT IS SAFE TO CONSIDER:" in formatted
    assert "5. DIFF PREVIEW:" in formatted
    assert "backend/src/awf/ops/run.py (+10 / -2 lines)" in formatted
    assert "+# new line" in formatted
    assert "6. NEXT OPERATOR ACTION:\n  Request merge approval" in formatted
    assert "Command:   awf improvement request-merge imp-001" in formatted


def test_format_improvement_proposal_full_diff():
    proposal = {
        "improvement_id": "imp-002",
        "status": "draft",
        "summary": "Full diff test",
        "diff_digest": "sha256:aabb",
        "diff_stats": [{"path": "a.py", "additions": 1, "deletions": 0, "preview_lines": ["+1"]}],
    }
    raw = "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n+1"
    formatted = _format_improvement_proposal(proposal, full_diff=True, raw_patch=raw)
    assert "FULL PATCH:" in formatted
    assert "diff --git a/a.py b/a.py" in formatted


def test_format_improvement_list():
    proposals = [
        {
            "improvement_id": "imp-1",
            "status": "ready_for_review",
            "human_summary": "1 file changed in foo.py.",
            "next_action": {"command": "awf improvement request-merge imp-1"},
        }
    ]
    formatted = _format_improvement_list(proposals)
    assert "Improvement Proposals:" in formatted
    assert "- imp-1 [READY_FOR_REVIEW] 1 file changed in foo.py." in formatted
    assert "Next: awf improvement request-merge imp-1" in formatted


def test_format_outcome_includes_proposal():
    outcome = {
        "run_id": "run-100",
        "workflow_ref": "self-improvement@1.0.0",
        "status": "SUCCEEDED",
        "response_text": "Completed self improvement.",
        "proposal": {
            "improvement_id": "imp-999",
            "status": "ready_for_review",
            "human_summary": "1 file changed in main.py.",
            "safety_assessment": "Localized change bounded to worktree sandbox.",
            "verdict_artifact_id": "art-v-1",
            "diff_stats": [
                {
                    "path": "main.py",
                    "additions": 5,
                    "deletions": 0,
                    "preview_lines": ["@@ -1 +1,2 @@", "+new line"],
                }
            ],
            "next_action": {
                "label": "Request merge approval",
                "command": "awf improvement request-merge imp-999",
            },
        },
    }
    formatted = _format_outcome(outcome)
    assert "AWF IMPROVEMENT PROPOSAL REVIEW" in formatted
    assert "1. WHAT CHANGED:\n  1 file changed in main.py." in formatted
    assert "2. VALIDATION STATUS:\n  PASSED" in formatted
    assert "3. WHY IT IS SAFE TO CONSIDER:\n  Localized change" in formatted
    assert "4. CHANGED FILES & DIFF PREVIEW:" in formatted
    assert "main.py (+5 / -0 lines)" in formatted
    assert "+new line" in formatted
    assert "5. NEXT OPERATOR ACTION:\n  Request merge approval" in formatted


def test_format_approval_detail_improvement():
    detail = {
        "approval": {
            "approval_id": "appr-001",
            "status": "pending",
            "risk_class": "R2",
            "action_digest": "sha256:abcdef",
            "requested_at": "2026-08-30T12:00:00Z",
        },
        "preview": {
            "kind": "improvement_merge",
            "human_summary": "1 file changed in main.py.",
            "safety_assessment": "Localized change. Isolated in worktree sandbox.",
            "verdict_artifact_id": "art-v-1",
            "diff_stats": [
                {
                    "path": "main.py",
                    "additions": 3,
                    "deletions": 1,
                    "preview_lines": ["@@ -1,2 +1,4 @@", "+added"],
                }
            ],
            "proposal": {
                "human_summary": "1 file changed in main.py.",
                "safety_assessment": "Localized change. Isolated in worktree sandbox.",
                "verdict_artifact_id": "art-v-1",
                "diff_stats": [
                    {
                        "path": "main.py",
                        "additions": 3,
                        "deletions": 1,
                        "preview_lines": ["@@ -1,2 +1,4 @@", "+added"],
                    }
                ],
            },
        },
    }
    formatted = _format_approval_detail(detail)
    assert "AWF APPROVAL REVIEW: appr-001 [PENDING]" in formatted
    assert "Risk Class: R2" in formatted
    assert "1. WHAT IS BEING APPROVED:\n  1 file changed in main.py." in formatted
    assert "2. WHY IT IS SAFE TO APPROVE:\n  Localized change." in formatted
    assert "3. VALIDATION STATUS:\n  PASSED" in formatted
    assert "main.py (+3 / -1 lines)" in formatted
    assert "+added" in formatted
    assert "Approve: awf approve appr-001" in formatted


def test_format_approvals_list():
    approvals = [
        {
            "approval_id": "appr-001",
            "risk_class": "R2",
            "action_digest": "sha256:123",
            "preview": {
                "human_summary": "1 file changed in main.py.",
            },
        }
    ]
    formatted = _format_approvals(approvals)
    assert "Pending Approvals:" in formatted
    assert "- appr-001 [R2] 1 file changed in main.py." in formatted
    assert "Next: awf approval appr-001  (or: awf approve appr-001)" in formatted
