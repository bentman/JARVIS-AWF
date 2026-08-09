import pytest

from awf.registry.memory_profile import MemoryProfileValidationError, parse_memory_profile


def valid_profile() -> dict:
    return {
        "apiVersion": "awf/v1",
        "kind": "MemoryProfile",
        "metadata": {"name": "default", "version": "1.0.0", "digest": "sha256:test"},
        "spec": {
            "enabled": True,
            "maximum_data_class": "internal",
            "retrieval": {
                "maxItems": 5,
                "maxTokens": 1000,
                "includeEpisodic": True,
                "includeSemantic": True,
                "minConfidence": 0.5,
            },
            "retention": {"activeSessionTtlHours": 24, "requireExplicitSemanticPublish": True},
            "embedding": {"enabled": False, "modelProfileRef": None, "version": "none"},
        },
    }


def test_parse_memory_profile_accepts_default_shape():
    profile = parse_memory_profile(valid_profile())

    assert profile.ref == "default@1.0.0"
    assert profile.retrieval.include_semantic is True
    assert profile.maximum_data_class == "internal"


def test_parse_memory_profile_rejects_invalid_limits():
    raw = valid_profile()
    raw["spec"]["retrieval"]["maxItems"] = 0

    with pytest.raises(MemoryProfileValidationError):
        parse_memory_profile(raw)
