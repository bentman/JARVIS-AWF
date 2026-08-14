"""JSON Schema for this AWF registry object kind."""

ROLES = ("builder", "verifier", "adversary")

SCHEMA = {
    "type": "object",
    "required": ["name", "version", "description", "adapter"],
    "properties": {
        "name": {"type": "string"},
        "version": {"type": "string"},
        "description": {"type": "string"},
        "adapter": {"type": "string"},
        "capabilities": {"type": "array", "items": {"type": "string"}},
        "role": {"enum": list(ROLES)},
        "mcp": {"type": "array", "items": {"type": "string"}},
        "skills": {
            "type": "array",
            "items": {
                "anyOf": [
                    {"type": "string"},
                    {
                        "type": "object",
                        "required": ["ref"],
                        "properties": {"ref": {"type": "string"}, "share": {"type": "boolean"}},
                    },
                ]
            },
        },
        "voice": {"type": "string"},
        "persona": {"type": "string"},
        "modelProfile": {"type": "string"},
    },
}
