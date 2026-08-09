"""Semantic memory retrieval (ADR-0020)."""

import dataclasses
import sqlite3
from pathlib import Path

from awf.registry.index import index_row
from awf.registry.kinds import SEMANTIC_MEMORIES, object_path, version_names
from awf.registry.memory_profile import MemoryProfile, load_memory_profile
from awf.registry.resolve import CONFIG_ROOT, DATA_ROOT, resolve_registry_object
from awf.registry.semantic_memory import SemanticMemory, load_semantic_memory

DATA_CLASS_RANK = {"public": 0, "internal": 1, "confidential": 2}


def _load_profile(repo_root: Path, profile_ref: str) -> MemoryProfile:
    name, sep, version = profile_ref.partition("@")
    if not sep or not name or not version:
        raise ValueError(f"profile must be '<name>@<version>', got {profile_ref!r}")
    path, _source = resolve_registry_object(repo_root, "memory-profiles", name, version)
    return load_memory_profile(path)


def _score(query: str, memory: SemanticMemory) -> float:
    haystack = " ".join(
        [
            memory.metadata.name,
            memory.subject,
            memory.predicate,
            memory.value,
            memory.memory_type,
            memory.scope,
            memory.provenance.source_ref,
        ]
    ).lower()
    terms = [term for term in query.lower().split() if term]
    if not terms:
        return 1.0
    hits = sum(1 for term in terms if term in haystack)
    return hits / len(terms)


def _iter_memory_paths(repo_root: Path):
    data_kind_dir = repo_root / DATA_ROOT / "semantic-memories"
    data_names = {path.name for path in data_kind_dir.iterdir() if path.is_dir()} if data_kind_dir.is_dir() else set()
    for source, root in (("data", repo_root / DATA_ROOT), ("config", repo_root / CONFIG_ROOT)):
        kind_dir = root / "semantic-memories"
        if not kind_dir.is_dir():
            continue
        for name_dir in sorted(path for path in kind_dir.iterdir() if path.is_dir()):
            if source == "config" and name_dir.name in data_names:
                continue
            for version in version_names(name_dir, SEMANTIC_MEMORIES):
                yield source, object_path(name_dir, SEMANTIC_MEMORIES, version)


def search_semantic_memories(
    repo_root: Path,
    conn: sqlite3.Connection,
    *,
    query: str,
    profile_ref: str = "default@1.0.0",
) -> list[dict]:
    profile = _load_profile(repo_root, profile_ref)
    if not profile.enabled or not profile.retrieval.include_semantic:
        return []

    max_rank = DATA_CLASS_RANK[profile.maximum_data_class]
    results = []
    for source, path in _iter_memory_paths(repo_root):
        memory = load_semantic_memory(path)
        if not memory.enabled or memory.confidence < profile.retrieval.min_confidence:
            continue
        if DATA_CLASS_RANK[memory.data_classification] > max_rank:
            continue
        row = index_row(conn, "semantic-memories", memory.metadata.name, memory.metadata.version)
        if row and row["trust_status"] == "blocked":
            continue
        score = _score(query, memory)
        if query and score == 0:
            continue
        results.append(
            {
                "kind": "semantic-memories",
                "name": memory.metadata.name,
                "version": memory.metadata.version,
                "ref": memory.ref,
                "source": source,
                "digest": row["digest"] if row else None,
                "trust_status": row["trust_status"] if row else None,
                "score": score,
                "confidence": memory.confidence,
                "object": dataclasses.asdict(memory),
            }
        )
    results.sort(key=lambda item: (item["score"], item["confidence"], item["ref"]), reverse=True)
    return results[: profile.retrieval.max_items]
