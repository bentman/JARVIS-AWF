"""JSON Schema for this AWF registry object kind."""

FUNCTIONS = ("stt", "tts", "vad", "wake")
KIND = "HardwareVoiceManifest"
VERSION = "1.0.0"

SCHEMA = {
    "type": "object",
    "required": ["apiVersion", "kind", "metadata", "spec"],
    "additionalProperties": False,
    "properties": {
        "apiVersion": {"const": "awf/v1"},
        "kind": {"const": KIND},
        "metadata": {
            "type": "object",
            "required": ["name", "version"],
            "additionalProperties": True,
            "properties": {
                "name": {"type": "string", "enum": list(FUNCTIONS)},
                "version": {"type": "string"},
                "digest": {"type": "string"},
            },
        },
        "spec": {
            "type": "object",
            "required": ["function"],
            "additionalProperties": False,
            "properties": {
                "function": {"type": "string", "enum": list(FUNCTIONS)},
                "files": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["name"],
                        "additionalProperties": False,
                        "properties": {
                            "name": {"type": "string", "minLength": 1},
                            "url": {"type": "string", "minLength": 1},
                            "package": {"type": "string", "minLength": 1},
                            "notes": {"type": "string"},
                        },
                    },
                },
                "classes": {
                    "type": "object",
                    "additionalProperties": {
                        "type": "object",
                        "required": ["model", "device", "compute_type"],
                        "additionalProperties": False,
                        "properties": {
                            "runtime": {"type": "string"},
                            "model": {"type": "string", "minLength": 1},
                            "local_path": {"type": ["string", "null"]},
                            "device": {"type": "string", "minLength": 1},
                            "compute_type": {"type": "string", "minLength": 1},
                        },
                    },
                },
                "notes": {"type": "string"},
            },
        },
    },
}
