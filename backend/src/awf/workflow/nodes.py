"""Workflow node types (Section 12.2) - eight, exactly."""

NODE_TYPES = (
    "activity",
    "agent",
    "approval",
    "gate",
    "subworkflow",
    "map",
    "loop",
    "handoff",
)

# Fields a node of this type MUST declare, beyond the universal `id`/`type`.
# handoff's four fields are Section 13.4's explicit "MUST declare" list:
# the initiating and receiving Agent references, a structured handoff
# payload schema, and maxHops (required, no default).
REQUIRED_FIELDS_BY_TYPE = {
    "activity": ("function",),
    "subworkflow": ("workflowRef",),
    "map": ("maxItems", "maxConcurrency", "workflowRef", "items"),
    "loop": ("maxIterations", "workflowRef"),
    "handoff": ("initiatingAgent", "receivingAgent", "payloadSchema", "maxHops"),
}


class NodeValidationError(ValueError):
    pass


def validate_node(node: dict) -> None:
    if "id" not in node:
        raise NodeValidationError("node missing required field 'id'")
    node_id = node["id"]

    if "type" not in node:
        raise NodeValidationError(f"node '{node_id}': missing required field 'type'")
    node_type = node["type"]
    if node_type not in NODE_TYPES:
        raise NodeValidationError(f"node '{node_id}': type '{node_type}' not in {NODE_TYPES}")

    for field in REQUIRED_FIELDS_BY_TYPE.get(node_type, ()):
        if field not in node:
            raise NodeValidationError(
                f"node '{node_id}' (type={node_type}): missing required field '{field}'"
            )
