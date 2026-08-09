import pytest

from awf.registry.semantic_memory import SemanticMemoryValidationError, parse_semantic_memory


def valid_memory() -> dict:
    return {
        "apiVersion": "awf/v1",
        "kind": "SemanticMemory",
        "metadata": {"name": "operator-prefers-targeted-tests", "version": "1.0.0", "digest": "sha256:test"},
        "spec": {
            "subject": "operator",
            "predicate": "prefers",
            "value": "targeted tests before broad suites",
            "memoryType": "preference",
            "scope": "repo",
            "confidence": 0.9,
            "data_classification": "internal",
            "provenance": {
                "sourceType": "operator",
                "sourceRef": "manual-note",
                "artifactId": None,
                "runId": None,
                "eventId": None,
                "observedAt": "2026-08-09T00:00:00Z",
            },
            "validity": {"validFrom": "2026-08-09T00:00:00Z", "validUntil": None},
            "correction": {"supersedes": None, "correctedBy": None, "correctionReason": None},
            "pinned": False,
            "enabled": True,
        },
    }


def test_parse_semantic_memory_accepts_provenanced_memory():
    memory = parse_semantic_memory(valid_memory())

    assert memory.ref == "operator-prefers-targeted-tests@1.0.0"
    assert memory.provenance.source_type == "operator"


def test_parse_semantic_memory_rejects_secret_like_value():
    raw = valid_memory()
    raw["spec"]["value"] = "api_key=sk-test"

    with pytest.raises(SemanticMemoryValidationError):
        parse_semantic_memory(raw)
