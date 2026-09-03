"""memory operation implementations."""

import sqlite3
from pathlib import Path

from awf.memory.context import retrieve_memory_context
from awf.memory.episodic import run_timeline, search_events
from awf.memory.proposals import MemoryProposalError, propose_semantic_memory
from awf.memory.semantic import search_semantic_memories
from awf.memory.sessions import (
    SessionError,
    append_entry,
    show_session,
    start_session,
    summarize_session,
)
from awf.ops.authoring import op_proposal_publish, op_proposal_reject
from awf.ops.registry import op_registry_get, op_registry_retire
from awf.ops.shared import CoreOpError


def _split_ref(ref: str) -> tuple[str, str]:
    name, sep, version = ref.partition("@")
    if not sep or not name or not version:
        raise CoreOpError(f"ref must be '<name>@<version>', got {ref!r}")
    return name, version


def op_memory_search(
    repo_root: Path,
    conn: sqlite3.Connection,
    *,
    query: str,
    profile_ref: str = "default@1.0.0",
) -> dict:
    try:
        semantic = search_semantic_memories(repo_root, conn, query=query, profile_ref=profile_ref)
        episodic = search_events(conn, query=query, limit=20)
        context = retrieve_memory_context(repo_root, conn, query=query, profile_ref=profile_ref)
    except ValueError as exc:
        raise CoreOpError(str(exc)) from exc
    return {"query": query, "profile_ref": profile_ref, "semantic": semantic, "episodic": episodic, "context": context}


def op_memory_get(repo_root: Path, conn: sqlite3.Connection, *, ref: str) -> dict:
    name, version = _split_ref(ref)
    return op_registry_get(repo_root, conn, kind="semantic-memories", name=name, version=version)


def op_memory_propose(repo_root: Path, conn: sqlite3.Connection, *, path: Path, summary: str | None = None) -> dict:
    try:
        return propose_semantic_memory(repo_root, conn, path=path, summary=summary)
    except MemoryProposalError as exc:
        raise CoreOpError(str(exc)) from exc


def op_memory_publish(repo_root: Path, conn: sqlite3.Connection, *, proposal_id: str, digest: str) -> dict:
    return op_proposal_publish(repo_root, conn, proposal_id=proposal_id, digest=digest)


def op_memory_reject(repo_root: Path, conn: sqlite3.Connection, *, proposal_id: str, reason: str | None = None) -> dict:
    return op_proposal_reject(repo_root, conn, proposal_id=proposal_id, reason=reason)


def op_memory_block(conn: sqlite3.Connection, *, ref: str) -> dict:
    name, version = _split_ref(ref)
    return op_registry_retire(conn, kind="semantic-memories", name=name, version=version)


def op_session_start(conn: sqlite3.Connection, *, title: str | None = None, expires_at: str | None = None) -> dict:
    return start_session(conn, title=title, expires_at=expires_at)


def op_session_append(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    role: str,
    content: dict,
    summary: str | None = None,
) -> dict:
    try:
        return append_entry(conn, session_id=session_id, role=role, content=content, summary=summary)
    except SessionError as exc:
        raise CoreOpError(str(exc)) from exc


def op_session_show(conn: sqlite3.Connection, *, session_id: str) -> dict:
    try:
        return show_session(conn, session_id=session_id)
    except SessionError as exc:
        raise CoreOpError(str(exc)) from exc


def op_session_summarize(conn: sqlite3.Connection, *, session_id: str, summary: str | None = None) -> dict:
    try:
        return summarize_session(conn, session_id=session_id, summary=summary)
    except SessionError as exc:
        raise CoreOpError(str(exc)) from exc


def op_episodic_search(conn: sqlite3.Connection, *, query: str, run_id: str | None = None) -> list[dict]:
    return search_events(conn, query=query, run_id=run_id)


def op_episodic_timeline(conn: sqlite3.Connection, *, run_id: str) -> dict:
    try:
        return run_timeline(conn, run_id=run_id)
    except ValueError as exc:
        raise CoreOpError(str(exc)) from exc


__all__ = (
    "op_episodic_search",
    "op_episodic_timeline",
    "op_memory_block",
    "op_memory_get",
    "op_memory_propose",
    "op_memory_publish",
    "op_memory_reject",
    "op_memory_search",
    "op_session_append",
    "op_session_show",
    "op_session_start",
    "op_session_summarize",
)
