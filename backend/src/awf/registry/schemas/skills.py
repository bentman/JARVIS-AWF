"""JSON Schema for this AWF registry object kind."""

SCHEMA = {
    "type": "object",
    "required": ["name", "description"],
    "properties": {
        "name": {
            "type": "string",
            "minLength": 1,
            "maxLength": 64,
            "pattern": "^[a-z0-9]+(-[a-z0-9]+)*$",
        },
        "description": {"type": "string", "minLength": 1, "maxLength": 1024},
        "license": {"type": "string"},
        "compatibility": {"type": "string", "maxLength": 500},
        "metadata": {"type": "object"},
        "allowed-tools": {"type": "string"},
    },
}
