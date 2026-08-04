"""Agent Manifest schema, loading, and validation (ADR-0002).

A Markdown file with YAML frontmatter - the shape every real subagent
config format independently converged on (Claude Code, GitHub Copilot CLI,
Antigravity), adapted for AWF's own concepts: which adapter it routes
through, its capability allowlist (Section 9.2), Trifecta role (Section
12.3), and optional voice/MCP/skills/model-profile references. The Markdown body
is the manifest's default instructions, layered under a workflow node's
per-invocation `objective`, never replacing it.

Like a Capability Record, an Agent Manifest is self-describing (`name` and
`version` are read from its own content, not just its publish path) -
`agents` has a real `config/app_registry/` counterpart (Section 9.3), so it
needs the same publish-by-content-identity path Capability Records use.
"""

from dataclasses import dataclass
from pathlib import Path

import yaml

ROLES = ("builder", "verifier", "adversary")


class AgentManifestValidationError(ValueError):
    pass


@dataclass(frozen=True)
class SkillRef:
    # `share: false` (default) is the AWF-injected tier (ADR-0004): the
    # Skill's body is folded into the objective text, the adapter never
    # sees a discoverable skill directory. `share: true` is the second,
    # explicit, per-reference opt-in - the only "grant" this system can
    # express, since no authority model exists above the operator who
    # authors the manifest.
    ref: str
    share: bool = False


@dataclass(frozen=True)
class AgentManifest:
    name: str
    version: str
    description: str
    adapter: str
    capabilities: tuple[str, ...] = ()
    role: str | None = None
    mcp: tuple[str, ...] = ()
    skills: tuple[SkillRef, ...] = ()
    voice: str | None = None
    model_profile: str | None = None
    instructions: str = ""

    @property
    def ref(self) -> str:
        return f"{self.name}@{self.version}"


def _require(mapping: dict, key: str, context: str) -> object:
    if key not in mapping:
        raise AgentManifestValidationError(f"{context}: missing required field '{key}'")
    return mapping[key]


def _split_frontmatter(text: str) -> tuple[dict, str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise AgentManifestValidationError(
            "agent manifest must start with a '---' YAML frontmatter block"
        )
    try:
        end = lines[1:].index("---") + 1
    except ValueError:
        raise AgentManifestValidationError("agent manifest frontmatter has no closing '---'") from None

    frontmatter = yaml.safe_load("\n".join(lines[1:end])) or {}
    if not isinstance(frontmatter, dict):
        raise AgentManifestValidationError("agent manifest frontmatter must be a YAML mapping")
    body = "\n".join(lines[end + 1 :]).strip()
    return frontmatter, body


def _parse_skill_ref(item: object) -> SkillRef:
    if isinstance(item, str):
        return SkillRef(ref=item)
    if isinstance(item, dict):
        return SkillRef(ref=_require(item, "ref", "skill ref"), share=bool(item.get("share", False)))
    raise AgentManifestValidationError(f"skills entry must be a string or a mapping, got {item!r}")


def parse_agent_manifest(raw: dict, instructions: str = "") -> AgentManifest:
    role = raw.get("role")
    if role is not None and role not in ROLES:
        raise AgentManifestValidationError(f"role '{role}' not in {ROLES}")

    return AgentManifest(
        name=_require(raw, "name", "agent manifest"),
        version=_require(raw, "version", "agent manifest"),
        description=_require(raw, "description", "agent manifest"),
        adapter=_require(raw, "adapter", "agent manifest"),
        capabilities=tuple(raw.get("capabilities", [])),
        role=role,
        mcp=tuple(raw.get("mcp", [])),
        skills=tuple(_parse_skill_ref(item) for item in raw.get("skills", [])),
        voice=raw.get("voice"),
        model_profile=raw.get("modelProfile"),
        instructions=instructions,
    )


def load_agent_manifest(path: Path) -> AgentManifest:
    frontmatter, body = _split_frontmatter(path.read_text())
    return parse_agent_manifest(frontmatter, instructions=body)
