"""Prompt-envelope memory context assembly (ADR-0020)."""

import json
import sqlite3
from pathlib import Path

from awf.cognition.envelope import PromptSegment
from awf.memory.episodic import search_events
from awf.memory.semantic import search_semantic_memories
from awf.registry.memory_profile import load_memory_profile
from awf.registry.resolve import resolve_registry_object


def _profile(repo_root: Path, profile_ref: str):
    name, _, version = profile_ref.partition("@")
    path, _source = resolve_registry_object(repo_root, "memory-profiles", name, version)
    return load_memory_profile(path)


def retrieve_memory_context(
    repo_root: Path,
    conn: sqlite3.Connection,
    *,
    query: str,
    profile_ref: str = "default@1.0.0",
) -> tuple[PromptSegment, ...]:
    profile = _profile(repo_root, profile_ref)
    segments: list[PromptSegment] = []
    remaining = profile.retrieval.max_tokens

    if profile.retrieval.include_semantic:
        for result in search_semantic_memories(repo_root, conn, query=query, profile_ref=profile_ref):
            text = json.dumps(result, sort_keys=True)
            if len(text) > remaining:
                break
            segments.append(PromptSegment("memory", "context", False, text))
            remaining -= len(text)

    if profile.retrieval.include_episodic and len(segments) < profile.retrieval.max_items:
        for result in search_events(conn, query=query, limit=profile.retrieval.max_items - len(segments)):
            text = json.dumps(result, sort_keys=True)
            if len(text) > remaining:
                break
            segments.append(PromptSegment("retrieval", "context", False, text))
            remaining -= len(text)

    return tuple(segments)
