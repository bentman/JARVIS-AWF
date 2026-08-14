"""Prompt-envelope memory context assembly (ADR-0020)."""

import json
import sqlite3
from pathlib import Path

from awf.cognition.envelope import PromptSegment
from awf.memory.episodic import search_events
from awf.memory.semantic import search_semantic_memories
from awf.registry.memory_profile import load_memory_profile
from awf.registry.resolve import resolve_registry_object


def _profile(repo_root: Path, profile_ref: str, conn: sqlite3.Connection | None = None):
    name, _, version = profile_ref.partition("@")
    path, _source = resolve_registry_object(repo_root, "memory-profiles", name, version, conn=conn)
    return load_memory_profile(path)


def _estimated_tokens(text: str) -> int:
    return max(1, (len(text) + 3) // 4)


def _semantic_line(result: dict) -> str:
    title = result.get("title") or result.get("key") or result.get("memory_id") or "semantic memory"
    text = result.get("text") or result.get("content") or result.get("summary") or json.dumps(result, sort_keys=True)
    confidence = result.get("confidence")
    prefix = f"{title}: {text}"
    if confidence is not None:
        return f"{prefix} (confidence={confidence})"
    return prefix


def _event_line(result: dict) -> str:
    actor = result.get("actor") or result.get("role") or result.get("reason_code") or "event"
    text = result.get("summary") or result.get("content") or result.get("payload") or result.get("payload_json")
    if text is None:
        text = json.dumps(result, sort_keys=True)
    if not isinstance(text, str):
        text = json.dumps(text, sort_keys=True)
    return f"{actor}: {text}"


def _append_budgeted(segments: list[PromptSegment], authority: str, text: str, remaining_tokens: int) -> int:
    cost = _estimated_tokens(text)
    if cost > remaining_tokens:
        return remaining_tokens
    segments.append(PromptSegment(authority, "context", False, text))
    return remaining_tokens - cost


def retrieve_memory_context(
    repo_root: Path,
    conn: sqlite3.Connection,
    *,
    query: str,
    profile_ref: str = "default@1.0.0",
) -> tuple[PromptSegment, ...]:
    profile = _profile(repo_root, profile_ref, conn)
    segments: list[PromptSegment] = []
    remaining = profile.retrieval.max_tokens

    if profile.retrieval.include_semantic:
        for result in search_semantic_memories(repo_root, conn, query=query, profile_ref=profile_ref):
            if len(segments) >= profile.retrieval.max_items:
                break
            remaining_after = _append_budgeted(segments, "memory", _semantic_line(result), remaining)
            if remaining_after == remaining:
                continue
            remaining = remaining_after

    if profile.retrieval.include_episodic and len(segments) < profile.retrieval.max_items:
        for result in search_events(conn, query=query, limit=profile.retrieval.max_items - len(segments)):
            remaining_after = _append_budgeted(segments, "retrieval", _event_line(result), remaining)
            if remaining_after == remaining:
                continue
            remaining = remaining_after

    return tuple(segments)
