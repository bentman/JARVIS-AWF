"""Unit tests for improvement proposal summarization and next action derivation (ADR-0027)."""

from awf.improvement.diff import parse_patch_diff_previews
from awf.improvement.summary import (
    derive_next_action,
    derive_safety_assessment,
    derive_scope_classification,
    generate_human_summary,
    generate_proposal_review_narrative,
)


def test_derive_scope_classification():
    localized = [{"path": "a.py", "additions": 10, "deletions": 5}]
    assert derive_scope_classification(localized) == "localized"

    broad_by_files = [{"path": f"file_{i}.py", "additions": 2, "deletions": 1} for i in range(5)]
    assert derive_scope_classification(broad_by_files) == "broad"

    broad_by_lines = [{"path": "big.py", "additions": 80, "deletions": 40}]
    assert derive_scope_classification(broad_by_lines) == "broad"


def test_generate_human_summary_single_file():
    proposal = {
        "status": "ready_for_review",
        "summary": "Fix docstring in validator",
        "verdict_artifact_id": "art-123",
    }
    stats = [{"path": "scripts/validate_backend.py", "additions": 5, "deletions": 2}]
    summary = generate_human_summary(proposal, stats)
    assert "1 file changed (+5 / -2 lines) in scripts/validate_backend.py" in summary
    assert "Fix docstring in validator" in summary
    assert "Validation passed." in summary
    assert "Proposal is ready for review." in summary


def test_generate_human_summary_multiple_files():
    proposal = {
        "status": "draft",
        "summary": "Refactor runner",
    }
    stats = [
        {"path": "backend/src/awf/ops/run.py", "additions": 20, "deletions": 10},
        {"path": "backend/tests/unit/test_run.py", "additions": 15, "deletions": 5},
    ]
    summary = generate_human_summary(proposal, stats)
    assert "2 files changed (+35 / -15 lines) across backend" in summary
    assert "Refactor runner" in summary
    assert "Proposal is in draft." in summary


def test_generate_human_summary_terminal_states():
    merged_prop = {"status": "merged", "target_branch": "main"}
    assert generate_human_summary(merged_prop, []) == "Proposal merged into main."

    rejected_prop = {"status": "rejected"}
    assert generate_human_summary(rejected_prop, []) == "Proposal was rejected and closed."


def test_derive_next_action_lifecycle():
    # Draft
    draft_prop = {"improvement_id": "imp-1", "status": "draft", "verdict_artifact_id": "ver-1"}
    action = derive_next_action(draft_prop)
    assert action["action"] == "mark_ready"
    assert "awf improvement mark-ready imp-1 ver-1" in action["command"]

    # Ready for review
    ready_prop = {"improvement_id": "imp-1", "status": "ready_for_review"}
    action = derive_next_action(ready_prop)
    assert action["action"] == "request_merge"
    assert action["command"] == "awf improvement request-merge imp-1"

    # Pending approval
    pending_prop = {
        "improvement_id": "imp-1",
        "status": "ready_for_review",
        "approval": {"approval_id": "appr-1", "status": "pending"},
    }
    action = derive_next_action(pending_prop)
    assert action["action"] == "approve_merge"
    assert action["command"] == "awf approve appr-1"

    # Approved
    approved_prop = {
        "improvement_id": "imp-1",
        "status": "ready_for_review",
        "approval": {"approval_id": "appr-1", "status": "approved"},
    }
    action = derive_next_action(approved_prop)
    assert action["action"] == "merge"
    assert action["command"] == "awf improvement merge imp-1 appr-1"

    # Merged
    merged_prop = {"improvement_id": "imp-1", "status": "merged"}
    action = derive_next_action(merged_prop)
    assert action["action"] == "none"


def test_parse_patch_diff_previews():
    sample_patch = """diff --git a/foo.py b/foo.py
--- a/foo.py
+++ b/foo.py
@@ -1,3 +1,4 @@
 def hello():
+    print("world")
     return True
diff --git a/bar.txt b/bar.txt
--- a/bar.txt
+++ b/bar.txt
@@ -1 +0,0 @@
-old line
"""
    previews = parse_patch_diff_previews(sample_patch, max_lines_per_file=10)
    assert len(previews) == 2
    assert previews[0]["path"] == "foo.py"
    assert previews[0]["additions"] == 1
    assert previews[0]["deletions"] == 0
    assert not previews[0]["truncated"]

    assert previews[1]["path"] == "bar.txt"
    assert previews[1]["additions"] == 0
    assert previews[1]["deletions"] == 1


def test_derive_safety_assessment():
    proposal = {
        "status": "ready_for_review",
        "verdict_artifact_id": "art-verdict-1",
        "diff_digest": "sha256:1122334455667788",
    }
    stats = [{"path": "a.py", "additions": 4, "deletions": 1}]
    safety = derive_safety_assessment(proposal, stats)
    assert "Localized change (1 file, 5 lines changed)." in safety
    assert "Isolated in worktree sandbox without modifying main branch." in safety
    assert "Validation passed all gate checks (verdict: art-verdict-1)." in safety
    assert "Protected by R2 approval gate" in safety


def test_generate_proposal_review_narrative():
    proposal = {
        "status": "ready_for_review",
        "summary": "Fix docstring in validator",
        "verdict_artifact_id": "art-verdict-1",
        "diff_digest": "sha256:1122334455667788",
        "improvement_id": "imp-123",
    }
    stats = [{"path": "scripts/validate_backend.py", "additions": 2, "deletions": 0}]
    review = generate_proposal_review_narrative(proposal, stats)
    assert "1 file changed (+2 / -0 lines)" in review["what_changed"]
    assert review["where_changed"] == ["scripts/validate_backend.py"]
    assert review["validation_passed"] is True
    assert review["validation_status"] == "PASSED"
    assert "Localized change" in review["why_safe"]
    assert review["next_action"]["command"] == "awf improvement request-merge imp-123"
