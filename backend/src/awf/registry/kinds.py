"""One registry kind vocabulary (ADR-0011): every registry kind's directory
name, on-disk layout, and config/app_registry/ presence, declared once.
`resolve.py`, `core_ops.op_registry_list`, and `core_ops.op_registry_publish`
each read the layout from here rather than deriving it independently.
"""

from dataclasses import dataclass
from pathlib import Path


class UnknownRegistryKindError(ValueError):
    pass


@dataclass(frozen=True)
class RegistryKind:
    key: str  # directory name under both registry roots
    layout: str  # "yaml" | "markdown" | "directory"
    data_only: bool  # no config/app_registry/ counterpart


WORKFLOWS = RegistryKind("workflows", "yaml", False)
AGENTS = RegistryKind("agents", "markdown", False)
CAPABILITIES = RegistryKind("capabilities", "yaml", False)
MCP = RegistryKind("mcp", "yaml", False)
SKILLS = RegistryKind("skills", "directory", False)
VOICE_PROFILES = RegistryKind("voice-profiles", "yaml", False)
MODEL_PROFILES = RegistryKind("model-profiles", "yaml", False)
PERSONAS = RegistryKind("personas", "yaml", False)
MEMORY_PROFILES = RegistryKind("memory-profiles", "yaml", False)
SEMANTIC_MEMORIES = RegistryKind("semantic-memories", "yaml", False)

KINDS: tuple[RegistryKind, ...] = (
    WORKFLOWS,
    AGENTS,
    CAPABILITIES,
    MCP,
    SKILLS,
    VOICE_PROFILES,
    MODEL_PROFILES,
    PERSONAS,
    MEMORY_PROFILES,
    SEMANTIC_MEMORIES,
)

_BY_KEY = {kind.key: kind for kind in KINDS}


def by_key(key: str) -> RegistryKind:
    try:
        return _BY_KEY[key]
    except KeyError:
        valid = ", ".join(sorted(_BY_KEY))
        raise UnknownRegistryKindError(f"unknown registry kind '{key}' - valid kinds: {valid}") from None


def object_path(base_dir: Path, kind: RegistryKind, version: str) -> Path:
    if kind.layout == "directory":
        return base_dir / version / "SKILL.md"
    if kind.layout == "markdown":
        return base_dir / f"{version}.md"
    return base_dir / f"{version}.yaml"


def version_names(name_dir: Path, kind: RegistryKind) -> tuple[str, ...]:
    if kind.layout == "directory":
        return tuple(sorted(p.name for p in name_dir.iterdir() if (p / "SKILL.md").is_file()))
    if kind.layout == "markdown":
        return tuple(sorted(p.stem for p in name_dir.glob("*.md")))
    return tuple(sorted(p.stem for p in name_dir.glob("*.yaml")))
