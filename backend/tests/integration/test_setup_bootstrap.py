import shutil
import sqlite3

import pytest

from awf.db.bootstrap import init_db
from awf.db.schema import EXPECTED_TABLES
from awf.events.writer import write_event
from awf.ids import uuid7
from awf.setup import PLACEHOLDER, bootstrap_repo


def test_init_db_creates_all_tables(tmp_path):
    db_path = tmp_path / "awf.db"
    init_db(db_path)

    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    finally:
        conn.close()

    table_names = {row[0] for row in rows}
    for expected in EXPECTED_TABLES:
        assert expected in table_names


def test_init_db_is_idempotent(tmp_path):
    db_path = tmp_path / "awf.db"
    init_db(db_path)

    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO runs (run_id, workflow_ref, status, input_json, budget_json, created_at, updated_at) "
            "VALUES ('run-1', 'wf@1.0.0#sha256:abc', 'CREATED', '{}', '{}', 't', 't')"
        )
        conn.commit()
    finally:
        conn.close()

    init_db(db_path)  # must not raise, and must not touch existing data

    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute("SELECT run_id, status FROM runs WHERE run_id = 'run-1'").fetchone()
    finally:
        conn.close()
    assert row == ("run-1", "CREATED")


def test_init_db_migrates_a_pre_existing_db_missing_the_risk_class_column(tmp_path):
    # simulates a real, already-deployed database created before
    # `approvals.risk_class` existed - a plain CREATE TABLE IF NOT EXISTS
    # alone would never add the column to it.
    db_path = tmp_path / "awf.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE approvals (
                approval_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                step_id TEXT NOT NULL,
                action_digest TEXT NOT NULL,
                status TEXT NOT NULL,
                reason TEXT,
                requested_at TEXT NOT NULL,
                decided_at TEXT
            )
            """
        )
        conn.execute(
            "INSERT INTO approvals (approval_id, run_id, step_id, action_digest, status, requested_at) "
            "VALUES ('ap-1', 'run-1', 'step-1', 'sha256:abc', 'pending', 't')"
        )
        conn.commit()
    finally:
        conn.close()

    init_db(db_path)  # must not raise, must add the column, must not touch existing rows

    conn = sqlite3.connect(db_path)
    try:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(approvals)").fetchall()}
        row = conn.execute("SELECT approval_id, status FROM approvals WHERE approval_id = 'ap-1'").fetchone()
    finally:
        conn.close()
    assert "risk_class" in columns
    assert row == ("ap-1", "pending")


def test_init_db_migrates_registry_proposal_kind_constraint_and_preserves_events(tmp_path):
    db_path = tmp_path / "awf.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE registry_proposals (
                proposal_id TEXT PRIMARY KEY,
                kind TEXT NOT NULL CHECK (kind IN ('workflows')),
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
            CREATE TABLE registry_proposal_events (
                event_id TEXT PRIMARY KEY,
                proposal_id TEXT NOT NULL REFERENCES registry_proposals (proposal_id),
                event_type TEXT NOT NULL CHECK (event_type IN ('created', 'updated', 'published', 'rejected')),
                occurred_at TEXT NOT NULL,
                actor TEXT NOT NULL,
                payload_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "INSERT INTO registry_proposals "
            "(proposal_id, kind, name, version, status, draft_digest, draft_path, summary, created_at, updated_at) "
            "VALUES ('p1', 'workflows', 'demo', '1.0.0', 'draft', 'abc', 'draft.yaml', 'demo', 't', 't')"
        )
        conn.execute(
            "INSERT INTO registry_proposal_events "
            "(event_id, proposal_id, event_type, occurred_at, actor, payload_json) "
            "VALUES ('e1', 'p1', 'created', 't', 'test', '{}')"
        )
        conn.commit()
    finally:
        conn.close()

    init_db(db_path)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute(
            "INSERT INTO registry_proposals "
            "(proposal_id, kind, name, version, status, draft_digest, draft_path, summary, created_at, updated_at) "
            "VALUES ('p2', 'semantic-memories', 'memory', '1.0.0', 'draft', 'def', 'draft.yaml', 'memory', 't', 't')"
        )
        conn.execute(
            "INSERT INTO registry_proposal_events "
            "(event_id, proposal_id, event_type, occurred_at, actor, payload_json) "
            "VALUES ('e2', 'p1', 'verified', 't', 'verifier', '{}')"
        )
        proposal = conn.execute("SELECT * FROM registry_proposals WHERE proposal_id = 'p1'").fetchone()
        events = conn.execute("SELECT * FROM registry_proposal_events WHERE proposal_id = 'p1'").fetchall()
    finally:
        conn.close()

    assert proposal["kind"] == "workflows"
    assert {event["event_id"] for event in events} == {"e1", "e2"}


def test_uuid7_has_correct_version_and_variant():
    value = uuid7()
    assert value[14] == "7"
    assert value[19] in "89ab"


def test_write_event_appends_row(tmp_path):
    db_path = tmp_path / "awf.db"
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO runs (run_id, workflow_ref, status, input_json, budget_json, created_at, updated_at) "
            "VALUES ('run-1', 'wf@1.0.0#sha256:abc', 'CREATED', '{}', '{}', 't', 't')"
        )
        conn.commit()

        event_id = write_event(
            conn,
            run_id="run-1",
            new_status="CREATED",
            actor="test",
            reason_code="test_created",
        )

        rows = conn.execute("SELECT event_id, run_id FROM events").fetchall()
    finally:
        conn.close()

    assert rows == [(event_id, "run-1")]


@pytest.fixture
def fake_repo(tmp_path, repo_root):
    shutil.copy(repo_root / ".env.example", tmp_path / ".env.example")
    return tmp_path


def test_bootstrap_repo_populates_env(fake_repo):
    bootstrap_repo(fake_repo)

    env_content = (fake_repo / ".env").read_text()
    assert PLACEHOLDER not in env_content
    assert "AWF_SECRET_KEY=" in env_content


def test_bootstrap_repo_creates_cache_and_db(fake_repo):
    bootstrap_repo(fake_repo)

    assert (fake_repo / "cache" / "sandbox").is_dir()
    assert (fake_repo / "data" / "awf_db" / "awf.db").is_file()


def test_bootstrap_repo_does_not_overwrite_existing_env(fake_repo):
    (fake_repo / ".env").write_text("AWF_SECRET_KEY=already-set\n")
    bootstrap_repo(fake_repo)

    assert (fake_repo / ".env").read_text() == "AWF_SECRET_KEY=already-set\n"
