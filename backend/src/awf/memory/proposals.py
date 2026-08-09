"""Semantic-memory proposal helpers (ADR-0020)."""

import hashlib
import json
import sqlite3
from pathlib import Path

import yaml

from awf.clock import utc_now_rfc3339
from awf.ids import uuid7
from awf.paths import proposals_dir
from awf.registry.semantic_memory import parse_semantic_memory


class MemoryProposalError(RuntimeError):
    pass


def _event(conn: sqlite3.Connection, proposal_id: str, event_type: str, payload: dict, *, actor: str = "operator") -> None:
    conn.execute(
        "INSERT INTO registry_proposal_events "
        "(event_id, proposal_id, event_type, occurred_at, actor, payload_json) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (uuid7(), proposal_id, event_type, utc_now_rfc3339(), actor, json.dumps(payload, sort_keys=True)),
    )


def propose_semantic_memory(repo_root: Path, conn: sqlite3.Connection, *, path: Path, summary: str | None = None) -> dict:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise MemoryProposalError(f"{path}: semantic memory proposal must be a YAML mapping")
    memory = parse_semantic_memory(raw)
    content = yaml.safe_dump(raw, sort_keys=False).encode("utf-8")
    draft_digest = hashlib.sha256(content).hexdigest()
    proposal_id = uuid7()
    draft_path = proposals_dir(repo_root) / "semantic-memories" / proposal_id / memory.metadata.name / f"{memory.metadata.version}.yaml"
    draft_path.parent.mkdir(parents=True, exist_ok=True)
    draft_path.write_bytes(content)
    rel_path = str(draft_path.relative_to(repo_root))
    now = utc_now_rfc3339()
    conn.execute(
        "INSERT INTO registry_proposals "
        "(proposal_id, kind, name, version, status, draft_digest, draft_path, summary, created_at, updated_at) "
        "VALUES (?, 'semantic-memories', ?, ?, 'draft', ?, ?, ?, ?, ?)",
        (
            proposal_id,
            memory.metadata.name,
            memory.metadata.version,
            draft_digest,
            rel_path,
            summary or f"Semantic memory proposal {memory.ref}",
            now,
            now,
        ),
    )
    _event(conn, proposal_id, "created", {"draft_digest": draft_digest, "path": rel_path})
    conn.commit()
    from awf.authoring.workflow import get_proposal

    return get_proposal(repo_root, conn, proposal_id=proposal_id)
