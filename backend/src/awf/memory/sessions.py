"""Active session store (ADR-0020)."""

import json
import sqlite3

from awf.clock import utc_now_rfc3339
from awf.ids import uuid7


class SessionError(RuntimeError):
    pass


def start_session(
    conn: sqlite3.Connection,
    *,
    title: str | None = None,
    expires_at: str | None = None,
    ttl_hours: int | None = None,
) -> dict:
    session_id = uuid7()
    now = utc_now_rfc3339()
    if expires_at is None and ttl_hours is not None:
        from datetime import UTC, datetime, timedelta

        dt = datetime.now(UTC) + timedelta(hours=ttl_hours)
        expires_at = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    conn.execute(
        "INSERT INTO active_sessions (session_id, title, status, summary, created_at, updated_at, expires_at) "
        "VALUES (?, ?, 'active', NULL, ?, ?, ?)",
        (session_id, title, now, now, expires_at),
    )
    conn.commit()
    return show_session(conn, session_id=session_id)


def append_entry(
    conn: sqlite3.Connection, *, session_id: str, role: str, content: dict, summary: str | None = None
) -> dict:
    row = conn.execute("SELECT status, expires_at FROM active_sessions WHERE session_id = ?", (session_id,)).fetchone()
    if row is None:
        raise SessionError(f"no such session: {session_id}")
    now = utc_now_rfc3339()
    if row["status"] == "expired" or (row["expires_at"] and now >= row["expires_at"]):
        if row["status"] != "expired":
            conn.execute(
                "UPDATE active_sessions SET status = 'expired', updated_at = ? WHERE session_id = ?", (now, session_id)
            )
            conn.commit()
        raise SessionError(f"session {session_id} is expired")
    entry_id = uuid7()
    conn.execute(
        "INSERT INTO active_session_entries (entry_id, session_id, role, content_json, summary, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (entry_id, session_id, role, json.dumps(content, sort_keys=True), summary, now),
    )
    conn.execute("UPDATE active_sessions SET updated_at = ? WHERE session_id = ?", (now, session_id))
    conn.commit()
    return show_session(conn, session_id=session_id)


def show_session(conn: sqlite3.Connection, *, session_id: str) -> dict:
    row = conn.execute("SELECT * FROM active_sessions WHERE session_id = ?", (session_id,)).fetchone()
    if row is None:
        raise SessionError(f"no such session: {session_id}")
    now = utc_now_rfc3339()
    if row["status"] == "active" and row["expires_at"] and now >= row["expires_at"]:
        conn.execute(
            "UPDATE active_sessions SET status = 'expired', updated_at = ? WHERE session_id = ?", (now, session_id)
        )
        conn.commit()
        row = conn.execute("SELECT * FROM active_sessions WHERE session_id = ?", (session_id,)).fetchone()

    entries = [
        {**dict(entry), "content": json.loads(entry["content_json"])}
        for entry in conn.execute(
            "SELECT * FROM active_session_entries WHERE session_id = ? ORDER BY created_at, entry_id",
            (session_id,),
        ).fetchall()
    ]
    return {**dict(row), "entries": entries}


def summarize_session(conn: sqlite3.Connection, *, session_id: str, summary: str | None = None) -> dict:
    current = show_session(conn, session_id=session_id)
    if summary is None:
        parts = []
        for entry in current["entries"]:
            entry_summary = entry.get("summary") or json.dumps(entry["content"], sort_keys=True)
            parts.append(f"{entry['role']}: {entry_summary}")
        summary = "\n".join(parts)
    now = utc_now_rfc3339()
    conn.execute(
        "UPDATE active_sessions SET status = 'summarized', summary = ?, updated_at = ? WHERE session_id = ?",
        (summary, now, session_id),
    )
    conn.commit()
    return show_session(conn, session_id=session_id)
