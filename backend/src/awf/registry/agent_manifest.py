"""Agent Manifest schema, loading, and validation (ADR-0002).

A Markdown file with YAML frontmatter - the shape every real subagent
config format independently converged on (Claude Code, GitHub Copilot CLI,
Antigravity), adapted for AWF's own concepts: which adapter it routes
through, its capability allowlist (Section 9.2), Trifecta role (Section
12.3), and optional voice/persona/MCP/skills/model-profile references. The Markdown body
is the manifest's default instructions, layered under a workflow node's
per-invocation `objective`, never replacing it.

Like a Capability Record, an Agent Manifest is self-describing (`name` and
`version` are read from its own content, not just its publish path) -
`agents` has a real `config/app_registry/` counterpart (Section 9.3), so it
needs the same publish-by-content-identity path Capability Records use.
"""

from dataclasses import dataclass
from functools import partial
from pathlib import Path

from awf.registry.schema import split_frontmatter, validate_json_schema, validate_registry_identity
from awf.registry.schemas.agent_manifests import SCHEMA


class AgentManifestValidationError(ValueError):
    pass


_split_frontmatter = partial(split_frontmatter, label="agent manifest", error=AgentManifestValidationError)


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
    persona: str | None = None
    model_profile: str | None = None
    instructions: str = ""

    @property
    def ref(self) -> str:
        return f"{self.name}@{self.version}"


def _parse_skill_ref(item: object) -> SkillRef:
    if isinstance(item, str):
        return SkillRef(ref=item)
    if isinstance(item, dict):
        return SkillRef(ref=item["ref"], share=item.get("share", False))
    raise AgentManifestValidationError(f"skills entry must be a string or a mapping, got {item!r}")


def parse_agent_manifest(raw: dict, instructions: str = "") -> AgentManifest:
    validate_json_schema(raw, SCHEMA, "agent manifest", error=AgentManifestValidationError)

    return AgentManifest(
        name=raw["name"],
        version=raw["version"],
        description=raw["description"],
        adapter=raw["adapter"],
        capabilities=tuple(raw.get("capabilities", [])),
        role=raw.get("role"),
        mcp=tuple(raw.get("mcp", [])),
        skills=tuple(_parse_skill_ref(item) for item in raw.get("skills", [])),
        voice=raw.get("voice"),
        persona=raw.get("persona"),
        model_profile=raw.get("modelProfile"),
        instructions=instructions,
    )


def load_agent_manifest(path: Path) -> AgentManifest:
    frontmatter, body = _split_frontmatter(path.read_text())
    manifest = parse_agent_manifest(frontmatter, instructions=body)
    validate_registry_identity(
        name=manifest.name,
        version=manifest.version,
        path=path,
        context="agent manifest",
        error=AgentManifestValidationError,
    )
    return manifest
