"""JSON Schema for this AWF registry object kind."""

TYPES = ("stdio", "http")

SCHEMA = {
    "type": "object",
    "required": ["name", "version", "type"],
    "properties": {
        "name": {"type": "string"},
        "version": {"type": "string"},
        "type": {"enum": list(TYPES)},
        "command": {"type": "string"},
        "args": {"type": "array", "items": {"type": "string"}},
        "url": {"type": "string"},
        "env": {"type": "object"},
        "env_secrets": {"type": "object"},
        "headers": {"type": "object"},
        "header_secrets": {"type": "object"},
        "startup_timeout_sec": {"type": "integer"},
        "tool_timeout_sec": {"type": "integer"},
        "tools": {"type": "array", "items": {"type": "string"}},
        "resources": {"type": "array", "items": {"type": "string"}},
        "prompts": {"type": "array", "items": {"type": "string"}},
    },
    "allOf": [
        {"if": {"properties": {"type": {"const": "stdio"}}}, "then": {"required": ["command"]}},
        {"if": {"properties": {"type": {"const": "http"}}}, "then": {"required": ["url"]}},
    ],
}
