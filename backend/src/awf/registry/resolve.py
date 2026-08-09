"""Registry resolution across the two roots (Section 9.3).

Lookup checks `data/registry/<kind>/<name>/` first. If any version exists
there, resolution uses that tree exclusively for that kind+name -
`config/app_registry/` is not read, merged, or blended in for the same name.
Only when `data/registry/<kind>/<name>/` has no entry does resolution fall
back to `config/app_registry/<kind>/<name>/`.
"""

import sqlite3
from pathlib import Path

from awf.paths import CONFIG_REGISTRY_RELATIVE as CONFIG_ROOT
from awf.paths import DATA_REGISTRY_RELATIVE as DATA_ROOT
from awf.registry.kinds import by_key, version_names
from awf.registry.kinds import object_path as _object_path


class RegistryObjectNotFoundError(FileNotFoundError):
    pass


class RegistryIntegrityError(ValueError):
    pass


class RegistryBlockedError(ValueError):
    pass


def resolve_registry_object(
    repo_root: Path, kind: str, name: str, version: str, conn: sqlite3.Connection | None = None
) -> tuple[Path, str]:
    """Return (path, source) for a registry object, source in {"config", "data"}."""
    registry_kind = by_key(kind)

    data_dir = repo_root / DATA_ROOT / kind / name
    if data_dir.is_dir() and any(version_names(data_dir, registry_kind)):
        # data/ has a presence for this kind+name: resolution is locked to
        # this tree exclusively, even if the requested version isn't in it.
        path = _object_path(data_dir, registry_kind, version)
        if not path.exists():
            raise RegistryObjectNotFoundError(
                f"{kind}/{name}@{version} not found in {DATA_ROOT} "
                f"(name is present there, so {CONFIG_ROOT} is not consulted)"
            )
        return _verify(conn, path, kind, name, version, registry_kind), "data"

    if not registry_kind.data_only:
        config_dir = repo_root / CONFIG_ROOT / kind / name
        if config_dir.is_dir() and any(config_dir.iterdir()):
            path = _object_path(config_dir, registry_kind, version)
            if not path.exists():
                raise RegistryObjectNotFoundError(f"{kind}/{name}@{version} not found in {CONFIG_ROOT}")
            return _verify(conn, path, kind, name, version, registry_kind), "config"

    raise RegistryObjectNotFoundError(f"no registry object for {kind}/{name} under {DATA_ROOT} or {CONFIG_ROOT}")


def _verify(conn, path: Path, kind: str, name: str, version: str, registry_kind) -> Path:
    if conn is None:
        return path

    from awf.registry import index  # local import: index.py imports this module

    row = index.index_row(conn, kind, name, version)
    if row is None:
        return path
    if row["trust_status"] == "blocked":
        raise RegistryBlockedError(f"{kind}/{name}@{version} is blocked")

    actual_digest = index.compute_digest(path, registry_kind)
    if actual_digest != row["digest"]:
        raise RegistryIntegrityError(
            f"{kind}/{name}@{version}: digest mismatch - indexed {row['digest']}, actual {actual_digest}, path {path}"
        )
    return path
