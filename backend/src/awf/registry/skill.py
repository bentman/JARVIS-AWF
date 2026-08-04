"""Skill schema, loading, and validation (Section 9.3, ADR-0004).

`skills/<name>/<version>/SKILL.md` (+ optional `scripts/`, `references/`,
`assets/`) - the Agent Skills open standard (agentskills.io, Apache-2.0),
unmodified. The frontmatter shape is not AWF's to define; this module only
parses and validates it, and computes the directory digest ADR-0004's
`events` record uses as the audit trail of what an agent was given.
"""

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

_NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


class SkillValidationError(ValueError):
    pass


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    body: str
    license: str | None = None
    compatibility: str | None = None
    metadata: dict = field(default_factory=dict)
    allowed_tools: str | None = None
    version: str | None = None

    @property
    def ref(self) -> str:
        return f"{self.name}@{self.version}"


def _require(mapping: dict, key: str, context: str) -> object:
    if key not in mapping:
        raise SkillValidationError(f"{context}: missing required field '{key}'")
    return mapping[key]


def _validate_name(name: str) -> None:
    if len(name) < 1 or len(name) > 64:
        raise SkillValidationError(f"skill name {name!r} must be 1-64 characters")
    if not _NAME_RE.match(name):
        raise SkillValidationError(
            f"skill name {name!r} must be lowercase alphanumeric with single hyphens, "
            "no leading/trailing/doubled hyphen"
        )


def _split_frontmatter(text: str) -> tuple[dict, str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise SkillValidationError("SKILL.md must start with a '---' YAML frontmatter block")
    try:
        end = lines[1:].index("---") + 1
    except ValueError:
        raise SkillValidationError("SKILL.md frontmatter has no closing '---'") from None

    frontmatter = yaml.safe_load("\n".join(lines[1:end])) or {}
    if not isinstance(frontmatter, dict):
        raise SkillValidationError("SKILL.md frontmatter must be a YAML mapping")
    body = "\n".join(lines[end + 1 :]).strip()
    return frontmatter, body


def parse_skill(raw: dict, *, body: str = "", version: str | None = None) -> Skill:
    name = _require(raw, "name", "SKILL.md")
    _validate_name(name)
    description = _require(raw, "description", "SKILL.md")
    if len(description) < 1 or len(description) > 1024:
        raise SkillValidationError("description must be 1-1024 characters")
    compatibility = raw.get("compatibility")
    if compatibility is not None and len(compatibility) > 500:
        raise SkillValidationError("compatibility must be at most 500 characters")

    return Skill(
        name=name,
        description=description,
        body=body,
        license=raw.get("license"),
        compatibility=compatibility,
        metadata=raw.get("metadata", {}),
        allowed_tools=raw.get("allowed-tools"),
        version=version,
    )


def load_skill(skill_md_path: Path) -> Skill:
    """`skill_md_path` is the SKILL.md file at `skills/<name>/<version>/SKILL.md`
    - the version is read from its parent directory name, and the
    frontmatter's own `name` MUST match the skill's directory
    (`skill_md_path.parent.parent`), per the standard's own rule that the
    `name` field and the containing folder agree."""
    frontmatter, body = _split_frontmatter(skill_md_path.read_text())
    version = skill_md_path.parent.name
    skill = parse_skill(frontmatter, body=body, version=version)
    expected_dir_name = skill_md_path.parent.parent.name
    if skill.name != expected_dir_name:
        raise SkillValidationError(
            f"SKILL.md name '{skill.name}' does not match its registry directory '{expected_dir_name}'"
        )
    return skill


def directory_digest(skill_dir: Path) -> str:
    """sha256 over sorted `relative_path:sha256(file_bytes)` lines, one per
    file, concatenated in path order and hashed once more - deterministic
    regardless of filesystem iteration order."""
    lines = []
    for path in sorted(p for p in skill_dir.rglob("*") if p.is_file()):
        file_digest = hashlib.sha256(path.read_bytes()).hexdigest()
        lines.append(f"{path.relative_to(skill_dir).as_posix()}:{file_digest}\n")
    return hashlib.sha256("".join(lines).encode("utf-8")).hexdigest()
