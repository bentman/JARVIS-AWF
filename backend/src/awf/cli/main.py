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


def cmd_run(args: argparse.Namespace, repo_root: Path, conn) -> int:
    input_data = json.loads(Path(args.input).read_text()) if args.input else {}
    result = ops.op_run_start(repo_root, conn, workflow_ref=args.workflow, input_data=input_data)
    _print(result)
    return 0 if result.get("status") == "SUCCEEDED" else 1


def cmd_status(args: argparse.Namespace, repo_root: Path, conn) -> int:
    _print(ops.op_run_status(conn, run_id=args.run_id))
    return 0


def cmd_resume(args: argparse.Namespace, repo_root: Path, conn) -> int:
    _print(ops.op_run_resume(repo_root, conn))
    return 0


def cmd_approvals(args: argparse.Namespace, repo_root: Path, conn) -> int:
    _print(ops.op_approval_list(conn))
    return 0


def cmd_approve(args: argparse.Namespace, repo_root: Path, conn) -> int:
    _print(ops.op_approval_approve(conn, approval_id=args.approval_id))
    return 0


def cmd_reject(args: argparse.Namespace, repo_root: Path, conn) -> int:
    _print(ops.op_approval_reject(conn, approval_id=args.approval_id, reason=args.reason))
    return 0


def cmd_artifacts(args: argparse.Namespace, repo_root: Path, conn) -> int:
    _print(ops.op_artifact_list(conn, run_id=args.run_id))
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
    run_parser.add_argument("--input", required=False, default=None)
    run_parser.set_defaults(func=cmd_run)

    status_parser = sub.add_parser("status")
    status_parser.add_argument("run_id")
    status_parser.set_defaults(func=cmd_status)

    resume_parser = sub.add_parser("resume")
    resume_parser.set_defaults(func=cmd_resume)

    approvals_parser = sub.add_parser("approvals")
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
    artifacts_parser.set_defaults(func=cmd_artifacts)

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
