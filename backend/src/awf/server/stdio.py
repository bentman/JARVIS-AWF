"""`awf system serve --stdio` (Section 16.3, ADR-0029): JSON-RPC 2.0 over stdio.

Plain JSON-RPC 2.0 request/response framing, one JSON object per line.
Method names and dispatch are generated from `awf.protocol.methods`; this
module owns only transport framing, connection lifecycle, and JSON-RPC errors.
"""

import json
import sys
import threading
from pathlib import Path

from awf.db.bootstrap import init_db
from awf.db.connection import get_connection
from awf.paths import db_path as resolve_db_path
from awf.server import protocol_generated

_CONNECTION_LOCK = threading.Lock()
METHOD_NAMES = protocol_generated.METHOD_NAMES
DISPATCH_TABLE = protocol_generated.DISPATCH_TABLE

METHOD_NOT_FOUND = -32601
PARSE_ERROR = -32700
INTERNAL_ERROR = -32000


class JsonRpcError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def dispatch(repo_root: Path, conn, method: str, params: dict):
    handler = DISPATCH_TABLE.get(method)
    if handler is None:
        raise JsonRpcError(METHOD_NOT_FOUND, f"unknown method: {method}")
    return handler(repo_root, conn, params)


def handle_line(repo_root: Path, conn, line: str, out_stream, write_lock=None) -> None:
    try:
        request = json.loads(line)
    except json.JSONDecodeError:
        _write(
            out_stream,
            {"jsonrpc": "2.0", "id": None, "error": {"code": PARSE_ERROR, "message": "parse error"}},
            write_lock,
        )
        return

    request_id = request.get("id")
    method = request.get("method")
    params = request.get("params") or {}

    try:
        result = dispatch(repo_root, conn, method, params)
        _write(out_stream, {"jsonrpc": "2.0", "id": request_id, "result": result}, write_lock)
    except JsonRpcError as exc:
        _write(
            out_stream,
            {"jsonrpc": "2.0", "id": request_id, "error": {"code": exc.code, "message": exc.message}},
            write_lock,
        )
    except Exception as exc:
        _write(
            out_stream,
            {"jsonrpc": "2.0", "id": request_id, "error": {"code": INTERNAL_ERROR, "message": str(exc)}},
            write_lock,
        )


def _write(out_stream, payload: dict, write_lock=None) -> None:
    def write() -> None:
        out_stream.write(json.dumps(payload, default=str) + "\n")
        out_stream.flush()

    if write_lock is None:
        write()
        return
    with write_lock:
        write()


def _handle_line_with_fresh_connection(repo_root: Path, db_path: Path, line: str, out_stream, write_lock) -> None:
    with _CONNECTION_LOCK:
        conn = get_connection(db_path, enable_wal=False)
    try:
        handle_line(repo_root, conn, line, out_stream, write_lock)
    finally:
        conn.close()


def serve_stdio(repo_root: Path, *, in_stream=None, out_stream=None) -> None:
    in_stream = in_stream if in_stream is not None else sys.stdin
    out_stream = out_stream if out_stream is not None else sys.stdout

    db_path = resolve_db_path(repo_root)
    init_db(db_path)
    write_lock = threading.Lock()
    for line in in_stream:
        line = line.strip()
        if not line:
            continue
        _handle_line_with_fresh_connection(repo_root, db_path, line, out_stream, write_lock)
