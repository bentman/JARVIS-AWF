"""JSON Schema for this AWF registry object kind."""

SCHEMA = {
    "type": "object",
    "required": ["apiVersion", "kind", "metadata", "spec"],
    "properties": {
        "apiVersion": {"const": "awf/v1"},
        "kind": {"const": "Workflow"},
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
            "required": ["inputSchema", "outputSchema", "budgets", "nodes", "outputs"],
            "properties": {
                "inputSchema": {"type": "object"},
                "outputSchema": {"type": "object"},
                "budgets": {"type": "object"},
                "nodes": {"type": "array", "minItems": 1},
                "outputs": {"type": "object"},
            },
        },
    },
}
