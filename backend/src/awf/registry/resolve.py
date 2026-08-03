"""Registry resolution across the two roots (Section 9.3).

Lookup checks `data/registry/<kind>/<name>/` first. If any version exists
there, resolution uses that tree exclusively for that kind+name -
`config/app_registry/` is not read, merged, or blended in for the same name.
Only when `data/registry/<kind>/<name>/` has no entry does resolution fall
back to `config/app_registry/<kind>/<name>/`.
"""

from pathlib import Path

CONFIG_ROOT = "config/app_registry"
DATA_ROOT = "data/registry"

# model-profiles names a specific provider account and budget, so it is
# always operator-specific and has no config/app_registry/ counterpart.
DATA_ONLY_KINDS = ("model-profiles",)


class RegistryObjectNotFoundError(FileNotFoundError):
    pass


def _object_path(base_dir: Path, kind: str, version: str) -> Path:
    if kind == "skills":
        return base_dir / version / "SKILL.md"
    if kind == "agents":
        return base_dir / f"{version}.md"
    return base_dir / f"{version}.yaml"


def resolve_registry_object(
    repo_root: Path, kind: str, name: str, version: str
) -> tuple[Path, str]:
    """Return (path, source) for a registry object, source in {"config", "data"}."""
    data_dir = repo_root / DATA_ROOT / kind / name
    if data_dir.is_dir() and any(data_dir.iterdir()):
        # data/ has a presence for this kind+name: resolution is locked to
        # this tree exclusively, even if the requested version isn't in it.
        path = _object_path(data_dir, kind, version)
        if not path.exists():
            raise RegistryObjectNotFoundError(
                f"{kind}/{name}@{version} not found in {DATA_ROOT} "
                f"(name is present there, so {CONFIG_ROOT} is not consulted)"
            )
        return path, "data"

    if kind not in DATA_ONLY_KINDS:
        config_dir = repo_root / CONFIG_ROOT / kind / name
        if config_dir.is_dir() and any(config_dir.iterdir()):
            path = _object_path(config_dir, kind, version)
            if not path.exists():
                raise RegistryObjectNotFoundError(
                    f"{kind}/{name}@{version} not found in {CONFIG_ROOT}"
                )
            return path, "config"

    raise RegistryObjectNotFoundError(
        f"no registry object for {kind}/{name} under {DATA_ROOT} or {CONFIG_ROOT}"
    )
