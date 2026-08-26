"""The `awf` core CLI (Section 16.1): a thin wrapper over Phases 0-9.

No command may bypass the Capability Guard, mark a Gate as passed, or
invoke an unregistered adapter - this module only orchestrates; every
mutation flows through `awf.ops.*`, the same operation functions
`awf serve --stdio` calls (Section 16.3: "the protocol adds no authority").
"""

import argparse
import json
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
        "args": ({"flags": ("run_id",)}, {"flags": ("--json",), "action": "store_true"}),
    },
    {"path": ("resume",), "func": cmd_resume, "args": ({"flags": ("--json",), "action": "store_true"},)},
    {"path": ("runs",), "func": cmd_runs, "args": ({"flags": ("--json",), "action": "store_true"},)},
    {"path": ("approvals",), "func": cmd_approvals, "args": ({"flags": ("--json",), "action": "store_true"},)},
    {"path": ("approve",), "func": cmd_approve, "args": ({"flags": ("approval_id",)},)},
    {
        "path": ("reject",),
        "func": cmd_reject,
        "args": ({"flags": ("approval_id",)}, {"flags": ("--reason",), "required": True}),
    },
    {
        "path": ("artifacts",),
        "func": cmd_artifacts,
        "args": ({"flags": ("run_id",)}, {"flags": ("--json",), "action": "store_true"}),
    },
    {"path": ("readiness",), "func": cmd_readiness, "args": ({"flags": ("--json",), "action": "store_true"},)},
    {"path": ("doctor",), "func": cmd_doctor, "args": ({"flags": ("--json",), "action": "store_true"},)},
    {
        "path": ("improvement", "list"),
        "func": cmd_improvement_list,
        "args": ({"flags": ("--status",), "default": None},),
    },
    {"path": ("improvement", "show"), "func": cmd_improvement_show, "args": ({"flags": ("improvement_id",)},)},
    {
        "path": ("improvement", "prepare"),
        "func": cmd_improvement_prepare,
        "args": ({"flags": ("run_id",)}, {"flags": ("--summary",), "default": None}),
    },
    {
        "path": ("improvement", "mark-ready"),
        "func": cmd_improvement_mark_ready,
        "args": (
            {"flags": ("improvement_id",)},
            {"flags": ("--verdict-artifact-id",), "required": True},
            {"flags": ("--validation-artifact-id",), "action": "append", "default": []},
        ),
    },
    {
        "path": ("improvement", "request-merge"),
        "func": cmd_improvement_request_merge,
        "args": ({"flags": ("improvement_id",)},),
    },
    {
        "path": ("improvement", "merge"),
        "func": cmd_improvement_merge,
        "args": ({"flags": ("improvement_id",)}, {"flags": ("approval_id",)}),
    },
    {
        "path": ("improvement", "reject"),
        "func": cmd_improvement_reject,
        "args": ({"flags": ("improvement_id",)}, {"flags": ("--reason",), "default": None}),
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
        "path": ("author", "workflow"),
        "func": cmd_author_workflow,
        "args": (
            {"flags": ("--objective",), "required": True},
            {"flags": ("--name",), "default": None},
            {"flags": ("--version",), "default": None},
            {"flags": ("--profile",), "default": ops.workflow_authoring.DEFAULT_AUTHOR_PROFILE},
        ),
    },
    {"path": ("proposal", "show"), "func": cmd_proposal_show, "args": ({"flags": ("proposal_id",)},)},
    {
        "path": ("proposal", "update"),
        "func": cmd_proposal_update,
        "args": (
            {"flags": ("proposal_id",)},
            {"flags": ("--file",), "required": True},
            {"flags": ("--summary",), "default": None},
        ),
    },
    {
        "path": ("proposal", "publish"),
        "func": cmd_proposal_publish,
        "args": ({"flags": ("proposal_id",)}, {"flags": ("--digest",), "required": True}),
    },
    {
        "path": ("proposal", "reject"),
        "func": cmd_proposal_reject,
        "args": ({"flags": ("proposal_id",)}, {"flags": ("--reason",), "default": None}),
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
        "path": ("session", "start"),
        "func": cmd_session_start,
        "args": ({"flags": ("--title",), "default": None}, {"flags": ("--expires-at",), "default": None}),
    },
    {
        "path": ("session", "append"),
        "func": cmd_session_append,
        "args": (
            {"flags": ("session_id",)},
            {"flags": ("--role",), "required": True},
            {"flags": ("--json",), "required": True},
            {"flags": ("--summary",), "default": None},
        ),
    },
    {"path": ("session", "show"), "func": cmd_session_show, "args": ({"flags": ("session_id",)},)},
    {
        "path": ("session", "summarize"),
        "func": cmd_session_summarize,
        "args": ({"flags": ("session_id",)}, {"flags": ("--summary",), "default": None}),
    },
    {
        "path": ("episodic", "search"),
        "func": cmd_episodic_search,
        "args": ({"flags": ("query",)}, {"flags": ("--run-id",), "default": None}),
    },
    {"path": ("episodic", "timeline"), "func": cmd_episodic_timeline, "args": ({"flags": ("run_id",)},)},
    {"path": ("llm", "servers"), "func": cmd_llm_servers, "args": ()},
    {"path": ("llm", "models"), "func": cmd_llm_models, "args": ()},
    {"path": ("llm", "acquire"), "func": cmd_llm_acquire, "args": ()},
    {
        "path": ("llm", "select"),
        "func": cmd_llm_select,
        "args": (
            {"flags": ("server_id",)},
            {"flags": ("--model",), "default": None},
            {"flags": ("--allow-remote",), "action": "store_true"},
        ),
    },
    {
        "path": ("llm", "serve"),
        "func": cmd_llm_serve,
        "args": ({"flags": ("action",), "choices": ("start", "stop", "status")},),
    },
    {
        "path": ("secret",),
        "defaults": {"is_secret": True},
        "args": ({"flags": ("secret_args",), "nargs": "REMAINDER"},),
    },
    {"path": ("serve",), "func": cmd_serve, "args": ({"flags": ("--stdio",), "action": "store_true"},)},
)


def _argument_kwargs(spec: dict) -> dict:
    kwargs = {key: value for key, value in spec.items() if key not in {"flags", "group"}}
    if kwargs.get("nargs") == "REMAINDER":
        kwargs["nargs"] = argparse.REMAINDER
    return kwargs


def _install_cli_command(parsers: dict[tuple[str, ...], argparse.ArgumentParser], spec: dict) -> None:
    path = spec["path"]
    current_path: tuple[str, ...] = ()
    for index, part in enumerate(path):
        parent = parsers[current_path]
        subparsers = getattr(parent, "_awf_subparsers", None)
        if subparsers is None:
            dest = "command" if not current_path else f"{current_path[0]}_command"
            subparsers = parent.add_subparsers(dest=dest, required=True)
            parent._awf_subparsers = subparsers
        next_path = (*current_path, part)
        if next_path not in parsers:
            parsers[next_path] = subparsers.add_parser(part)
        current_path = next_path
        if index == len(path) - 1:
            parser = parsers[current_path]
            groups: dict[str, argparse._MutuallyExclusiveGroup] = {}
            for arg_spec in spec.get("args", ()):
                target = parser
                if group_name := arg_spec.get("group"):
                    groups.setdefault(group_name, parser.add_mutually_exclusive_group())
                    target = groups[group_name]
                target.add_argument(*arg_spec["flags"], **_argument_kwargs(arg_spec))
            parser.set_defaults(**spec.get("defaults", {}))
            if func := spec.get("func"):
                parser.set_defaults(func=func)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="awf")
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
        except CoreOpError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
    finally:
        conn.close()


def main() -> int:
    return run(sys.argv[1:], REPO_ROOT)


if __name__ == "__main__":
    sys.exit(main())
