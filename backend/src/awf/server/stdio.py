"""`awf serve --stdio` (Section 16.3): JSON-RPC 2.0 over stdio.

Plain JSON-RPC 2.0 request/response framing, one JSON object per line. Every
method maps 1:1 onto a 16.1 operation or a Section 8 table read (via
`awf.cli.core_ops`, the same functions the CLI calls). Full ACP shaping
(sessions, streamed content blocks, the official `agent-client-protocol`
SDK) is a separate presentation layer that can sit on top of these same
method bodies without changing what each one does.

`awf/events.subscribe` is a server-push stream in the spec; this
request/response-per-line transport cannot express that, so it responds
with a method-not-found-shaped error rather than pretending to stream.
"""

import json
import sys
from pathlib import Path

from awf.cli import core_ops as ops
from awf.db.bootstrap import init_db
from awf.db.connection import get_connection
from awf.paths import artifacts_dir
from awf.paths import db_path as resolve_db_path

METHOD_NAMES = (
    "awf/run.start",
    "awf/run.status",
    "awf/run.list",
    "awf/run.resume",
    "awf/approval.list",
    "awf/approval.approve",
    "awf/approval.reject",
    "awf/artifact.list",
    "awf/artifact.read",
    "awf/registry.list",
    "awf/registry.get",
    "awf/registry.validate",
    "awf/registry.publish",
    "awf/registry.reindex",
    "awf/registry.retire",
    "awf/registry.trust",
    "awf/workflow.authorDraft",
    "awf/proposal.get",
    "awf/proposal.update",
    "awf/proposal.publish",
    "awf/proposal.reject",
    "awf/secret.set",
    "awf/secret.listNames",
    "awf/events.subscribe",
)

METHOD_NOT_FOUND = -32601
PARSE_ERROR = -32700
INTERNAL_ERROR = -32000


class JsonRpcError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def dispatch(repo_root: Path, conn, method: str, params: dict):
    if method == "awf/run.start":
        return ops.op_run_start(repo_root, conn, workflow_ref=params["workflow"], input_data=params.get("input", {}))
    if method == "awf/run.status":
        return ops.op_run_status(conn, run_id=params["runId"])
    if method == "awf/run.list":
        return ops.op_run_list(conn)
    if method == "awf/run.resume":
        return ops.op_run_resume(repo_root, conn)
    if method == "awf/approval.list":
        return ops.op_approval_list(conn)
    if method == "awf/approval.approve":
        return ops.op_approval_approve(
            conn,
            approval_id=params["approvalId"],
            channel=params.get("channel", "manual"),
            risk_class=params.get("riskClass"),
        )
    if method == "awf/approval.reject":
        return ops.op_approval_reject(conn, approval_id=params["approvalId"], reason=params.get("reason", ""))
    if method == "awf/artifact.list":
        return ops.op_artifact_list(conn, run_id=params["runId"])
    if method == "awf/artifact.read":
        return ops.op_artifact_read(conn, artifact_id=params["artifactId"], artifacts_root=artifacts_dir(repo_root))
    if method == "awf/registry.list":
        return ops.op_registry_list(repo_root, kind=params["kind"], conn=conn)
    if method == "awf/registry.get":
        return ops.op_registry_get(repo_root, conn, kind=params["kind"], name=params["name"], version=params["version"])
    if method == "awf/registry.validate":
        return ops.op_registry_validate(Path(params["path"]), kind=params.get("kind"))
    if method == "awf/registry.publish":
        return ops.op_registry_publish(repo_root, conn, path=Path(params["path"]), kind=params["kind"])
    if method == "awf/registry.reindex":
        return ops.op_registry_reindex(repo_root, conn)
    if method == "awf/registry.retire":
        return ops.op_registry_retire(conn, kind=params["kind"], name=params["name"], version=params["version"])
    if method == "awf/registry.trust":
        return ops.op_registry_trust(
            conn, kind=params["kind"], name=params["name"], version=params["version"], status=params["status"]
        )
    if method == "awf/workflow.authorDraft":
        return ops.op_workflow_author_draft(
            repo_root,
            conn,
            objective=params["objective"],
            name=params.get("name"),
            version=params.get("version"),
            profile_ref=params.get("profile", ops.workflow_authoring.DEFAULT_AUTHOR_PROFILE),
        )
    if method == "awf/proposal.get":
        return ops.op_proposal_get(repo_root, conn, proposal_id=params["proposalId"])
    if method == "awf/proposal.update":
        return ops.op_proposal_update(
            repo_root,
            conn,
            proposal_id=params["proposalId"],
            content=params["content"],
            summary=params.get("summary"),
        )
    if method == "awf/proposal.publish":
        return ops.op_proposal_publish(repo_root, conn, proposal_id=params["proposalId"], digest=params["digest"])
    if method == "awf/proposal.reject":
        return ops.op_proposal_reject(repo_root, conn, proposal_id=params["proposalId"], reason=params.get("reason"))
    if method == "awf/secret.set":
        return ops.op_secret_set(repo_root, conn, name=params["name"], value=params["value"])
    if method == "awf/secret.listNames":
        return ops.op_secret_list_names(conn)
    if method == "awf/events.subscribe":
        raise JsonRpcError(
            METHOD_NOT_FOUND,
            "awf/events.subscribe requires a streaming transport, not implemented over request/response stdio",
        )
    raise JsonRpcError(METHOD_NOT_FOUND, f"unknown method: {method}")


def handle_line(repo_root: Path, conn, line: str, out_stream) -> None:
    try:
        request = json.loads(line)
    except json.JSONDecodeError:
        _write(out_stream, {"jsonrpc": "2.0", "id": None, "error": {"code": PARSE_ERROR, "message": "parse error"}})
        return

    request_id = request.get("id")
    method = request.get("method")
    params = request.get("params") or {}

    try:
        result = dispatch(repo_root, conn, method, params)
        _write(out_stream, {"jsonrpc": "2.0", "id": request_id, "result": result})
    except JsonRpcError as exc:
        _write(out_stream, {"jsonrpc": "2.0", "id": request_id, "error": {"code": exc.code, "message": exc.message}})
    except Exception as exc:
        _write(out_stream, {"jsonrpc": "2.0", "id": request_id, "error": {"code": INTERNAL_ERROR, "message": str(exc)}})


def _write(out_stream, payload: dict) -> None:
    out_stream.write(json.dumps(payload, default=str) + "\n")
    out_stream.flush()


def serve_stdio(repo_root: Path, *, in_stream=None, out_stream=None) -> None:
    in_stream = in_stream if in_stream is not None else sys.stdin
    out_stream = out_stream if out_stream is not None else sys.stdout

    db_path = resolve_db_path(repo_root)
    init_db(db_path)
    conn = get_connection(db_path)

    try:
        for line in in_stream:
            line = line.strip()
            if not line:
                continue
            handle_line(repo_root, conn, line, out_stream)
    finally:
        conn.close()
