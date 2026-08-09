"""The registry index as a catalog and integrity check (ADR-0012).

The filesystem stays the resolution source of truth; this module reads and
writes `registry_index`, the table `resolve.resolve_registry_object` and
`cli.core_ops` consult for digest verification, trust status, and
latest-version lookup. A rebuild (`reindex`) is idempotent and never touches
an existing row's `trust_status`, so an operator's `blocked`/`quarantined`/
`trusted` decision survives it.
"""

import hashlib
import sqlite3
from pathlib import Path

from awf.clock import utc_now_rfc3339
from awf.paths import CONFIG_REGISTRY_RELATIVE as CONFIG_ROOT
from awf.paths import DATA_REGISTRY_RELATIVE as DATA_ROOT
from awf.registry.kinds import KINDS, RegistryKind, by_key, object_path, version_names
from awf.registry.resolve import RegistryObjectNotFoundError
from awf.registry.skill import directory_digest

_DEFAULT_TRUST_STATUS = {"config": "trusted", "data": "local"}


def compute_digest(path: Path, kind: RegistryKind) -> str:
    if kind.layout == "directory":
        return directory_digest(path.parent)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def index_row(conn: sqlite3.Connection, kind: str, name: str, version: str) -> dict | None:
    row = conn.execute(
        "SELECT * FROM registry_index WHERE kind = ? AND name = ? AND version = ?",
        (kind, name, version),
    ).fetchone()
    return dict(row) if row is not None else None


def set_trust_status(conn: sqlite3.Connection, kind: str, name: str, version: str, status: str) -> dict | None:
    conn.execute(
        "UPDATE registry_index SET trust_status = ? WHERE kind = ? AND name = ? AND version = ?",
        (status, kind, name, version),
    )
    conn.commit()
    return index_row(conn, kind, name, version)


def _upsert(
    conn: sqlite3.Connection,
    *,
    kind: str,
    name: str,
    version: str,
    digest: str,
    source: str,
    path: Path,
    repo_root: Path,
) -> None:
    conn.execute(
        "INSERT INTO registry_index (kind, name, version, digest, source, path, trust_status, indexed_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(kind, name, version) DO UPDATE SET "
        "digest=excluded.digest, path=excluded.path, source=excluded.source, indexed_at=excluded.indexed_at",
        (
            kind,
            name,
            version,
            digest,
            source,
            str(path.relative_to(repo_root)),
            _DEFAULT_TRUST_STATUS[source],
            utc_now_rfc3339(),
        ),
    )


def reindex(repo_root: Path, conn: sqlite3.Connection) -> dict:
    counts: dict[str, dict[str, int]] = {kind.key: {"config": 0, "data": 0} for kind in KINDS}

    # config first, then data: when the same (kind, name, version) exists on
    # both sides, resolution always prefers data for a shadowed name, so
    # indexing data last leaves the row matching what resolution returns.
    roots = (("config", repo_root / CONFIG_ROOT), ("data", repo_root / DATA_ROOT))
    for kind in KINDS:
        for source, root in roots:
            if source == "config" and kind.data_only:
                continue
            kind_dir = root / kind.key
            if not kind_dir.is_dir():
                continue
            for name_dir in sorted(p for p in kind_dir.iterdir() if p.is_dir()):
                for version in version_names(name_dir, kind):
                    path = object_path(name_dir, kind, version)
                    digest = compute_digest(path, kind)
                    _upsert(
                        conn,
                        kind=kind.key,
                        name=name_dir.name,
                        version=version,
                        digest=digest,
                        source=source,
                        path=path,
                        repo_root=repo_root,
                    )
                    counts[kind.key][source] += 1
    conn.commit()
    return counts


def _version_key(version: str) -> tuple:
    try:
        return (1, tuple(int(part) for part in version.split(".")))
    except ValueError:
        return (0, version)


def latest_version(repo_root: Path, kind: str, name: str) -> str:
    registry_kind = by_key(kind)

    data_dir = repo_root / DATA_ROOT / kind / name
    if data_dir.is_dir():
        versions = version_names(data_dir, registry_kind)
        if versions:
            return max(versions, key=_version_key)

    if not registry_kind.data_only:
        config_dir = repo_root / CONFIG_ROOT / kind / name
        if config_dir.is_dir():
            versions = version_names(config_dir, registry_kind)
            if versions:
                return max(versions, key=_version_key)

    raise RegistryObjectNotFoundError(f"no {kind}/{name} under {DATA_ROOT} or {CONFIG_ROOT}")
