"""JSON Schema for this AWF registry object kind."""

FALLBACK_MODES = ("none", "ordered")

SCHEMA = {
    "type": "object",
    "required": ["name", "version", "persona_ref", "tts", "privacy", "limits"],
    "not": {"required": ["persona"]},
    "properties": {
        "name": {"type": "string"},
        "version": {"type": "string"},
        "persona_ref": {"type": "string"},
        "tts": {
            "type": "object",
            "required": ["candidates", "fallback"],
            "properties": {
                "candidates": {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                        "type": "object",
                        "required": ["engine", "model", "voice_id", "speed", "priority", "enabled"],
                        "properties": {
                            "engine": {"type": "string"},
                            "model": {"type": "string"},
                            "voice_id": {"type": "string"},
                            "speed": {"type": "number"},
                            "style": {"type": "object"},
                            "priority": {"type": "integer"},
                            "enabled": {"type": "boolean"},
                        },
                    },
                },
                "fallback": {
                    "type": "object",
                    "properties": {
                        "mode": {"enum": list(FALLBACK_MODES)},
                        "allow_quality_degrade": {"type": "boolean"},
                    },
                },
            },
        },
        "privacy": {
            "type": "object",
            "required": ["local_only"],
            "properties": {"local_only": {"type": "boolean"}},
        },
        "limits": {
            "type": "object",
            "required": ["max_seconds_per_utterance"],
            "properties": {"max_seconds_per_utterance": {"type": "integer"}},
        },
    },
}
