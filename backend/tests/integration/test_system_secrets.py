import pytest
from backend.tests.support import make_db
from cryptography.fernet import Fernet, InvalidToken

from awf.db.bootstrap import init_db
from awf.db.connection import get_connection
from awf.secrets import cli as secrets_cli
from awf.secrets.store import (
    SecretNotFoundError,
    get_secret,
    list_secret_names,
    rotate_key,
    set_secret,
)


def test_set_get_round_trip(tmp_path):
    conn = make_db(tmp_path)
    key = Fernet.generate_key()
    set_secret(conn, "api-key", "sekret-value", key)
    assert get_secret(conn, "api-key", key) == "sekret-value"


def test_get_secret_raises_for_missing_name(tmp_path):
    conn = make_db(tmp_path)
    key = Fernet.generate_key()
    with pytest.raises(SecretNotFoundError):
        get_secret(conn, "does-not-exist", key)


def test_round_trip_survives_process_restart(tmp_path):
    db_path = tmp_path / "awf.db"
    init_db(db_path)
    key = Fernet.generate_key()

    conn = get_connection(db_path)
    set_secret(conn, "api-key", "sekret-value", key)
    conn.close()

    # simulate a restart: fresh connection, key re-read as if from .env
    conn2 = get_connection(db_path)
    assert get_secret(conn2, "api-key", key) == "sekret-value"
    conn2.close()


def test_list_shows_names_only(tmp_path):
    conn = make_db(tmp_path)
    key = Fernet.generate_key()
    set_secret(conn, "b-key", "v1", key)
    set_secret(conn, "a-key", "v2", key)
    assert list_secret_names(conn) == ["a-key", "b-key"]


def test_set_is_overwrite_only_no_partial_update(tmp_path, monkeypatch):
    conn = make_db(tmp_path)
    key = Fernet.generate_key()

    timestamps = iter(["2026-01-01T00:00:00Z", "2026-01-01T00:05:00Z"])
    monkeypatch.setattr("awf.secrets.store.utc_now_rfc3339", lambda: next(timestamps))

    set_secret(conn, "api-key", "v1", key)
    set_secret(conn, "api-key", "v2", key)

    row = conn.execute("SELECT created_at, updated_at FROM secrets WHERE name = 'api-key'").fetchone()
    assert tuple(row) == ("2026-01-01T00:00:00Z", "2026-01-01T00:05:00Z")
    assert get_secret(conn, "api-key", key) == "v2"
    assert conn.execute("SELECT COUNT(*) FROM secrets").fetchone()[0] == 1


def test_rotate_key_reencrypts_and_invalidates_old_key(tmp_path):
    conn = make_db(tmp_path)
    old_key = Fernet.generate_key()
    new_key = Fernet.generate_key()

    set_secret(conn, "api-key", "sekret-value", old_key)
    rotate_key(conn, old_key, new_key)

    assert get_secret(conn, "api-key", new_key) == "sekret-value"
    with pytest.raises(InvalidToken):
        get_secret(conn, "api-key", old_key)


@pytest.fixture
def fake_repo(tmp_path):
    key = Fernet.generate_key().decode("ascii")
    (tmp_path / ".env").write_text(f"AWF_SECRET_KEY={key}\n")
    return tmp_path


def test_cli_set_then_list(fake_repo, monkeypatch, capsys):
    monkeypatch.setattr(secrets_cli.getpass, "getpass", lambda prompt: "sekret-value")
    secrets_cli.run(["set", "api-key"], fake_repo)

    secrets_cli.run(["list"], fake_repo)
    out = capsys.readouterr().out
    assert out == "api-key\n"


def test_cli_rotate_key_updates_env_and_data(fake_repo, monkeypatch):
    monkeypatch.setattr(secrets_cli.getpass, "getpass", lambda prompt: "sekret-value")
    secrets_cli.run(["set", "api-key"], fake_repo)

    old_key = secrets_cli._load_key(fake_repo)
    secrets_cli.run(["rotate-key"], fake_repo)
    new_key = secrets_cli._load_key(fake_repo)

    assert new_key != old_key

    conn = get_connection(secrets_cli.db_path(fake_repo))
    try:
        assert get_secret(conn, "api-key", new_key) == "sekret-value"
        with pytest.raises(InvalidToken):
            get_secret(conn, "api-key", old_key)
    finally:
        conn.close()
