"""Skill schema, loading, and validation (Section 9.3, ADR-0004).

`skills/<name>/<version>/SKILL.md` (+ optional `scripts/`, `references/`,
`assets/`) - the Agent Skills open standard (agentskills.io, Apache-2.0),
unmodified. The frontmatter shape is not AWF's to define; this module only
parses and validates it, and computes the directory digest ADR-0004's
`events` record uses as the audit trail of what an agent was given.
"""

import hashlib
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path

from awf.registry.schema import split_frontmatter, validate_json_schema
from awf.registry.schemas.skills import SCHEMA


class SkillValidationError(ValueError):
    pass


_split_frontmatter = partial(split_frontmatter, label="SKILL.md", error=SkillValidationError)


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


def parse_skill(raw: dict, *, body: str = "", version: str | None = None) -> Skill:
    validate_json_schema(raw, SCHEMA, "SKILL.md", error=SkillValidationError)
    name = raw["name"]
    description = raw["description"]
    compatibility = raw.get("compatibility")

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
