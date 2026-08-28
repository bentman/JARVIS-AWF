"""JSON Schema for this AWF registry object kind."""

from awf.registry.schemas.model_profiles import DATA_CLASSES

MEMORY_TYPES = ("fact", "preference", "profile", "correction")
SOURCE_TYPES = ("operator", "run", "artifact", "manual")

SCHEMA = {
    "type": "object",
    "required": ["apiVersion", "kind", "metadata", "spec"],
    "properties": {
        "apiVersion": {"const": "awf/v1"},
        "kind": {"const": "SemanticMemory"},
        "metadata": {
            "type": "object",
            "required": ["name", "version", "digest"],
            "properties": {
                "name": {"type": "string"},
                "version": {"type": "string"},
                "digest": {"type": "string"},
            },
        },
        "spec": {
            "type": "object",
            "required": [
                "subject",
                "predicate",
                "value",
                "memoryType",
                "scope",
                "confidence",
                "data_classification",
                "provenance",
                "validity",
                "correction",
                "pinned",
                "enabled",
            ],
            "properties": {
                "subject": {"type": "string"},
                "predicate": {"type": "string"},
                "value": {"type": "string"},
                "memoryType": {"enum": list(MEMORY_TYPES)},
                "scope": {"type": "string"},
                "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                "data_classification": {"enum": list(DATA_CLASSES)},
                "provenance": {
                    "type": "object",
                    "required": ["sourceType", "sourceRef", "observedAt"],
                    "properties": {
                        "sourceType": {"enum": list(SOURCE_TYPES)},
                        "sourceRef": {"type": "string"},
                        "artifactId": {"type": ["string", "null"]},
                        "runId": {"type": ["string", "null"]},
                        "eventId": {"type": ["string", "null"]},
                        "observedAt": {"type": "string"},
                    },
                },
                "validity": {
                    "type": "object",
                    "required": ["validFrom"],
                    "properties": {
                        "validFrom": {"type": "string"},
                        "validUntil": {"type": ["string", "null"]},
                    },
                },
                "correction": {
                    "type": "object",
                    "properties": {
                        "supersedes": {"type": ["string", "null"]},
                        "correctedBy": {"type": ["string", "null"]},
                        "correctionReason": {"type": ["string", "null"]},
                    },
                },
                "pinned": {"type": "boolean"},
                "enabled": {"type": "boolean"},
            },
        },
    },
}
