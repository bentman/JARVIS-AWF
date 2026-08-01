import shutil
import sqlite3
from pathlib import Path

import pytest

from awf.db.bootstrap import init_db
from awf.db.schema import EXPECTED_TABLES
from awf.events.writer import write_event
from awf.ids import uuid7
from awf.setup import PLACEHOLDER, bootstrap_repo

REPO_ROOT = Path(__file__).resolve().parents[2]


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
    init_db(db_path)  # must not raise


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
def fake_repo(tmp_path):
    shutil.copy(REPO_ROOT / ".env.example", tmp_path / ".env.example")
    return tmp_path


def test_bootstrap_repo_populates_env(fake_repo):
    bootstrap_repo(fake_repo)

    env_content = (fake_repo / ".env").read_text()
    assert PLACEHOLDER not in env_content
    assert "AWF_SECRET_KEY=" in env_content


def test_bootstrap_repo_creates_cache_and_db(fake_repo):
    bootstrap_repo(fake_repo)

    assert (fake_repo / "cache" / "sandbox").is_dir()
    assert (fake_repo / "cache" / "temp").is_dir()
    assert (fake_repo / "data" / "awf_db" / "awf.db").is_file()


def test_bootstrap_repo_does_not_overwrite_existing_env(fake_repo):
    (fake_repo / ".env").write_text("AWF_SECRET_KEY=already-set\n")
    bootstrap_repo(fake_repo)

    assert (fake_repo / ".env").read_text() == "AWF_SECRET_KEY=already-set\n"
