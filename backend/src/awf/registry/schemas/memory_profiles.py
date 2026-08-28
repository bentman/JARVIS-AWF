"""JSON Schema for memory profile registry objects."""

from awf.registry.schemas.model_profiles import DATA_CLASSES

SCHEMA = {
    "type": "object",
    "required": ["apiVersion", "kind", "metadata", "spec"],
    "properties": {
        "apiVersion": {"const": "awf/v1"},
        "kind": {"const": "MemoryProfile"},
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
            "required": ["enabled", "maximum_data_class", "retrieval", "retention", "embedding"],
            "properties": {
                "enabled": {"type": "boolean"},
                "maximum_data_class": {"enum": list(DATA_CLASSES)},
                "retrieval": {
                    "type": "object",
                    "required": ["maxItems", "maxTokens", "includeEpisodic", "includeSemantic", "minConfidence"],
                    "properties": {
                        "maxItems": {"type": "integer", "minimum": 1},
                        "maxTokens": {"type": "integer", "minimum": 1},
                        "includeEpisodic": {"type": "boolean"},
                        "includeSemantic": {"type": "boolean"},
                        "minConfidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                    },
                },
                "retention": {
                    "type": "object",
                    "required": ["activeSessionTtlHours", "requireExplicitSemanticPublish"],
                    "properties": {
                        "activeSessionTtlHours": {"type": "integer"},
                        "requireExplicitSemanticPublish": {"type": "boolean"},
                    },
                },
                "embedding": {
                    "type": "object",
                    "required": ["enabled", "version"],
                    "properties": {
                        "enabled": {"type": "boolean"},
                        "modelProfileRef": {"type": ["string", "null"]},
                        "version": {"type": "string"},
                    },
                },
            },
        },
    },
}
