"""Persona schema, loading, and deterministic prompt compilation (ADR-0018)."""

from dataclasses import dataclass
from functools import partial
from pathlib import Path

import yaml

from awf.registry.schema import require, require_enum

TRAIT_LEVELS = ("none", "low", "medium", "high", "strong")
HUMOR_LEVELS = ("none", "light", "medium", "high", "dry")

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

GENERATION_FIELDS = ("temperature", "top_p", "top_k", "repeat_penalty", "max_tokens", "stop")

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


_require = partial(require, error=PersonaValidationError)
_require_enum = partial(require_enum, error=PersonaValidationError)


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


def _require_mapping(value: object, context: str) -> dict:
    if not isinstance(value, dict):
        raise PersonaValidationError(f"{context} must be a mapping")
    return value


def _string_tuple(value: object, context: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise PersonaValidationError(f"{context} must be a list of strings")
    return tuple(value)


def parse_persona(raw: dict) -> Persona:
    prohibited = sorted(key for key in raw if key in PROHIBITED_FIELDS)
    if prohibited:
        raise PersonaValidationError(f"persona contains prohibited authority fields: {', '.join(prohibited)}")
    unknown = sorted(key for key in raw if key not in ALLOWED_FIELDS)
    if unknown:
        raise PersonaValidationError(f"persona contains unknown fields: {', '.join(unknown)}")

    style_raw = _require_mapping(_require(raw, "style", "persona"), "persona.style")
    traits_raw = _require_mapping(_require(raw, "traits", "persona"), "persona.traits")
    examples_raw = _require(raw, "examples", "persona")
    generation_raw = _require_mapping(_require(raw, "generation", "persona"), "persona.generation")

    generation_unknown = sorted(key for key in generation_raw if key not in GENERATION_FIELDS)
    if generation_unknown:
        raise PersonaValidationError(f"persona.generation contains unknown fields: {', '.join(generation_unknown)}")

    if not isinstance(examples_raw, list) or not examples_raw:
        raise PersonaValidationError("persona.examples must be a non-empty list")
    examples = []
    for index, example_raw in enumerate(examples_raw):
        example = _require_mapping(example_raw, f"persona.examples[{index}]")
        examples.append(
            PersonaExample(
                user=_require(example, "user", f"persona.examples[{index}]"),
                assistant=_require(example, "assistant", f"persona.examples[{index}]"),
            )
        )

    return Persona(
        name=_require(raw, "name", "persona"),
        version=_require(raw, "version", "persona"),
        display_name=_require(raw, "display_name", "persona"),
        description=_require(raw, "description", "persona"),
        locale=_require(raw, "locale", "persona"),
        system=_require(raw, "system", "persona"),
        style=PersonaStyle(
            max_words_default=int(_require(style_raw, "max_words_default", "persona.style")),
            structure=_require(style_raw, "structure", "persona.style"),
            do=_string_tuple(_require(style_raw, "do", "persona.style"), "persona.style.do"),
            avoid=_string_tuple(_require(style_raw, "avoid", "persona.style"), "persona.style.avoid"),
        ),
        traits=PersonaTraits(
            warmth=_require_enum(
                _require(traits_raw, "warmth", "persona.traits"), TRAIT_LEVELS, "persona.traits.warmth"
            ),
            assertiveness=_require_enum(
                _require(traits_raw, "assertiveness", "persona.traits"), TRAIT_LEVELS, "persona.traits.assertiveness"
            ),
            detail=_require_enum(
                _require(traits_raw, "detail", "persona.traits"), TRAIT_LEVELS, "persona.traits.detail"
            ),
            humor=_require_enum(_require(traits_raw, "humor", "persona.traits"), HUMOR_LEVELS, "persona.traits.humor"),
        ),
        examples=tuple(examples),
        generation=dict(generation_raw),
        enabled=bool(raw.get("enabled", True)),
    )


def load_persona(path: Path) -> Persona:
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict):
        raise PersonaValidationError(f"{path}: persona must be a YAML mapping")
    persona = parse_persona(raw)

    expected_name = path.parent.name
    if persona.name != expected_name:
        raise PersonaValidationError(
            f"persona name '{persona.name}' does not match its registry directory '{expected_name}'"
        )
    expected_version = path.stem
    if persona.version != expected_version:
        raise PersonaValidationError(
            f"persona version '{persona.version}' does not match its file name '{expected_version}'"
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
