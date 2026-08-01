"""The `secrets` table access function (Section 9.4).

Fernet, keyed by AWF_SECRET_KEY. Writes are overwrite-only — a set replaces
ciphertext and updated_at, never a partial edit. Rotation decrypts every row
with the old key and re-encrypts with a fresh key inside one transaction.
"""

import sqlite3

from cryptography.fernet import Fernet

from awf.clock import utc_now_rfc3339


class SecretNotFoundError(KeyError):
    pass


def set_secret(conn: sqlite3.Connection, name: str, plaintext: str, key: bytes) -> None:
    ciphertext = Fernet(key).encrypt(plaintext.encode("utf-8"))
    now = utc_now_rfc3339()
    conn.execute(
        """
        INSERT INTO secrets (name, ciphertext, created_at, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(name) DO UPDATE SET ciphertext = excluded.ciphertext, updated_at = excluded.updated_at
        """,
        (name, ciphertext, now, now),
    )
    conn.commit()


def get_secret(conn: sqlite3.Connection, name: str, key: bytes) -> str:
    row = conn.execute("SELECT ciphertext FROM secrets WHERE name = ?", (name,)).fetchone()
    if row is None:
        raise SecretNotFoundError(name)
    return Fernet(key).decrypt(row[0]).decode("utf-8")


def list_secret_names(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute("SELECT name FROM secrets ORDER BY name").fetchall()
    return [row[0] for row in rows]


def rotate_key(conn: sqlite3.Connection, old_key: bytes, new_key: bytes) -> None:
    old_fernet = Fernet(old_key)
    new_fernet = Fernet(new_key)
    rows = conn.execute("SELECT name, ciphertext FROM secrets").fetchall()
    now = utc_now_rfc3339()
    try:
        for name, ciphertext in rows:
            plaintext = old_fernet.decrypt(ciphertext)
            conn.execute(
                "UPDATE secrets SET ciphertext = ?, updated_at = ? WHERE name = ?",
                (new_fernet.encrypt(plaintext), now, name),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
