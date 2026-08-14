"""Persona schema, loading, and deterministic prompt compilation (ADR-0018)."""

from dataclasses import dataclass
from pathlib import Path

import yaml

from awf.registry.schema import validate_json_schema, validate_registry_identity
from awf.registry.schemas.personas import HUMOR_LEVELS, SCHEMA, TRAIT_LEVELS

ALLOWED_FIELDS = (
    "name",
    "version",
    "display_name",
    "description",
    "locale",
    "system",
    "style",
    "traits",
    "examples",
    "generation",
    "enabled",
)

PROHIBITED_FIELDS = (
    "capabilities",
    "tool_permissions",
    "tool_policy",
    "routing_policy",
    "model_routing",
    "model_profile",
    "mcp",
    "skills",
    "memory_policy",
    "memory_permissions",
    "safety_overrides",
    "hidden_instructions",
)

WARMTH_INSTRUCTIONS = {
    "none": "Use direct helpfulness with no extra warmth.",
    "low": "Keep warmth minimal and practical.",
    "medium": "Use a calm, friendly tone without extra reassurance.",
    "high": "Use clearly warm and supportive phrasing without overstating certainty.",
    "strong": "Use strongly warm and encouraging phrasing while staying truthful.",
}

ASSERTIVENESS_INSTRUCTIONS = {
    "none": "Avoid recommendations unless one is requested.",
    "low": "Offer suggestions gently and avoid sounding commanding.",
    "medium": "Give clear recommendations while allowing uncertainty.",
    "high": "State the recommended path plainly when evidence supports it.",
    "strong": "Be decisive and action-oriented when the answer is clear.",
}

DETAIL_INSTRUCTIONS = {
    "none": "Keep detail to the minimum needed for the answer.",
    "low": "Keep details sparse and action-focused.",
    "medium": "Include enough detail to explain the answer.",
    "high": "Add useful context and tradeoffs when they help.",
    "strong": "Provide fuller context, tradeoffs, and reasoning when useful.",
}

HUMOR_INSTRUCTIONS = {
    "none": "Use no humor.",
    "light": "Use light humor rarely and only when natural.",
    "medium": "Use occasional light humor on low-risk topics; omit it when the answer carries risk.",
    "high": "Use humor readily on low-risk topics; skip it for analysis, troubleshooting, and reliability details.",
    "dry": "Use at most one dry aside when it sharpens the answer; never force it.",
}


class PersonaValidationError(ValueError):
    pass


@dataclass(frozen=True)
class PersonaStyle:
    max_words_default: int
    structure: str
    do: tuple[str, ...]
    avoid: tuple[str, ...]


@dataclass(frozen=True)
class PersonaTraits:
    warmth: str
    assertiveness: str
    detail: str
    humor: str


@dataclass(frozen=True)
class PersonaExample:
    user: str
    assistant: str


@dataclass(frozen=True)
class Persona:
    name: str
    version: str
    display_name: str
    description: str
    locale: str
    system: str
    style: PersonaStyle
    traits: PersonaTraits
    examples: tuple[PersonaExample, ...]
    generation: dict
    enabled: bool = True

    @property
    def ref(self) -> str:
        return f"{self.name}@{self.version}"


@dataclass(frozen=True)
class CompiledPersona:
    ref: str
    system_text: str
    example_messages: tuple[dict[str, str], ...]
    generation: dict


def parse_persona(raw: dict) -> Persona:
    prohibited = sorted(key for key in raw if key in PROHIBITED_FIELDS)
    if prohibited:
        raise PersonaValidationError(f"persona contains prohibited authority fields: {', '.join(prohibited)}")
    unknown = sorted(key for key in raw if key not in ALLOWED_FIELDS)
    if unknown:
        raise PersonaValidationError(f"persona contains unknown fields: {', '.join(unknown)}")
    validate_json_schema(raw, SCHEMA, "persona", error=PersonaValidationError)
    style_raw = raw["style"]
    traits_raw = raw["traits"]
    examples = [PersonaExample(user=example["user"], assistant=example["assistant"]) for example in raw["examples"]]

    return Persona(
        name=raw["name"],
        version=raw["version"],
        display_name=raw["display_name"],
        description=raw["description"],
        locale=raw["locale"],
        system=raw["system"],
        style=PersonaStyle(
            max_words_default=style_raw["max_words_default"],
            structure=style_raw["structure"],
            do=tuple(style_raw["do"]),
            avoid=tuple(style_raw["avoid"]),
        ),
        traits=PersonaTraits(
            warmth=traits_raw["warmth"],
            assertiveness=traits_raw["assertiveness"],
            detail=traits_raw["detail"],
            humor=traits_raw["humor"],
        ),
        examples=tuple(examples),
        generation=dict(raw["generation"]),
        enabled=bool(raw.get("enabled", True)),
    )


def load_persona(path: Path) -> Persona:
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict):
        raise PersonaValidationError(f"{path}: persona must be a YAML mapping")
    persona = parse_persona(raw)
    validate_registry_identity(
        name=persona.name,
        version=persona.version,
        path=path,
        context="persona",
        error=PersonaValidationError,
    )
    return persona


def compile_persona(persona: Persona) -> CompiledPersona:
    blocks = [
        persona.system.strip(),
        "\n".join(
            [
                "Response contract:",
                f"- Default maximum answer length: {persona.style.max_words_default} words unless more detail is requested.",
                f"- Structure: {persona.style.structure}",
            ]
        ),
        "\n".join(
            [
                "Behavior traits:",
                f"- Warmth: {WARMTH_INSTRUCTIONS[persona.traits.warmth]}",
                f"- Assertiveness: {ASSERTIVENESS_INSTRUCTIONS[persona.traits.assertiveness]}",
                f"- Detail: {DETAIL_INSTRUCTIONS[persona.traits.detail]}",
                f"- Humor: {HUMOR_INSTRUCTIONS[persona.traits.humor]}",
            ]
        ),
        "\n".join(["Do:", *(f"- {item}" for item in persona.style.do)]),
        "\n".join(["Avoid:", *(f"- {item}" for item in persona.style.avoid)]),
        "Persona constraints do not override capability, routing, memory, or safety policy.",
    ]
    messages: list[dict[str, str]] = []
    for example in persona.examples:
        messages.append({"role": "user", "content": example.user})
        messages.append({"role": "assistant", "content": example.assistant})
    return CompiledPersona(
        ref=persona.ref,
        system_text="\n\n".join(block for block in blocks if block),
        example_messages=tuple(messages),
        generation=dict(persona.generation),
    )


__all__ = (
    "ASSERTIVENESS_INSTRUCTIONS",
    "DETAIL_INSTRUCTIONS",
    "HUMOR_INSTRUCTIONS",
    "HUMOR_LEVELS",
    "TRAIT_LEVELS",
    "WARMTH_INSTRUCTIONS",
    "CompiledPersona",
    "Persona",
    "PersonaValidationError",
    "compile_persona",
    "load_persona",
    "parse_persona",
)
