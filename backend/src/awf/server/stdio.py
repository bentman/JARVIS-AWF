"""`awf serve --stdio` (Section 16.3): JSON-RPC 2.0 over stdio.

Plain JSON-RPC 2.0 request/response framing, one JSON object per line. Full
ACP shaping (sessions, streamed content blocks, the official
`agent-client-protocol` SDK) is not implemented in this phase - every method
below already maps 1:1 onto a 16.1 operation or a Section 8 table read
(via `awf.cli.core_ops`, the same functions the CLI calls), so an ACP layer
can be added later without changing what each method does.

`awf/events.subscribe` is a server-push stream in the spec; this
request/response-per-line transport can't express that yet, so it responds
with a method-not-found-shaped error rather than pretending to stream.
"""

import json
import sys
from pathlib import Path

from awf.cli import core_ops as ops
from awf.db.bootstrap import init_db
from awf.db.connection import get_connection

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
        return ops.op_approval_approve(conn, approval_id=params["approvalId"])
    if method == "awf/approval.reject":
        return ops.op_approval_reject(conn, approval_id=params["approvalId"], reason=params.get("reason", ""))
    if method == "awf/artifact.list":
        return ops.op_artifact_list(conn, run_id=params["runId"])
    if method == "awf/artifact.read":
        return ops.op_artifact_read(
            conn, artifact_id=params["artifactId"], artifacts_root=repo_root / "data" / "artifacts"
        )
    if method == "awf/registry.list":
        return ops.op_registry_list(repo_root, kind=params["kind"])
    if method == "awf/registry.get":
        return ops.op_registry_get(repo_root, kind=params["kind"], name=params["name"], version=params["version"])
    if method == "awf/registry.validate":
        return ops.op_registry_validate(Path(params["path"]))
    if method == "awf/registry.publish":
        return ops.op_registry_publish(repo_root, conn, path=Path(params["path"]))
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
    except Exception as exc:  # noqa: BLE001 - JSON-RPC boundary: a bad request must not crash the server
        _write(out_stream, {"jsonrpc": "2.0", "id": request_id, "error": {"code": INTERNAL_ERROR, "message": str(exc)}})


def _write(out_stream, payload: dict) -> None:
    out_stream.write(json.dumps(payload, default=str) + "\n")
    out_stream.flush()


def serve_stdio(repo_root: Path, *, in_stream=None, out_stream=None) -> None:
    in_stream = in_stream if in_stream is not None else sys.stdin
    out_stream = out_stream if out_stream is not None else sys.stdout

    db_path = repo_root / "data" / "awf_db" / "awf.db"
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
