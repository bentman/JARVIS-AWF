"""Idempotent creation of data/awf_db/awf.db (Phase 0 exit condition)."""

from pathlib import Path

from awf.db.connection import get_connection
from awf.db.schema import DDL_STATEMENTS

# Columns added to an existing table after its original CREATE TABLE - a
# real, pre-existing local database predates the column and
# `CREATE TABLE IF NOT EXISTS` alone never adds it. Checked and applied on
# every `init_db` call; a no-op once the column is already there.
_COLUMN_MIGRATIONS = [
    ("approvals", "risk_class", "TEXT CHECK (risk_class IS NULL OR risk_class IN ('R0', 'R1', 'R2', 'R3'))"),
]


def _apply_column_migrations(conn) -> None:
    for table, column, ddl_type in _COLUMN_MIGRATIONS:
        existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}")


def _registry_proposals_accepts_semantic_memories(conn) -> bool:
    row = conn.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'registry_proposals'").fetchone()
    return row is None or "semantic-memories" in (row[0] or "")


def _registry_proposal_events_accepts_verified(conn) -> bool:
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'registry_proposal_events'"
    ).fetchone()
    return row is None or "verified" in (row[0] or "")


def _migrate_registry_proposals_kind_constraint(conn) -> None:
    if _registry_proposals_accepts_semantic_memories(conn):
        return
    foreign_keys_enabled = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    conn.commit()
    conn.execute("PRAGMA foreign_keys = OFF")
    has_events = (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'registry_proposal_events'"
        ).fetchone()
        is not None
    )
    if has_events:
        conn.execute("ALTER TABLE registry_proposal_events RENAME TO registry_proposal_events_old")
    conn.execute("ALTER TABLE registry_proposals RENAME TO registry_proposals_old")
    conn.execute(
        """
        CREATE TABLE registry_proposals (
            proposal_id TEXT PRIMARY KEY,
            kind TEXT NOT NULL CHECK (kind IN ('workflows', 'semantic-memories')),
            name TEXT NOT NULL,
            version TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('draft', 'published', 'rejected')),
            draft_digest TEXT NOT NULL,
            draft_path TEXT NOT NULL,
            summary TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            decided_at TEXT,
            published_digest TEXT,
            rejection_reason TEXT
        )
        """
    )
    conn.execute(
        """
        INSERT INTO registry_proposals (
            proposal_id, kind, name, version, status, draft_digest, draft_path,
            summary, created_at, updated_at, decided_at, published_digest, rejection_reason
        )
        SELECT proposal_id, kind, name, version, status, draft_digest, draft_path,
            summary, created_at, updated_at, decided_at, published_digest, rejection_reason
        FROM registry_proposals_old
        """
    )
    conn.execute("DROP TABLE registry_proposals_old")
    if has_events:
        conn.execute(
            """
            CREATE TABLE registry_proposal_events (
                event_id TEXT PRIMARY KEY,
                proposal_id TEXT NOT NULL REFERENCES registry_proposals (proposal_id),
                event_type TEXT NOT NULL CHECK (event_type IN ('created', 'updated', 'verified', 'published', 'rejected')),
                occurred_at TEXT NOT NULL,
                actor TEXT NOT NULL,
                payload_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            INSERT INTO registry_proposal_events (
                event_id, proposal_id, event_type, occurred_at, actor, payload_json
            )
            SELECT event_id, proposal_id, event_type, occurred_at, actor, payload_json
            FROM registry_proposal_events_old
            """
        )
        conn.execute("DROP TABLE registry_proposal_events_old")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_registry_proposal_events_proposal_id "
            "ON registry_proposal_events (proposal_id)"
        )
    conn.commit()
    if foreign_keys_enabled:
        conn.execute("PRAGMA foreign_keys = ON")


def _migrate_registry_proposal_events_verified_constraint(conn) -> None:
    if _registry_proposal_events_accepts_verified(conn):
        return
    foreign_keys_enabled = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    conn.commit()
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("ALTER TABLE registry_proposal_events RENAME TO registry_proposal_events_old")
    conn.execute(
        """
        CREATE TABLE registry_proposal_events (
            event_id TEXT PRIMARY KEY,
            proposal_id TEXT NOT NULL REFERENCES registry_proposals (proposal_id),
            event_type TEXT NOT NULL CHECK (event_type IN ('created', 'updated', 'verified', 'published', 'rejected')),
            occurred_at TEXT NOT NULL,
            actor TEXT NOT NULL,
            payload_json TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        INSERT INTO registry_proposal_events (
            event_id, proposal_id, event_type, occurred_at, actor, payload_json
        )
        SELECT event_id, proposal_id, event_type, occurred_at, actor, payload_json
        FROM registry_proposal_events_old
        """
    )
    conn.execute("DROP TABLE registry_proposal_events_old")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_registry_proposal_events_proposal_id ON registry_proposal_events (proposal_id)"
    )
    conn.commit()
    if foreign_keys_enabled:
        conn.execute("PRAGMA foreign_keys = ON")


def init_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = get_connection(db_path)
    try:
        for statement in DDL_STATEMENTS:
            conn.execute(statement)
        _apply_column_migrations(conn)
        _migrate_registry_proposals_kind_constraint(conn)
        _migrate_registry_proposal_events_verified_constraint(conn)
        conn.commit()
    finally:
        conn.close()
