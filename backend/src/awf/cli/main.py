"""The `awf` core CLI (Section 16.1): a thin wrapper over Phases 0-9.

No command may bypass the Capability Guard, mark a Gate as passed, or
invoke an unregistered adapter - this module only orchestrates; every
mutation flows through `awf.cli.core_ops`, the same functions
`awf serve --stdio` calls (Section 16.3: "the protocol adds no authority").
"""

import argparse
import json
import sys
from pathlib import Path

from awf.cli import core_ops as ops
from awf.cli.core_ops import CoreOpError
from awf.db.bootstrap import init_db
from awf.db.connection import get_connection
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
    if evidence:
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
        lines.append(f"Next: {outcome['next_action']}")
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


def _format_run_list(runs: list[dict]) -> str:
    if not runs:
        return "No runs."
    lines = ["Runs:"]
    for run in runs:
        outcome = run.get("outcome") if isinstance(run.get("outcome"), dict) else {}
        response = outcome.get("response_text") or ""
        lines.append(f"  - {run.get('run_id')} {run.get('status')} {run.get('workflow_ref')} :: {response}")
    return "\n".join(lines)


def _format_approvals(approvals: list[dict]) -> str:
    if not approvals:
        return "No pending approvals."
    lines = ["Pending approvals:"]
    for approval in approvals:
        risk = approval.get("risk_class") or "risk?"
        lines.append(
            f"  - {approval.get('approval_id')} {risk} run={approval.get('run_id')} digest={approval.get('action_digest')}"
        )
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
    tokens = readiness.get("tokens") if isinstance(readiness.get("tokens"), list) else []
    if tokens:
        lines.append(f"Tokens: {', '.join(tokens)}")
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


def cmd_run(args: argparse.Namespace, repo_root: Path, conn) -> int:
    input_data = {"objective": args.objective} if args.objective else {}
    if args.input:
        input_data = json.loads(Path(args.input).read_text())
    result = ops.op_run_start(repo_root, conn, workflow_ref=args.workflow, input_data=input_data)
    _print_or_json(args, result, _format_outcome(_outcome_from_result(result)))
    return 0 if result.get("status") == "SUCCEEDED" else 1


def cmd_status(args: argparse.Namespace, repo_root: Path, conn) -> int:
    result = ops.op_run_status(conn, run_id=args.run_id)
    _print_or_json(args, result, _format_outcome(result["outcome"]))
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


def cmd_approvals(args: argparse.Namespace, repo_root: Path, conn) -> int:
    result = ops.op_approval_list(conn)
    _print_or_json(args, result, _format_approvals(result))
    return 0


def cmd_approve(args: argparse.Namespace, repo_root: Path, conn) -> int:
    _print(ops.op_approval_approve(conn, approval_id=args.approval_id))
    return 0


def cmd_reject(args: argparse.Namespace, repo_root: Path, conn) -> int:
    _print(ops.op_approval_reject(conn, approval_id=args.approval_id, reason=args.reason))
    return 0


def cmd_artifacts(args: argparse.Namespace, repo_root: Path, conn) -> int:
    result = ops.op_artifact_list(conn, run_id=args.run_id)
    _print_or_json(args, result, _format_artifacts(result))
    return 0


def cmd_readiness(args: argparse.Namespace, repo_root: Path, conn) -> int:
    result = ops.op_system_readiness(repo_root)
    _print_or_json(args, result, _format_readiness(result))
    return 0 if "error" not in result else 1


def cmd_doctor(args: argparse.Namespace, repo_root: Path, conn) -> int:
    result = ops.op_system_doctor(repo_root)
    _print_or_json(args, result, _format_doctor(result))
    return 0 if result.get("status") != "error" else 1


def cmd_improvement_list(args: argparse.Namespace, repo_root: Path, conn) -> int:
    _print(ops.op_improvement_list(conn, status=args.status))
    return 0


def cmd_improvement_show(args: argparse.Namespace, repo_root: Path, conn) -> int:
    _print(ops.op_improvement_get(conn, improvement_id=args.improvement_id))
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


def cmd_improvement_reject(args: argparse.Namespace, repo_root: Path, conn) -> int:
    _print(ops.op_improvement_reject(repo_root, conn, improvement_id=args.improvement_id, reason=args.reason))
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


def cmd_proposal_show(args: argparse.Namespace, repo_root: Path, conn) -> int:
    _print(ops.op_proposal_get(repo_root, conn, proposal_id=args.proposal_id))
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


def cmd_proposal_reject(args: argparse.Namespace, repo_root: Path, conn) -> int:
    _print(ops.op_proposal_reject(repo_root, conn, proposal_id=args.proposal_id, reason=args.reason))
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="awf")
    sub = parser.add_subparsers(dest="command", required=True)

    run_parser = sub.add_parser("run")
    run_parser.add_argument("workflow")
    run_input = run_parser.add_mutually_exclusive_group()
    run_input.add_argument("--input", required=False, default=None)
    run_input.add_argument("--objective", required=False, default=None)
    run_parser.add_argument("--json", action="store_true")
    run_parser.set_defaults(func=cmd_run)

    status_parser = sub.add_parser("status")
    status_parser.add_argument("run_id")
    status_parser.add_argument("--json", action="store_true")
    status_parser.set_defaults(func=cmd_status)

    resume_parser = sub.add_parser("resume")
    resume_parser.add_argument("--json", action="store_true")
    resume_parser.set_defaults(func=cmd_resume)

    runs_parser = sub.add_parser("runs")
    runs_parser.add_argument("--json", action="store_true")
    runs_parser.set_defaults(func=cmd_runs)

    approvals_parser = sub.add_parser("approvals")
    approvals_parser.add_argument("--json", action="store_true")
    approvals_parser.set_defaults(func=cmd_approvals)

    approve_parser = sub.add_parser("approve")
    approve_parser.add_argument("approval_id")
    approve_parser.set_defaults(func=cmd_approve)

    reject_parser = sub.add_parser("reject")
    reject_parser.add_argument("approval_id")
    reject_parser.add_argument("--reason", required=True)
    reject_parser.set_defaults(func=cmd_reject)

    artifacts_parser = sub.add_parser("artifacts")
    artifacts_parser.add_argument("run_id")
    artifacts_parser.add_argument("--json", action="store_true")
    artifacts_parser.set_defaults(func=cmd_artifacts)

    readiness_parser = sub.add_parser("readiness")
    readiness_parser.add_argument("--json", action="store_true")
    readiness_parser.set_defaults(func=cmd_readiness)

    doctor_parser = sub.add_parser("doctor")
    doctor_parser.add_argument("--json", action="store_true")
    doctor_parser.set_defaults(func=cmd_doctor)

    improvement_parser = sub.add_parser("improvement")
    improvement_sub = improvement_parser.add_subparsers(dest="improvement_command", required=True)
    improvement_list_parser = improvement_sub.add_parser("list")
    improvement_list_parser.add_argument("--status", required=False, default=None)
    improvement_list_parser.set_defaults(func=cmd_improvement_list)
    improvement_show_parser = improvement_sub.add_parser("show")
    improvement_show_parser.add_argument("improvement_id")
    improvement_show_parser.set_defaults(func=cmd_improvement_show)
    improvement_prepare_parser = improvement_sub.add_parser("prepare")
    improvement_prepare_parser.add_argument("run_id")
    improvement_prepare_parser.add_argument("--summary", required=False, default=None)
    improvement_prepare_parser.set_defaults(func=cmd_improvement_prepare)
    improvement_ready_parser = improvement_sub.add_parser("mark-ready")
    improvement_ready_parser.add_argument("improvement_id")
    improvement_ready_parser.add_argument("--verdict-artifact-id", required=True)
    improvement_ready_parser.add_argument("--validation-artifact-id", action="append", default=[])
    improvement_ready_parser.set_defaults(func=cmd_improvement_mark_ready)
    improvement_request_parser = improvement_sub.add_parser("request-merge")
    improvement_request_parser.add_argument("improvement_id")
    improvement_request_parser.set_defaults(func=cmd_improvement_request_merge)
    improvement_merge_parser = improvement_sub.add_parser("merge")
    improvement_merge_parser.add_argument("improvement_id")
    improvement_merge_parser.add_argument("approval_id")
    improvement_merge_parser.set_defaults(func=cmd_improvement_merge)
    improvement_reject_parser = improvement_sub.add_parser("reject")
    improvement_reject_parser.add_argument("improvement_id")
    improvement_reject_parser.add_argument("--reason", required=False, default=None)
    improvement_reject_parser.set_defaults(func=cmd_improvement_reject)

    registry_parser = sub.add_parser("registry")
    registry_sub = registry_parser.add_subparsers(dest="registry_command", required=True)
    validate_parser = registry_sub.add_parser("validate")
    validate_parser.add_argument("definition_file")
    validate_parser.add_argument("--kind", required=False, default=None)
    validate_parser.set_defaults(func=cmd_registry_validate)
    publish_parser = registry_sub.add_parser("publish")
    publish_parser.add_argument("definition_file")
    publish_parser.add_argument("--kind", required=True)
    publish_parser.set_defaults(func=cmd_registry_publish)
    reindex_parser = registry_sub.add_parser("reindex")
    reindex_parser.set_defaults(func=cmd_registry_reindex)
    retire_parser = registry_sub.add_parser("retire")
    retire_parser.add_argument("kind")
    retire_parser.add_argument("name")
    retire_parser.add_argument("version")
    retire_parser.set_defaults(func=cmd_registry_retire)
    trust_parser = registry_sub.add_parser("trust")
    trust_parser.add_argument("kind")
    trust_parser.add_argument("name")
    trust_parser.add_argument("version")
    trust_parser.add_argument("--status", required=True)
    trust_parser.set_defaults(func=cmd_registry_trust)

    author_parser = sub.add_parser("author")
    author_sub = author_parser.add_subparsers(dest="author_command", required=True)
    author_workflow_parser = author_sub.add_parser("workflow")
    author_workflow_parser.add_argument("--objective", required=True)
    author_workflow_parser.add_argument("--name", required=False, default=None)
    author_workflow_parser.add_argument("--version", required=False, default=None)
    author_workflow_parser.add_argument(
        "--profile", required=False, default=ops.workflow_authoring.DEFAULT_AUTHOR_PROFILE
    )
    author_workflow_parser.set_defaults(func=cmd_author_workflow)

    proposal_parser = sub.add_parser("proposal")
    proposal_sub = proposal_parser.add_subparsers(dest="proposal_command", required=True)
    proposal_show_parser = proposal_sub.add_parser("show")
    proposal_show_parser.add_argument("proposal_id")
    proposal_show_parser.set_defaults(func=cmd_proposal_show)
    proposal_update_parser = proposal_sub.add_parser("update")
    proposal_update_parser.add_argument("proposal_id")
    proposal_update_parser.add_argument("--file", required=True)
    proposal_update_parser.add_argument("--summary", required=False, default=None)
    proposal_update_parser.set_defaults(func=cmd_proposal_update)
    proposal_publish_parser = proposal_sub.add_parser("publish")
    proposal_publish_parser.add_argument("proposal_id")
    proposal_publish_parser.add_argument("--digest", required=True)
    proposal_publish_parser.set_defaults(func=cmd_proposal_publish)
    proposal_reject_parser = proposal_sub.add_parser("reject")
    proposal_reject_parser.add_argument("proposal_id")
    proposal_reject_parser.add_argument("--reason", required=False, default=None)
    proposal_reject_parser.set_defaults(func=cmd_proposal_reject)

    memory_parser = sub.add_parser("memory")
    memory_sub = memory_parser.add_subparsers(dest="memory_command", required=True)
    memory_search_parser = memory_sub.add_parser("search")
    memory_search_parser.add_argument("query")
    memory_search_parser.add_argument("--profile", required=False, default="default@1.0.0")
    memory_search_parser.set_defaults(func=cmd_memory_search)
    memory_get_parser = memory_sub.add_parser("get")
    memory_get_parser.add_argument("ref")
    memory_get_parser.set_defaults(func=cmd_memory_get)
    memory_propose_parser = memory_sub.add_parser("propose")
    memory_propose_parser.add_argument("--file", required=True)
    memory_propose_parser.add_argument("--summary", required=False, default=None)
    memory_propose_parser.set_defaults(func=cmd_memory_propose)
    memory_publish_parser = memory_sub.add_parser("publish")
    memory_publish_parser.add_argument("proposal_id")
    memory_publish_parser.add_argument("--digest", required=True)
    memory_publish_parser.set_defaults(func=cmd_memory_publish)
    memory_reject_parser = memory_sub.add_parser("reject")
    memory_reject_parser.add_argument("proposal_id")
    memory_reject_parser.add_argument("--reason", required=False, default=None)
    memory_reject_parser.set_defaults(func=cmd_memory_reject)
    memory_block_parser = memory_sub.add_parser("block")
    memory_block_parser.add_argument("ref")
    memory_block_parser.set_defaults(func=cmd_memory_block)

    session_parser = sub.add_parser("session")
    session_sub = session_parser.add_subparsers(dest="session_command", required=True)
    session_start_parser = session_sub.add_parser("start")
    session_start_parser.add_argument("--title", required=False, default=None)
    session_start_parser.add_argument("--expires-at", required=False, default=None)
    session_start_parser.set_defaults(func=cmd_session_start)
    session_append_parser = session_sub.add_parser("append")
    session_append_parser.add_argument("session_id")
    session_append_parser.add_argument("--role", required=True)
    session_append_parser.add_argument("--json", required=True)
    session_append_parser.add_argument("--summary", required=False, default=None)
    session_append_parser.set_defaults(func=cmd_session_append)
    session_show_parser = session_sub.add_parser("show")
    session_show_parser.add_argument("session_id")
    session_show_parser.set_defaults(func=cmd_session_show)
    session_summarize_parser = session_sub.add_parser("summarize")
    session_summarize_parser.add_argument("session_id")
    session_summarize_parser.add_argument("--summary", required=False, default=None)
    session_summarize_parser.set_defaults(func=cmd_session_summarize)

    episodic_parser = sub.add_parser("episodic")
    episodic_sub = episodic_parser.add_subparsers(dest="episodic_command", required=True)
    episodic_search_parser = episodic_sub.add_parser("search")
    episodic_search_parser.add_argument("query")
    episodic_search_parser.add_argument("--run-id", required=False, default=None)
    episodic_search_parser.set_defaults(func=cmd_episodic_search)
    episodic_timeline_parser = episodic_sub.add_parser("timeline")
    episodic_timeline_parser.add_argument("run_id")
    episodic_timeline_parser.set_defaults(func=cmd_episodic_timeline)

    llm_parser = sub.add_parser("llm")
    llm_sub = llm_parser.add_subparsers(dest="llm_command", required=True)

    servers_parser = llm_sub.add_parser("servers")
    servers_parser.set_defaults(func=cmd_llm_servers)

    models_parser = llm_sub.add_parser("models")
    models_parser.set_defaults(func=cmd_llm_models)

    acquire_parser = llm_sub.add_parser("acquire")
    acquire_parser.set_defaults(func=cmd_llm_acquire)

    select_parser = llm_sub.add_parser("select")
    select_parser.add_argument("server_id")
    select_parser.add_argument("--model", required=False, default=None)
    select_parser.add_argument("--allow-remote", action="store_true")
    select_parser.set_defaults(func=cmd_llm_select)

    serve_sub_parser = llm_sub.add_parser("serve")
    serve_sub_parser.add_argument("action", choices=["start", "stop", "status"])
    serve_sub_parser.set_defaults(func=cmd_llm_serve)

    secret_parser = sub.add_parser("secret")
    secret_parser.add_argument("secret_args", nargs=argparse.REMAINDER)
    secret_parser.set_defaults(is_secret=True)

    serve_parser = sub.add_parser("serve")
    serve_parser.add_argument("--stdio", action="store_true")
    serve_parser.set_defaults(func=cmd_serve)

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
        except CoreOpError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
    finally:
        conn.close()


def main() -> int:
    return run(sys.argv[1:], REPO_ROOT)


if __name__ == "__main__":
    sys.exit(main())
