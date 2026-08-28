"""JSON Schema for this AWF registry object kind."""

PURPOSES = ("general-reasoning", "coding", "judge", "adversary", "embedding")
DATA_CLASSES = ("public", "internal", "confidential")
FALLBACK_MODES = ("none", "ordered")

SCHEMA = {
    "type": "object",
    "required": ["name", "version", "purpose", "privacy", "candidates", "fallback", "limits"],
    "properties": {
        "name": {"type": "string"},
        "version": {"type": "string"},
        "purpose": {"enum": list(PURPOSES)},
        "privacy": {
            "type": "object",
            "required": ["maximum_data_class", "local_only"],
            "properties": {
                "maximum_data_class": {"enum": list(DATA_CLASSES)},
                "local_only": {"type": "boolean"},
            },
        },
        "candidates": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["provider", "model", "priority", "enabled"],
                "properties": {
                    "provider": {"type": "string"},
                    "model": {"type": "string"},
                    "priority": {"type": "integer"},
                    "enabled": {"type": "boolean"},
                    "api_base": {"type": ["string", "null"]},
                    "api_key_secret_name": {"type": ["string", "null"]},
                },
            },
        },
        "fallback": {
            "type": "object",
            "required": ["mode", "allow_quality_degrade"],
            "properties": {
                "mode": {"enum": list(FALLBACK_MODES)},
                "allow_quality_degrade": {"type": "boolean"},
            },
        },
        "limits": {
            "type": "object",
            "required": ["max_input_tokens_per_call", "max_output_tokens_per_call", "max_cost_usd_per_call"],
            "properties": {
                "max_input_tokens_per_call": {"type": "integer"},
                "max_output_tokens_per_call": {"type": "integer"},
                "max_cost_usd_per_call": {"type": "number"},
            },
        },
    },
}
