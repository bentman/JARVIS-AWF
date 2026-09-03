"""The `awf` core CLI (Section 16.1): a thin wrapper over Phases 0-9.

No command may bypass the Capability Guard, mark a Gate as passed, or
invoke an unregistered adapter - this module only orchestrates; every
mutation flows through `awf.ops.*`, the same operation functions
`awf system serve --stdio` calls (Section 16.3: "the protocol adds no authority").
"""

import argparse
import json
import os
import sys
from pathlib import Path

from awf import ops
from awf.db.bootstrap import init_db
from awf.db.connection import get_connection
from awf.ops.shared import CoreOpError
from awf.paths import REPO_ROOT, db_path
from awf.secrets import cli as secrets_cli


def _print(obj) -> None:
    print(json.dumps(obj, indent=2, default=str))


def _print_or_json(args: argparse.Namespace, obj, text: str) -> None:
    if getattr(args, "json", False):
        _print(obj)
    else:
        print(text)


def _format_outcome(outcome: dict) -> str:
    lines = [
        f"Run: {outcome.get('run_id')}",
        f"Workflow: {outcome.get('workflow_ref')}",
        f"Status: {outcome.get('status')}",
        f"Result: {outcome.get('response_text')}",
    ]
    evidence = outcome.get("evidence") if isinstance(outcome.get("evidence"), list) else []
    failures = outcome.get("failures") if isinstance(outcome.get("failures"), list) else []
    pending = outcome.get("pending_approvals") if isinstance(outcome.get("pending_approvals"), list) else []
    proposal = outcome.get("proposal") if isinstance(outcome.get("proposal"), dict) else None

    if proposal:
        lines.append("\n" + "=" * 60)
        lines.append("AWF IMPROVEMENT PROPOSAL REVIEW")
        lines.append(
            f"Proposal: {proposal.get('improvement_id')}  •  Status: {proposal.get('status', '').upper()} [{str(proposal.get('scope_classification', 'localized')).capitalize()}]"
        )
        lines.append("=" * 60)
        lines.append(f"\n1. WHAT CHANGED:\n  {proposal.get('human_summary') or proposal.get('summary')}")

        verdict = proposal.get("verdict_artifact_id")
        if verdict:
            lines.append(f"\n2. VALIDATION STATUS:\n  PASSED — All gate checks and tests passed (verdict: {verdict})")

        if proposal.get("safety_assessment"):
            lines.append(f"\n3. WHY IT IS SAFE TO CONSIDER:\n  {proposal.get('safety_assessment')}")

        diff_stats = proposal.get("diff_stats") or []
        if diff_stats:
            lines.append("\n4. CHANGED FILES & DIFF PREVIEW:")
            for f in diff_stats:
                lines.append(f"  • {f.get('path')} (+{f.get('additions', 0)} / -{f.get('deletions', 0)} lines)")
                if f.get("preview_lines"):
                    for pl in f["preview_lines"][:6]:
                        lines.append(f"      {pl}")

        next_action = proposal.get("next_action")
        if next_action and next_action.get("command"):
            lines.append("\n" + "-" * 60)
            lines.append(
                f"5. NEXT OPERATOR ACTION:\n  {next_action.get('label')}\n  Command: {next_action.get('command')}"
            )
            lines.append("-" * 60)
        lines.append("=" * 60)

    if evidence and not proposal:
        lines.append("Evidence:")
        lines.extend(f"  - {item.get('type')}: {item.get('path')} ({item.get('artifact_id')})" for item in evidence)
    if failures:
        lines.append("Failures:")
        lines.extend(
            f"  - {item.get('node_id')} ({item.get('step_id')}): {item.get('failure_class') or 'failed'}"
            for item in failures
        )
    if pending:
        lines.append("Pending approvals:")
        lines.extend(f"  - {item.get('approval_id')} {item.get('risk_class') or ''}".rstrip() for item in pending)
    if outcome.get("next_action"):
        lines.append(f"\nNext: {outcome['next_action']}")
    return "\n".join(lines)


def _format_improvement_proposal(proposal: dict, full_diff: bool = False, raw_patch: str | None = None) -> str:
    imp_id = proposal.get("improvement_id", "unknown")
    status = proposal.get("status", "draft")
    summary = proposal.get("human_summary") or proposal.get("summary") or "No summary"
    scope = proposal.get("scope_classification") or "localized"
    safety = proposal.get("safety_assessment") or ""

    lines = [
        "=" * 60,
        f"AWF IMPROVEMENT PROPOSAL REVIEW: {imp_id}",
        f"Status: {status.upper()} [{scope.capitalize()}]",
        "=" * 60,
        f"\n1. WHAT CHANGED:\n  {summary}",
    ]

    diff_stats = proposal.get("diff_stats") or []
    if diff_stats:
        lines.append("\n2. WHERE IT CHANGED:")
        for f in diff_stats:
            add = f.get("additions", 0)
            dele = f.get("deletions", 0)
            path = f.get("path", "")
            lines.append(f"  • {path} (+{add} / -{dele} lines)")

    verdict_id = proposal.get("verdict_artifact_id")
    if verdict_id:
        lines.append(
            f"\n3. VALIDATION STATUS:\n  PASSED — All deterministic verification checks and automated tests passed (verdict: {verdict_id})."
        )
    else:
        lines.append("\n3. VALIDATION STATUS:\n  PENDING — Awaiting verification verdict.")

    if safety:
        lines.append(f"\n4. WHY IT IS SAFE TO CONSIDER:\n  {safety}")

    approval = proposal.get("approval")
    if approval:
        lines.append(f"\nApproval Gate: {approval.get('approval_id')} [{approval.get('status')}]")

    if diff_stats:
        lines.append("\n5. DIFF PREVIEW:")
        for f in diff_stats:
            lines.append(f"  --- {f.get('path')} ---")
            if f.get("preview_lines"):
                for pl in f["preview_lines"][:8]:
                    lines.append(f"    {pl}")
                if f.get("truncated") and not full_diff:
                    lines.append("    ... [diff truncated; run with --full-diff to inspect entire patch]")

    if full_diff and raw_patch:
        lines.append("\nFULL PATCH:")
        lines.append(raw_patch)

    next_action = proposal.get("next_action")
    if next_action:
        cmd = next_action.get("command")
        label = next_action.get("label") or "Next Action"
        lines.append("\n" + "-" * 60)
        lines.append(f"6. NEXT OPERATOR ACTION:\n  {label}")
        if cmd:
            lines.append(f"  Command:   {cmd}")
        if next_action.get("description"):
            lines.append(f"  Rationale: {next_action['description']}")
        lines.append("-" * 60)

    # Technical provenance footer
    target = proposal.get("target_branch") or "main"
    base = str(proposal.get("base_commit", ""))[:10]
    cand = str(proposal.get("candidate_commit", ""))[:10]
    digest = proposal.get("diff_digest") or ""
    lines.append(f"\n[Provenance: target={target} ({base}..{cand}) digest={digest}]")

    return "\n".join(lines)


def _outcome_from_result(result: dict) -> dict:
    outcome = result.get("outcome")
    if isinstance(outcome, dict):
        return outcome
    return {
        "run_id": result.get("run_id"),
        "workflow_ref": result.get("workflow_ref"),
        "status": result.get("status"),
        "response_text": result.get("outputs", {}).get("response_text")
        if isinstance(result.get("outputs"), dict)
        else "",
        "evidence": [],
        "failures": [],
        "pending_approvals": [],
        "next_action": None,
    }


def _one_line(text: str, limit: int = 72) -> str:
    """Collapse a multi-line result to one scannable line."""
    collapsed = " ".join(str(text).split())
    return collapsed if len(collapsed) <= limit else collapsed[: limit - 1].rstrip() + "\u2026"


def _format_run_list(runs: list[dict]) -> str:
    if not runs:
        return 'No runs. Start one with: awf run <workflow> --objective "..."'
    lines = ["Runs:"]
    for run in runs:
        outcome = run.get("outcome") if isinstance(run.get("outcome"), dict) else {}
        response = _one_line(outcome.get("response_text") or "")
        status = str(run.get("status") or "")
        lines.append(f"  {status:<10} {run.get('run_id')}  {run.get('workflow_ref')}")
        if response:
            lines.append(f"             {response}")
    lines.append("")
    lines.append("Detail: awf status <run-id>")
    return "\n".join(lines)


def _format_review_list(result: dict) -> str:
    approvals = result.get("approvals") or []
    changes = [c for c in (result.get("changes") or []) if c.get("status") in {"draft", "ready_for_review", "approved"}]
    if not approvals and not changes:
        return "Nothing is waiting on a decision."
    lines = []
    if approvals:
        lines.append("Approvals:")
        for approval in approvals:
            lines.append(f"  {approval.get('approval_id')}  {approval.get('risk_class')}  run {approval.get('run_id')}")
    if changes:
        if lines:
            lines.append("")
        lines.append("Proposed changes:")
        for change in changes:
            summary = _one_line(change.get("summary") or "", 60)
            lines.append(f"  {change.get('improvement_id')}  [{change.get('status')}]  {summary}")
    lines.append("")
    lines.append("Detail: awf review show <id>   Decide: awf review approve|reject <id>")
    return "\n".join(lines)


def _format_approval_detail(detail: dict) -> str:
    approval = detail.get("approval") or {}
    preview = detail.get("preview") or {}
    appr_id = approval.get("approval_id")
    status = approval.get("status", "pending")
    risk = approval.get("risk_class") or "R2"
    digest = approval.get("action_digest")

    lines = [
        "=" * 60,
        f"AWF APPROVAL REVIEW: {appr_id} [{status.upper()}]",
        f"Risk Class: {risk}  •  Requested: {approval.get('requested_at')}",
        "=" * 60,
    ]

    proposal = preview.get("proposal") if isinstance(preview.get("proposal"), dict) else None
    if proposal:
        summary = proposal.get("human_summary") or proposal.get("summary") or ""
        lines.append(f"\n1. WHAT IS BEING APPROVED:\n  {summary}")
        if proposal.get("safety_assessment"):
            lines.append(f"\n2. WHY IT IS SAFE TO APPROVE:\n  {proposal.get('safety_assessment')}")
        if proposal.get("verdict_artifact_id"):
            lines.append(
                f"\n3. VALIDATION STATUS:\n  PASSED — All gate checks verified (verdict: {proposal['verdict_artifact_id']})"
            )
        diff_stats = proposal.get("diff_stats") or []
        if diff_stats:
            lines.append("\n4. CHANGED FILES & DIFF PREVIEW:")
            for f in diff_stats:
                lines.append(f"  • {f.get('path')} (+{f.get('additions', 0)} / -{f.get('deletions', 0)} lines)")
                if f.get("preview_lines"):
                    for pl in f["preview_lines"][:8]:
                        lines.append(f"      {pl}")
    elif preview.get("machine_action"):
        action = preview["machine_action"]
        lines.append(f"\nAction: {action.get('kind')} {action.get('capability_ref') or ''}")
        lines.append(f"Target: {json.dumps(action.get('target') or {})}")

    lines.append("\n" + "-" * 60)
    lines.append("DECISION ACTIONS:")
    lines.append(f"  Approve: awf review approve {appr_id}")
    lines.append(f'  Reject:  awf review reject {appr_id} --reason "..."')
    lines.append("-" * 60)
    lines.append(f"\n[Digest: {digest}]")
    return "\n".join(lines)


def _format_artifacts(artifacts: list[dict]) -> str:
    if not artifacts:
        return "No artifacts for this run."
    lines = ["Artifacts:"]
    for artifact in artifacts:
        lines.append(
            f"  - {artifact.get('artifact_type')}: {artifact.get('relative_path')} ({artifact.get('artifact_id')})"
        )
    return "\n".join(lines)


def _format_readiness(readiness: dict) -> str:
    lines = [f"Profile: {readiness.get('profile_id') or 'unknown'}"]
    if readiness.get("error"):
        lines.append(f"Error: {readiness['error']}")
    results = readiness.get("readiness") if isinstance(readiness.get("readiness"), dict) else {}
    for name, result in results.items():
        state = "ready" if result.get("ready") else "not ready"
        lines.append(f"{name}: {state} on {result.get('device')} - {result.get('reason')}")
    # The raw capability tokens are probe evidence, not an operator summary;
    # they stay available through `awf system readiness --json`.
    return "\n".join(lines)


def _format_doctor(report: dict) -> str:
    lines = [f"AWF doctor: {report.get('status')}"]
    for check in report.get("checks", []):
        lines.append(f"- {check.get('name')}: {check.get('status')} - {check.get('summary')}")
        if check.get("next_action"):
            lines.append(f"  next: {check['next_action']}")
    if report.get("first_run_command"):
        lines.append(f"First run: {report['first_run_command']}")
    return "\n".join(lines)


def _format_control_summary(summary: dict) -> str:
    work_items = summary.get("operator_work_items") if isinstance(summary.get("operator_work_items"), list) else []
    next_actions = (
        summary.get("operator_next_actions") if isinstance(summary.get("operator_next_actions"), list) else []
    )
    lines = [
        "AWF Control",
        f"Runs: {len(summary.get('runs') or [])}",
        f"Pending approvals: {len(summary.get('approvals') or [])}",
        f"Improvement proposals: {len(summary.get('improvements') or [])}",
    ]
    readiness = summary.get("readiness") if isinstance(summary.get("readiness"), dict) else {}
    llm = summary.get("llm") if isinstance(summary.get("llm"), dict) else {}
    llm_status = llm.get("status") if isinstance(llm.get("status"), dict) else {}
    doctor = summary.get("doctor") if isinstance(summary.get("doctor"), dict) else {}
    lines.append(f"Readiness: {readiness.get('profile_id') or 'unknown'}")
    lines.append(f"LLM: {llm_status.get('state') or 'unknown'}")
    if doctor.get("status"):
        lines.append(f"Doctor: {doctor['status']}")
    if work_items:
        lanes = {
            "Start work": {"idle"},
            "Needs action": {"approval", "failed_run", "readiness", "llm", "doctor"},
            "Running": {"active_run"},
            "Review / close out": {"improvement", "completed_evidence"},
        }
        lines.append("\nWork queue:")
        ordinal = 1
        for lane, kinds in lanes.items():
            lane_items = [item for item in work_items if item.get("kind") in kinds]
            if not lane_items:
                continue
            lines.append(f"  {lane}:")
            for item in lane_items:
                action = item.get("primary_action") if isinstance(item.get("primary_action"), dict) else {}
                command = action.get("command") or item.get("command")
                label = action.get("label") or "Next"
                lines.append(f"    {ordinal}. [{item.get('status')}] {item.get('title')}")
                lines.append(f"       {item.get('description')}")
                lines.append(f"       {label}: {command}")
                ordinal += 1
    else:
        lines.append("\nWork queue: empty")
    start_options = (
        summary.get("operator_start_options") if isinstance(summary.get("operator_start_options"), list) else []
    )
    if start_options:
        lines.append("\nStart work:")
        for option in start_options[:5]:
            command = (
                option.get("primary_action", {}).get("command")
                if isinstance(option.get("primary_action"), dict)
                else None
            )
            lines.append(
                f"  - {option.get('workflow_ref')} [{option.get('status')}] "
                f"{option.get('source') or 'registry'} {option.get('trust_status') or 'trust unknown'}"
            )
            fallback = f"awf run {option.get('workflow_ref')}"
            lines.append(f"    Run: {command or fallback}")
    if next_actions:
        lines.append("\nTop next actions:")
        for index, action in enumerate(next_actions, start=1):
            primary = action.get("primary_action") if isinstance(action.get("primary_action"), dict) else {}
            lines.append(f"  {index}. {primary.get('command') or action.get('command')} :: {action.get('label')}")
    return "\n".join(lines)


def _format_run_detail(detail: dict) -> str:
    run = detail.get("run") if isinstance(detail.get("run"), dict) else {}
    outcome = detail.get("outcome") if isinstance(detail.get("outcome"), dict) else {}
    lines = [
        f"Run: {run.get('run_id')}",
        f"Workflow: {run.get('workflow_ref')}",
        f"Status: {run.get('status')}",
    ]
    if outcome:
        lines.append(f"Result: {outcome.get('response_text')}")
        if outcome.get("next_action"):
            lines.append(f"Next: {outcome['next_action']}")
    work_items = detail.get("operator_work_items") if isinstance(detail.get("operator_work_items"), list) else []
    if work_items:
        lines.append("\nRun work items:")
        for item in work_items:
            lines.append(f"  - [{item.get('status')}] {item.get('title')}")
            lines.append(f"    Next: {item.get('command')}")
    steps = run.get("steps") if isinstance(run.get("steps"), list) else []
    if steps:
        lines.append("\nSteps:")
        for step in steps:
            lines.append(
                f"  - {step.get('node_id')}: {step.get('status')} "
                f"(attempt {step.get('attempt')}, step {step.get('step_id')})"
            )
    failures = outcome.get("failures") if isinstance(outcome.get("failures"), list) else []
    if failures:
        lines.append("\nFailures:")
        for failure in failures:
            lines.append(
                f"  - {failure.get('node_id')} ({failure.get('step_id')}): {failure.get('failure_class') or 'failed'}"
            )
    approvals = outcome.get("pending_approvals") if isinstance(outcome.get("pending_approvals"), list) else []
    if approvals:
        lines.append("\nPending approvals:")
        for approval in approvals:
            lines.append(f"  - {approval.get('approval_id')} {approval.get('risk_class') or 'R2'}")
    artifacts = detail.get("artifacts") if isinstance(detail.get("artifacts"), list) else []
    if artifacts:
        lines.append("\nArtifacts:")
        for artifact in artifacts:
            lines.append(
                f"  - {artifact.get('artifact_type')}: {artifact.get('relative_path')} ({artifact.get('artifact_id')})"
            )
    timeline = detail.get("operator_timeline") if isinstance(detail.get("operator_timeline"), list) else []
    if timeline:
        lines.append("\nTimeline:")
        for item in timeline[:12]:
            lines.append(f"  - {item.get('occurred_at') or 'time n/a'} [{item.get('kind')}] {item.get('title')}")
    return "\n".join(lines)


def cmd_run(args: argparse.Namespace, repo_root: Path, conn) -> int:
    input_data = {"objective": args.objective} if args.objective else {}
    if args.input:
        input_data = json.loads(Path(args.input).read_text())
    result = ops.op_run_start(repo_root, conn, workflow_ref=args.workflow, input_data=input_data)
    _print_or_json(args, result, _format_outcome(_outcome_from_result(result)))
    return 0 if result.get("status") == "SUCCEEDED" else 1


def cmd_status(args: argparse.Namespace, repo_root: Path, conn) -> int:
    if args.run_id is None:
        return cmd_runs(args, repo_root, conn)
    if getattr(args, "artifacts", False):
        result = ops.op_artifact_list(conn, run_id=args.run_id)
        _print_or_json(args, result, _format_artifacts(result))
        return 0
    if getattr(args, "json", False):
        _print(ops.op_run_status(conn, run_id=args.run_id))
        return 0
    result = ops.op_control_center_run_detail(repo_root, conn, run_id=args.run_id)
    print(_format_run_detail(result))
    return 0


def cmd_control(args: argparse.Namespace, repo_root: Path, conn) -> int:
    result = ops.op_control_center_summary(repo_root, conn)
    _print_or_json(args, result, _format_control_summary(result))
    return 0


def cmd_resume(args: argparse.Namespace, repo_root: Path, conn) -> int:
    results = ops.op_run_resume(repo_root, conn)
    text = (
        "No incomplete runs to resume."
        if not results
        else "\n\n".join(_format_outcome(_outcome_from_result(item)) for item in results)
    )
    _print_or_json(args, results, text)
    return 0


def cmd_runs(args: argparse.Namespace, repo_root: Path, conn) -> int:
    result = ops.op_run_list(conn)
    _print_or_json(args, result, _format_run_list(result))
    return 0


def cmd_readiness(args: argparse.Namespace, repo_root: Path, conn) -> int:
    result = ops.op_system_readiness(repo_root)
    _print_or_json(args, result, _format_readiness(result))
    return 0 if "error" not in result else 1


def cmd_doctor(args: argparse.Namespace, repo_root: Path, conn) -> int:
    result = ops.op_system_doctor(repo_root)
    _print_or_json(args, result, _format_doctor(result))
    return 0 if result.get("status") != "error" else 1


def _render_improvement(args: argparse.Namespace, repo_root: Path, conn, result: dict) -> int:
    raw_patch = None
    if getattr(args, "full_diff", False):
        patch_art_id = result.get("patch_artifact_id")
        if patch_art_id:
            from awf.paths import artifacts_dir

            art_row = conn.execute(
                "SELECT relative_path FROM artifacts WHERE artifact_id = ?", (patch_art_id,)
            ).fetchone()
            if art_row is not None:
                patch_file = artifacts_dir(repo_root) / art_row["relative_path"]
                if patch_file.is_file():
                    raw_patch = patch_file.read_text(encoding="utf-8", errors="replace")
    _print_or_json(
        args,
        result,
        _format_improvement_proposal(result, full_diff=getattr(args, "full_diff", False), raw_patch=raw_patch),
    )
    return 0


def cmd_improvement_prepare(args: argparse.Namespace, repo_root: Path, conn) -> int:
    _print(ops.op_improvement_prepare(repo_root, conn, run_id=args.run_id, summary=args.summary))
    return 0


def cmd_improvement_mark_ready(args: argparse.Namespace, repo_root: Path, conn) -> int:
    _print(
        ops.op_improvement_mark_ready(
            repo_root,
            conn,
            improvement_id=args.improvement_id,
            verdict_artifact_id=args.verdict_artifact_id,
            validation_artifact_ids=args.validation_artifact_id,
        )
    )
    return 0


def cmd_improvement_request_merge(args: argparse.Namespace, repo_root: Path, conn) -> int:
    _print(ops.op_improvement_request_merge(repo_root, conn, improvement_id=args.improvement_id))
    return 0


def cmd_improvement_merge(args: argparse.Namespace, repo_root: Path, conn) -> int:
    _print(ops.op_improvement_merge(repo_root, conn, improvement_id=args.improvement_id, approval_id=args.approval_id))
    return 0


# One id namespace for the operator: an approval, a proposed code change, and a
# drafted registry object are all "something waiting on a decision", and `awf
# review` resolves which one an id names rather than making the operator know.
def _review_resolve(repo_root: Path, conn, item_id: str) -> tuple[str, dict]:
    lookups = (
        ("approval", lambda: ops.op_approval_detail(conn, approval_id=item_id)),
        ("change", lambda: ops.op_improvement_get(conn, improvement_id=item_id)),
        ("draft", lambda: ops.op_proposal_get(repo_root, conn, proposal_id=item_id)),
    )
    for kind, lookup in lookups:
        try:
            return kind, lookup()
        except CoreOpError:
            continue
    raise CoreOpError(f"no approval, change, or draft with id {item_id!r} - run `awf control` to see what is waiting")


def cmd_review_list(args: argparse.Namespace, repo_root: Path, conn) -> int:
    result = {
        "approvals": ops.op_approval_list(conn),
        "changes": ops.op_improvement_list(conn, status=args.status),
    }
    _print_or_json(args, result, _format_review_list(result))
    return 0


def cmd_review_show(args: argparse.Namespace, repo_root: Path, conn) -> int:
    kind, payload = _review_resolve(repo_root, conn, args.item_id)
    if kind == "approval":
        _print_or_json(args, payload, _format_approval_detail(payload))
        return 0
    if kind == "change":
        return _render_improvement(args, repo_root, conn, payload)
    _print(payload)
    return 0


def cmd_review_approve(args: argparse.Namespace, repo_root: Path, conn) -> int:
    kind, _payload = _review_resolve(repo_root, conn, args.item_id)
    if kind != "approval":
        raise CoreOpError(
            f"{args.item_id} is a {kind}, not an approval. "
            f"Use `awf review merge {args.item_id} <approval-id>` for a change, "
            f"or `awf review publish {args.item_id} --digest <digest>` for a draft."
        )
    _print(ops.op_approval_approve(conn, approval_id=args.item_id))
    return 0


def cmd_review_reject(args: argparse.Namespace, repo_root: Path, conn) -> int:
    kind, _payload = _review_resolve(repo_root, conn, args.item_id)
    if kind == "approval":
        _print(ops.op_approval_reject(conn, approval_id=args.item_id, reason=args.reason))
    elif kind == "change":
        _print(ops.op_improvement_reject(repo_root, conn, improvement_id=args.item_id, reason=args.reason))
    else:
        _print(ops.op_proposal_reject(repo_root, conn, proposal_id=args.item_id, reason=args.reason))
    return 0


def cmd_registry_validate(args: argparse.Namespace, repo_root: Path, conn) -> int:
    _print(ops.op_registry_validate(Path(args.definition_file), kind=args.kind))
    return 0


def cmd_registry_publish(args: argparse.Namespace, repo_root: Path, conn) -> int:
    _print(ops.op_registry_publish(repo_root, conn, path=Path(args.definition_file), kind=args.kind))
    return 0


def cmd_registry_reindex(args: argparse.Namespace, repo_root: Path, conn) -> int:
    _print(ops.op_registry_reindex(repo_root, conn))
    return 0


def cmd_registry_retire(args: argparse.Namespace, repo_root: Path, conn) -> int:
    _print(ops.op_registry_retire(conn, kind=args.kind, name=args.name, version=args.version))
    return 0


def cmd_registry_trust(args: argparse.Namespace, repo_root: Path, conn) -> int:
    _print(ops.op_registry_trust(conn, kind=args.kind, name=args.name, version=args.version, status=args.status))
    return 0


def cmd_author_workflow(args: argparse.Namespace, repo_root: Path, conn) -> int:
    _print(
        ops.op_workflow_author_draft(
            repo_root,
            conn,
            objective=args.objective,
            name=args.name,
            version=args.version,
            profile_ref=args.profile,
        )
    )
    return 0


def cmd_proposal_update(args: argparse.Namespace, repo_root: Path, conn) -> int:
    _print(
        ops.op_proposal_update(
            repo_root,
            conn,
            proposal_id=args.proposal_id,
            content=Path(args.file).read_text(encoding="utf-8"),
            summary=args.summary,
        )
    )
    return 0


def cmd_proposal_publish(args: argparse.Namespace, repo_root: Path, conn) -> int:
    _print(ops.op_proposal_publish(repo_root, conn, proposal_id=args.proposal_id, digest=args.digest))
    return 0


def cmd_memory_search(args: argparse.Namespace, repo_root: Path, conn) -> int:
    _print(ops.op_memory_search(repo_root, conn, query=args.query, profile_ref=args.profile))
    return 0


def cmd_memory_get(args: argparse.Namespace, repo_root: Path, conn) -> int:
    _print(ops.op_memory_get(repo_root, conn, ref=args.ref))
    return 0


def cmd_memory_propose(args: argparse.Namespace, repo_root: Path, conn) -> int:
    _print(ops.op_memory_propose(repo_root, conn, path=Path(args.file), summary=args.summary))
    return 0


def cmd_memory_publish(args: argparse.Namespace, repo_root: Path, conn) -> int:
    _print(ops.op_memory_publish(repo_root, conn, proposal_id=args.proposal_id, digest=args.digest))
    return 0


def cmd_memory_reject(args: argparse.Namespace, repo_root: Path, conn) -> int:
    _print(ops.op_memory_reject(repo_root, conn, proposal_id=args.proposal_id, reason=args.reason))
    return 0


def cmd_memory_block(args: argparse.Namespace, repo_root: Path, conn) -> int:
    _print(ops.op_memory_block(conn, ref=args.ref))
    return 0


def cmd_session_start(args: argparse.Namespace, repo_root: Path, conn) -> int:
    _print(ops.op_session_start(conn, title=args.title, expires_at=args.expires_at))
    return 0


def cmd_session_append(args: argparse.Namespace, repo_root: Path, conn) -> int:
    content = json.loads(Path(args.json).read_text(encoding="utf-8"))
    _print(
        ops.op_session_append(conn, session_id=args.session_id, role=args.role, content=content, summary=args.summary)
    )
    return 0


def cmd_session_show(args: argparse.Namespace, repo_root: Path, conn) -> int:
    _print(ops.op_session_show(conn, session_id=args.session_id))
    return 0


def cmd_session_summarize(args: argparse.Namespace, repo_root: Path, conn) -> int:
    _print(ops.op_session_summarize(conn, session_id=args.session_id, summary=args.summary))
    return 0


def cmd_episodic_search(args: argparse.Namespace, repo_root: Path, conn) -> int:
    _print(ops.op_episodic_search(conn, query=args.query, run_id=args.run_id))
    return 0


def cmd_episodic_timeline(args: argparse.Namespace, repo_root: Path, conn) -> int:
    _print(ops.op_episodic_timeline(conn, run_id=args.run_id))
    return 0


def cmd_serve(args: argparse.Namespace, repo_root: Path, conn) -> int:
    conn.close()  # the server owns its own connection lifecycle
    from awf.server.stdio import serve_stdio

    serve_stdio(repo_root)
    return 0


def cmd_llm_servers(args: argparse.Namespace, repo_root: Path, conn) -> int:
    _print(ops.op_llm_servers(repo_root))
    return 0


def cmd_llm_models(args: argparse.Namespace, repo_root: Path, conn) -> int:
    _print(ops.op_llm_models(repo_root))
    return 0


def cmd_llm_acquire(args: argparse.Namespace, repo_root: Path, conn) -> int:
    _print(ops.op_llm_acquire(repo_root))
    return 0


def cmd_llm_select(args: argparse.Namespace, repo_root: Path, conn) -> int:
    _print(
        ops.op_llm_select(
            repo_root,
            conn,
            server_id=args.server_id,
            model=args.model,
            allow_remote=args.allow_remote,
        )
    )
    return 0


def cmd_llm_serve(args: argparse.Namespace, repo_root: Path, conn) -> int:
    _print(ops.op_llm_serve(repo_root, conn, action=args.action))
    return 0


# One line per command path, including the group parents that only exist to
# hold subcommands. `awf --help` and every `awf <group> --help` read from here.
CLI_HELP = {
    ("run",): "Start work: run a workflow",
    ("control",): "What needs action, and the command for each",
    ("status",): "Runs: the list, one run's detail, or its artifacts",
    ("doctor",): "Check the install and report what to fix",
    ("review",): "Decide on anything waiting: approvals, changes, drafts",
    ("review", "list"): "List everything waiting on a decision",
    ("review", "show"): "Show one approval, proposed change, or draft",
    ("review", "approve"): "Approve a pending approval",
    ("review", "reject"): "Reject an approval, change, or draft",
    ("review", "prepare"): "Turn a run's work into a proposed change",
    ("review", "mark-ready"): "Mark a proposed change ready for review",
    ("review", "request-merge"): "Request merge approval for a change",
    ("review", "merge"): "Merge an approved change",
    ("review", "draft"): "Draft a new workflow from an objective",
    ("review", "update"): "Replace a draft's definition file",
    ("review", "publish"): "Publish a draft into the registry",
    ("registry",): "Manage published workflows, agents, skills, and policies",
    ("registry", "validate"): "Validate a definition file before publishing",
    ("registry", "publish"): "Publish a definition into the registry",
    ("registry", "reindex"): "Rebuild the registry index from disk",
    ("registry", "retire"): "Retire a published version",
    ("registry", "trust"): "Set the trust status of a published version",
    ("memory",): "Search and curate what the system remembers",
    ("memory", "search"): "Search semantic and episodic memory",
    ("memory", "get"): "Show one semantic memory",
    ("memory", "propose"): "Draft a semantic memory proposal",
    ("memory", "publish"): "Publish a semantic memory proposal",
    ("memory", "reject"): "Reject a semantic memory proposal",
    ("memory", "block"): "Block a semantic memory from recall",
    ("memory", "events"): "Search the event history behind runs",
    ("memory", "timeline"): "Show the raw event timeline for a run",
    ("memory", "session-start"): "Start a conversation session",
    ("memory", "session-append"): "Append a turn to a session",
    ("memory", "session-show"): "Show a session",
    ("memory", "session-summarize"): "Summarize and close a session",
    ("system",): "Host, model, secret, and process configuration",
    ("system", "readiness"): "Show hardware and runtime readiness per function",
    ("system", "resume"): "Recover runs interrupted by a restart",
    ("system", "secret"): "Manage local secret names and values",
    ("system", "serve"): "Serve the JSON-RPC protocol for the GUI and TUI",
    ("system", "llm"): "Configure and serve the local language model",
    ("system", "llm", "servers"): "List detected local LLM servers",
    ("system", "llm", "models"): "List available local models",
    ("system", "llm", "acquire"): "Download the selected model",
    ("system", "llm", "select"): "Select the server and model to use",
    ("system", "llm", "serve"): "Start, stop, or check the local model server",
}

CLI_DESCRIPTION = """\
awf - operate the Agentic Workflow Fabric from the terminal.

The loop:
  awf doctor                     check the install
  awf run <workflow> --objective "..."
                                 start work
  awf control                    see what needs action, and the command for it
  awf status                     list runs; add a run id to follow one
  awf review list                decide on what is waiting

Configuration lives under: registry, memory, system.
"""

CLI_COMMAND_SPECS = (
    {
        "path": ("run",),
        "func": cmd_run,
        "args": (
            {"flags": ("workflow",)},
            {"flags": ("--input",), "default": None, "group": "input"},
            {"flags": ("--objective",), "default": None, "group": "input"},
            {"flags": ("--json",), "action": "store_true"},
        ),
    },
    {
        "path": ("status",),
        "func": cmd_status,
        "args": (
            {"flags": ("run_id",), "nargs": "?", "default": None},
            {"flags": ("--artifacts",), "action": "store_true"},
            {"flags": ("--json",), "action": "store_true"},
        ),
    },
    {"path": ("control",), "func": cmd_control, "args": ({"flags": ("--json",), "action": "store_true"},)},
    {"path": ("system", "resume"), "func": cmd_resume, "args": ({"flags": ("--json",), "action": "store_true"},)},
    {
        "path": ("review", "list"),
        "func": cmd_review_list,
        "args": ({"flags": ("--status",), "default": None}, {"flags": ("--json",), "action": "store_true"}),
    },
    {
        "path": ("review", "show"),
        "func": cmd_review_show,
        "args": (
            {"flags": ("item_id",)},
            {"flags": ("--json",), "action": "store_true"},
            {"flags": ("--full-diff",), "action": "store_true"},
        ),
    },
    {"path": ("review", "approve"), "func": cmd_review_approve, "args": ({"flags": ("item_id",)},)},
    {
        "path": ("review", "reject"),
        "func": cmd_review_reject,
        "args": ({"flags": ("item_id",)}, {"flags": ("--reason",), "required": True}),
    },
    {"path": ("system", "readiness"), "func": cmd_readiness, "args": ({"flags": ("--json",), "action": "store_true"},)},
    {"path": ("doctor",), "func": cmd_doctor, "args": ({"flags": ("--json",), "action": "store_true"},)},
    {
        "path": ("review", "prepare"),
        "func": cmd_improvement_prepare,
        "args": ({"flags": ("run_id",)}, {"flags": ("--summary",), "default": None}),
    },
    {
        "path": ("review", "mark-ready"),
        "func": cmd_improvement_mark_ready,
        "args": (
            {"flags": ("improvement_id",)},
            {"flags": ("--verdict-artifact-id",), "required": True},
            {"flags": ("--validation-artifact-id",), "action": "append", "default": []},
        ),
    },
    {
        "path": ("review", "request-merge"),
        "func": cmd_improvement_request_merge,
        "args": ({"flags": ("improvement_id",)},),
    },
    {
        "path": ("review", "merge"),
        "func": cmd_improvement_merge,
        "args": ({"flags": ("improvement_id",)}, {"flags": ("approval_id",)}),
    },
    {
        "path": ("registry", "validate"),
        "func": cmd_registry_validate,
        "args": ({"flags": ("definition_file",)}, {"flags": ("--kind",), "default": None}),
    },
    {
        "path": ("registry", "publish"),
        "func": cmd_registry_publish,
        "args": ({"flags": ("definition_file",)}, {"flags": ("--kind",), "required": True}),
    },
    {"path": ("registry", "reindex"), "func": cmd_registry_reindex, "args": ()},
    {
        "path": ("registry", "retire"),
        "func": cmd_registry_retire,
        "args": ({"flags": ("kind",)}, {"flags": ("name",)}, {"flags": ("version",)}),
    },
    {
        "path": ("registry", "trust"),
        "func": cmd_registry_trust,
        "args": (
            {"flags": ("kind",)},
            {"flags": ("name",)},
            {"flags": ("version",)},
            {"flags": ("--status",), "required": True},
        ),
    },
    {
        "path": ("review", "draft"),
        "func": cmd_author_workflow,
        "args": (
            {"flags": ("--objective",), "required": True},
            {"flags": ("--name",), "default": None},
            {"flags": ("--version",), "default": None},
            {"flags": ("--profile",), "default": ops.workflow_authoring.DEFAULT_AUTHOR_PROFILE},
        ),
    },
    {
        "path": ("review", "update"),
        "func": cmd_proposal_update,
        "args": (
            {"flags": ("proposal_id",)},
            {"flags": ("--file",), "required": True},
            {"flags": ("--summary",), "default": None},
        ),
    },
    {
        "path": ("review", "publish"),
        "func": cmd_proposal_publish,
        "args": ({"flags": ("proposal_id",)}, {"flags": ("--digest",), "required": True}),
    },
    {
        "path": ("memory", "search"),
        "func": cmd_memory_search,
        "args": ({"flags": ("query",)}, {"flags": ("--profile",), "default": "default@1.0.0"}),
    },
    {"path": ("memory", "get"), "func": cmd_memory_get, "args": ({"flags": ("ref",)},)},
    {
        "path": ("memory", "propose"),
        "func": cmd_memory_propose,
        "args": ({"flags": ("--file",), "required": True}, {"flags": ("--summary",), "default": None}),
    },
    {
        "path": ("memory", "publish"),
        "func": cmd_memory_publish,
        "args": ({"flags": ("proposal_id",)}, {"flags": ("--digest",), "required": True}),
    },
    {
        "path": ("memory", "reject"),
        "func": cmd_memory_reject,
        "args": ({"flags": ("proposal_id",)}, {"flags": ("--reason",), "default": None}),
    },
    {"path": ("memory", "block"), "func": cmd_memory_block, "args": ({"flags": ("ref",)},)},
    {
        "path": ("memory", "session-start"),
        "func": cmd_session_start,
        "args": ({"flags": ("--title",), "default": None}, {"flags": ("--expires-at",), "default": None}),
    },
    {
        "path": ("memory", "session-append"),
        "func": cmd_session_append,
        "args": (
            {"flags": ("session_id",)},
            {"flags": ("--role",), "required": True},
            {"flags": ("--json",), "required": True},
            {"flags": ("--summary",), "default": None},
        ),
    },
    {"path": ("memory", "session-show"), "func": cmd_session_show, "args": ({"flags": ("session_id",)},)},
    {
        "path": ("memory", "session-summarize"),
        "func": cmd_session_summarize,
        "args": ({"flags": ("session_id",)}, {"flags": ("--summary",), "default": None}),
    },
    {
        "path": ("memory", "events"),
        "func": cmd_episodic_search,
        "args": ({"flags": ("query",)}, {"flags": ("--run-id",), "default": None}),
    },
    {"path": ("memory", "timeline"), "func": cmd_episodic_timeline, "args": ({"flags": ("run_id",)},)},
    {"path": ("system", "llm", "servers"), "func": cmd_llm_servers, "args": ()},
    {"path": ("system", "llm", "models"), "func": cmd_llm_models, "args": ()},
    {"path": ("system", "llm", "acquire"), "func": cmd_llm_acquire, "args": ()},
    {
        "path": ("system", "llm", "select"),
        "func": cmd_llm_select,
        "args": (
            {"flags": ("server_id",)},
            {"flags": ("--model",), "default": None},
            {"flags": ("--allow-remote",), "action": "store_true"},
        ),
    },
    {
        "path": ("system", "llm", "serve"),
        "func": cmd_llm_serve,
        "args": ({"flags": ("action",), "choices": ("start", "stop", "status")},),
    },
    {
        "path": ("system", "secret"),
        "defaults": {"is_secret": True},
        "args": ({"flags": ("secret_args",), "nargs": "REMAINDER"},),
    },
    {"path": ("system", "serve"), "func": cmd_serve, "args": ({"flags": ("--stdio",), "action": "store_true"},)},
)


# Argument names carry the same meaning everywhere they appear, so their help
# text is written once here rather than repeated per command.
ARG_HELP = {
    "--json": "Print the raw JSON payload instead of the operator summary",
    "--objective": "Plain-language objective for the run",
    "--input": "Path to a JSON file matching the workflow's inputSchema",
    "--reason": "Why this is being rejected",
    "--summary": "Short human-readable summary",
    "--status": "Filter by status",
    "--full-diff": "Show the complete diff instead of a preview",
    "--artifacts": "List the run's artifacts instead of its detail",
    "--digest": "Expected sha256 digest of the definition being published",
    "run_id": "Run identifier",
    "approval_id": "Approval identifier",
    "improvement_id": "Improvement proposal identifier",
    "proposal_id": "Proposal identifier",
    "workflow": "Workflow reference, name@version (version optional)",
}


def _argument_kwargs(spec: dict) -> dict:
    kwargs = {key: value for key, value in spec.items() if key not in {"flags", "group"}}
    if kwargs.get("nargs") == "REMAINDER":
        kwargs["nargs"] = argparse.REMAINDER
    if "help" not in kwargs:
        for flag in spec["flags"]:
            if flag in ARG_HELP:
                kwargs["help"] = ARG_HELP[flag]
                break
    return kwargs


def _install_cli_command(parsers: dict[tuple[str, ...], argparse.ArgumentParser], spec: dict) -> None:
    path = spec["path"]
    current_path: tuple[str, ...] = ()
    for index, part in enumerate(path):
        parent = parsers[current_path]
        subparsers = getattr(parent, "_awf_subparsers", None)
        if subparsers is None:
            dest = "command" if not current_path else f"{current_path[0]}_command"
            subparsers = parent.add_subparsers(dest=dest, required=True, metavar="<command>")
            parent._awf_subparsers = subparsers
        next_path = (*current_path, part)
        if next_path not in parsers:
            summary = CLI_HELP.get(next_path)
            parsers[next_path] = subparsers.add_parser(part, help=summary, description=summary)
        current_path = next_path
        if index == len(path) - 1:
            parser = parsers[current_path]
            groups: dict[str, argparse._MutuallyExclusiveGroup] = {}
            for arg_spec in spec.get("args", ()):
                target = parser
                if group_name := arg_spec.get("group"):
                    if group_name not in groups:
                        groups[group_name] = parser.add_mutually_exclusive_group()
                    target = groups[group_name]
                target.add_argument(*arg_spec["flags"], **_argument_kwargs(arg_spec))
            parser.set_defaults(**spec.get("defaults", {}))
            if func := spec.get("func"):
                parser.set_defaults(func=func)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="awf",
        description=CLI_DESCRIPTION,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parsers = {(): parser}
    for spec in CLI_COMMAND_SPECS:
        _install_cli_command(parsers, spec)
    return parser


def run(argv: list[str], repo_root: Path) -> int:
    args = build_parser().parse_args(argv)

    if getattr(args, "is_secret", False):
        return secrets_cli.run(args.secret_args, repo_root)

    conn_db_path = db_path(repo_root)
    init_db(conn_db_path)
    conn = get_connection(conn_db_path)
    try:
        try:
            return args.func(args, repo_root, conn)
        except Exception as exc:
            # The JSON-RPC surface already reports every failure as a message
            # rather than a stack trace; the CLI matches that contract. Set
            # AWF_DEBUG=1 to see the traceback instead.
            if os.environ.get("AWF_DEBUG"):
                raise
            print(f"error: {exc}", file=sys.stderr)
            return 1
    finally:
        conn.close()


def main() -> int:
    return run(sys.argv[1:], REPO_ROOT)


if __name__ == "__main__":
    sys.exit(main())
