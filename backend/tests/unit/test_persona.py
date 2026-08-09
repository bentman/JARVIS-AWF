import pytest

from awf.registry.persona import (
    ASSERTIVENESS_INSTRUCTIONS,
    DETAIL_INSTRUCTIONS,
    HUMOR_INSTRUCTIONS,
    TRAIT_LEVELS,
    WARMTH_INSTRUCTIONS,
    PersonaValidationError,
    compile_persona,
    load_persona,
    parse_persona,
)


def minimal_raw(**overrides):
    raw = {
        "name": "demo",
        "version": "1.0.0",
        "display_name": "Demo",
        "description": "x",
        "locale": "en",
        "system": "Demo system.",
        "style": {
            "max_words_default": 120,
            "structure": "Answer first.",
            "do": ["Be direct."],
            "avoid": ["Guessing."],
        },
        "traits": {"warmth": "medium", "assertiveness": "medium", "detail": "medium", "humor": "none"},
        "examples": [{"user": "Hi", "assistant": "Hello"}],
        "generation": {"temperature": 0.6, "max_tokens": 180},
    }
    raw.update(overrides)
    return raw


def test_parse_rejects_prohibited_authority_fields():
    raw = minimal_raw(capabilities=[])
    with pytest.raises(PersonaValidationError, match="prohibited authority fields: capabilities"):
        parse_persona(raw)


def test_parse_rejects_unknown_fields():
    raw = minimal_raw(extra="x")
    with pytest.raises(PersonaValidationError, match="unknown fields: extra"):
        parse_persona(raw)


@pytest.mark.parametrize("level", TRAIT_LEVELS)
def test_every_trait_level_compiles(level):
    persona = parse_persona(
        minimal_raw(traits={"warmth": level, "assertiveness": level, "detail": level, "humor": "none"})
    )
    compiled = compile_persona(persona)
    assert WARMTH_INSTRUCTIONS[level] in compiled.system_text
    assert ASSERTIVENESS_INSTRUCTIONS[level] in compiled.system_text
    assert DETAIL_INSTRUCTIONS[level] in compiled.system_text


@pytest.mark.parametrize("humor", HUMOR_INSTRUCTIONS)
def test_every_humor_level_compiles(humor):
    persona = parse_persona(
        minimal_raw(traits={"warmth": "medium", "assertiveness": "medium", "detail": "medium", "humor": humor})
    )
    assert HUMOR_INSTRUCTIONS[humor] in compile_persona(persona).system_text


def test_compile_persona_is_deterministic_and_flattens_examples():
    persona = parse_persona(minimal_raw())

    first = compile_persona(persona)
    second = compile_persona(persona)

    assert first.system_text == second.system_text
    assert first.example_messages == (
        {"role": "user", "content": "Hi"},
        {"role": "assistant", "content": "Hello"},
    )
    assert first.generation == {"temperature": 0.6, "max_tokens": 180}


def test_load_rejects_path_name_mismatch(tmp_path):
    target = tmp_path / "personas" / "other" / "1.0.0.yaml"
    target.parent.mkdir(parents=True)
    target.write_text(
        "name: demo\n"
        "version: 1.0.0\n"
        "display_name: Demo\n"
        "description: x\n"
        "locale: en\n"
        "system: Demo system.\n"
        "style: {max_words_default: 120, structure: Answer first., do: [Be direct.], avoid: [Guessing.]}\n"
        "traits: {warmth: medium, assertiveness: medium, detail: medium, humor: none}\n"
        "examples: [{user: Hi, assistant: Hello}]\n"
        "generation: {temperature: 0.6, max_tokens: 180}\n"
    )
    with pytest.raises(PersonaValidationError, match="does not match its registry directory"):
        load_persona(target)
