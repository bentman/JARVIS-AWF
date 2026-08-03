import pytest

from awf.workflow.nodes import NODE_TYPES, NodeValidationError, validate_node


def test_all_eight_types_recognized():
    assert len(NODE_TYPES) == 8
    for node_type in NODE_TYPES:
        validate_node({"id": "n", "type": node_type, **_required_extra(node_type)})


def _required_extra(node_type):
    return {
        "subworkflow": {"workflowRef": "child@1.0.0"},
        "map": {"maxItems": 5, "maxConcurrency": 2, "workflowRef": "child@1.0.0", "items": [1, 2]},
        "loop": {"maxIterations": 3, "workflowRef": "child@1.0.0"},
        "handoff": {
            "initiatingAgent": {"adapter": "claude-code", "objective": "x"},
            "receivingAgent": {"adapter": "codex", "objective": "y"},
            "payloadSchema": {"type": "object"},
            "maxHops": 4,
        },
    }.get(node_type, {})


def test_rejects_missing_id():
    with pytest.raises(NodeValidationError):
        validate_node({"type": "activity"})


def test_rejects_missing_type():
    with pytest.raises(NodeValidationError):
        validate_node({"id": "n"})


def test_rejects_unknown_type():
    with pytest.raises(NodeValidationError):
        validate_node({"id": "n", "type": "not-a-real-type"})


def test_map_requires_max_items_and_concurrency():
    with pytest.raises(NodeValidationError):
        validate_node({"id": "n", "type": "map", "maxItems": 5})
    with pytest.raises(NodeValidationError):
        validate_node({"id": "n", "type": "map", "maxConcurrency": 2})


def test_loop_requires_max_iterations():
    with pytest.raises(NodeValidationError):
        validate_node({"id": "n", "type": "loop"})


def test_handoff_requires_max_hops():
    with pytest.raises(NodeValidationError):
        validate_node(
            {
                "id": "n",
                "type": "handoff",
                "initiatingAgent": {"adapter": "claude-code", "objective": "x"},
                "receivingAgent": {"adapter": "codex", "objective": "y"},
                "payloadSchema": {"type": "object"},
            }
        )


def test_handoff_requires_agent_references_and_payload_schema():
    with pytest.raises(NodeValidationError):
        validate_node({"id": "n", "type": "handoff", "maxHops": 4})
