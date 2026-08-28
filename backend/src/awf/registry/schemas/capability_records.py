"""JSON Schema for this AWF registry object kind."""

IDENTITY_TYPES = ("mcp-tool", "activity", "cli-adapter-action")
OPERATIONS = ("read", "create", "update", "delete", "execute", "communicate")
RISK_CLASSES = ("R0", "R1", "R2", "R3")
APPROVAL_MODES = ("never", "per-run", "per-invocation")

SCHEMA = {
    "type": "object",
    "required": ["identity", "schema", "effects", "risk_class", "approval"],
    "properties": {
        "identity": {
            "type": "object",
            "required": ["type", "provider", "name", "version"],
            "properties": {
                "type": {"enum": list(IDENTITY_TYPES)},
                "provider": {"type": "string"},
                "name": {"type": "string"},
                "version": {"type": "string"},
            },
        },
        "schema": {
            "type": "object",
            "required": ["input", "output"],
            "properties": {"input": {"type": "string"}, "output": {"type": "string"}},
        },
        "effects": {
            "type": "object",
            "required": ["operation", "reversible", "idempotent", "external_side_effect"],
            "properties": {
                "operation": {"enum": list(OPERATIONS)},
                "reversible": {"type": "boolean"},
                "idempotent": {"type": "boolean"},
                "external_side_effect": {"type": "boolean"},
            },
        },
        "risk_class": {"enum": list(RISK_CLASSES)},
        "approval": {"enum": list(APPROVAL_MODES)},
        "constraints": {"type": "object"},
    },
}
