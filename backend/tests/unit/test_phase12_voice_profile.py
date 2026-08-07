import pytest

from awf.registry.voice_profile import (
    VoiceProfileValidationError,
    load_voice_profile,
    parse_voice_profile,
    resolve_default_voice_id,
)


@pytest.fixture
def voice_profiles_root(repo_root):
    return repo_root / "config" / "app_registry" / "voice-profiles"


def minimal_raw(**overrides):
    raw = {
        "persona": {"name": "Demo", "description": "x", "style_prompt": "y"},
        "tts": {
            "candidates": [
                {"engine": "kokoro", "model": "kokoro-v1.0", "voice_id": "bf_isabella", "speed": 1.0, "priority": 1, "enabled": True}
            ],
            "fallback": {"mode": "none", "allow_quality_degrade": False},
        },
        "privacy": {"local_only": True},
        "limits": {"max_seconds_per_utterance": 30},
    }
    raw.update(overrides)
    return raw


def test_parse_minimal_voice_profile():
    profile = parse_voice_profile(minimal_raw())
    assert profile.persona.name == "Demo"
    candidate = profile.enabled_candidates_by_priority()[0]
    assert candidate.voice_id == "bf_isabella"


def test_parse_rejects_missing_persona():
    raw = minimal_raw()
    del raw["persona"]
    with pytest.raises(VoiceProfileValidationError):
        parse_voice_profile(raw)


def test_parse_rejects_empty_candidates():
    raw = minimal_raw()
    raw["tts"]["candidates"] = []
    with pytest.raises(VoiceProfileValidationError):
        parse_voice_profile(raw)


def test_parse_rejects_invalid_fallback_mode():
    raw = minimal_raw()
    raw["tts"]["fallback"]["mode"] = "not-a-real-mode"
    with pytest.raises(VoiceProfileValidationError):
        parse_voice_profile(raw)


@pytest.mark.parametrize(
    "name,expected_voice_id",
    [
        ("narrator", "bf_isabella"),
        ("builder", "am_michael"),
        ("verifier", "bf_emma"),
        ("adversary", "bm_george"),
    ],
)
def test_load_real_shipped_voice_profile(name, expected_voice_id, voice_profiles_root):
    profile = load_voice_profile(voice_profiles_root / name / "1.0.0.yaml")
    candidate = profile.enabled_candidates_by_priority()[0]
    assert candidate.voice_id == expected_voice_id
    assert candidate.engine == "kokoro"


def test_all_four_default_voice_profiles_use_distinct_voice_ids(voice_profiles_root):
    voice_ids = set()
    for name in ("narrator", "builder", "verifier", "adversary"):
        profile = load_voice_profile(voice_profiles_root / name / "1.0.0.yaml")
        voice_ids.add(profile.enabled_candidates_by_priority()[0].voice_id)
    assert len(voice_ids) == 4


def test_resolve_default_voice_id_from_shipped_narrator_profile(repo_root):
    assert resolve_default_voice_id(repo_root) == "bf_isabella"


def test_resolve_default_voice_id_follows_data_registry_override(tmp_path):
    override_dir = tmp_path / "data" / "registry" / "voice-profiles" / "narrator"
    override_dir.mkdir(parents=True)
    (override_dir / "1.0.0.yaml").write_text(minimal_raw_yaml("am_michael"))

    assert resolve_default_voice_id(tmp_path) == "am_michael"


def minimal_raw_yaml(voice_id: str) -> str:
    return (
        "persona: {name: Demo, description: x, style_prompt: y}\n"
        "tts:\n"
        "  candidates:\n"
        f"    - {{engine: kokoro, model: kokoro-v1.0, voice_id: {voice_id}, speed: 1.0, priority: 1, enabled: true}}\n"
        "  fallback: {mode: none, allow_quality_degrade: false}\n"
        "privacy: {local_only: true}\n"
        "limits: {max_seconds_per_utterance: 30}\n"
    )
