"""UTC timestamps in RFC 3339 form, per AGENTS.md's Time convention (Section 5)."""

from datetime import datetime, timezone


def utc_now_rfc3339() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
