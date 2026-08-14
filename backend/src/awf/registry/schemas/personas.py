"""JSON Schema for this AWF registry object kind."""

TRAIT_LEVELS = ("none", "low", "medium", "high", "strong")
HUMOR_LEVELS = ("none", "light", "medium", "high", "dry")

SCHEMA = {
    "type": "object",
    "required": [
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
    ],
    "properties": {
        "name": {"type": "string"},
        "version": {"type": "string"},
        "display_name": {"type": "string"},
        "description": {"type": "string"},
        "locale": {"type": "string"},
        "system": {"type": "string"},
        "style": {
            "type": "object",
            "required": ["max_words_default", "structure", "do", "avoid"],
            "properties": {
                "max_words_default": {"type": "integer"},
                "structure": {"type": "string"},
                "do": {"type": "array", "items": {"type": "string"}},
                "avoid": {"type": "array", "items": {"type": "string"}},
            },
        },
        "traits": {
            "type": "object",
            "required": ["warmth", "assertiveness", "detail", "humor"],
            "properties": {
                "warmth": {"enum": list(TRAIT_LEVELS)},
                "assertiveness": {"enum": list(TRAIT_LEVELS)},
                "detail": {"enum": list(TRAIT_LEVELS)},
                "humor": {"enum": list(HUMOR_LEVELS)},
            },
        },
        "examples": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["user", "assistant"],
                "properties": {"user": {"type": "string"}, "assistant": {"type": "string"}},
            },
        },
        "generation": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "temperature": {"type": "number"},
                "top_p": {"type": "number"},
                "top_k": {"type": "integer"},
                "repeat_penalty": {"type": "number"},
                "max_tokens": {"type": "integer"},
                "stop": {"type": "array", "items": {"type": "string"}},
            },
        },
        "enabled": {"type": "boolean"},
    },
}
