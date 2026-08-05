import pytest

from awf.workflow.definition import (
    WorkflowValidationError,
    load_workflow,
    parse_workflow,
)


def minimal_raw(**overrides):
    raw = {
        "apiVersion": "awf/v1",
        "kind": "Workflow",
        "metadata": {"name": "demo", "version": "1.0.0", "digest": "sha256:abc"},
        "spec": {
            "inputSchema": {},
            "outputSchema": {},
            "budgets": {},
            "nodes": [{"id": "a", "type": "activity", "function": "hardware_probe"}],
            "outputs": {},
        },
    }
    raw.update(overrides)
    return raw


def test_parse_minimal_workflow():
    workflow = parse_workflow(minimal_raw())
    assert workflow.ref == "demo@1.0.0"
    assert workflow.node("a")["type"] == "activity"


def test_parse_rejects_missing_metadata():
    raw = minimal_raw()
    del raw["metadata"]
    with pytest.raises(WorkflowValidationError):
        parse_workflow(raw)


def test_parse_rejects_missing_spec_key():
    raw = minimal_raw()
    del raw["spec"]["budgets"]
    with pytest.raises(WorkflowValidationError):
        parse_workflow(raw)


def test_parse_rejects_empty_nodes():
    raw = minimal_raw()
    raw["spec"]["nodes"] = []
    with pytest.raises(WorkflowValidationError):
        parse_workflow(raw)


def test_parse_rejects_duplicate_node_ids():
    raw = minimal_raw()
    raw["spec"]["nodes"] = [
        {"id": "a", "type": "activity", "function": "hardware_probe"},
        {"id": "a", "type": "activity", "function": "hardware_probe"},
    ]
    with pytest.raises(WorkflowValidationError):
        parse_workflow(raw)


def test_parse_propagates_node_validation_error():
    raw = minimal_raw()
    raw["spec"]["nodes"] = [{"id": "a", "type": "not-a-real-type"}]
    with pytest.raises(WorkflowValidationError):
        parse_workflow(raw)


def test_node_lookup_raises_for_unknown_id():
    workflow = parse_workflow(minimal_raw())
    with pytest.raises(WorkflowValidationError):
        workflow.node("does-not-exist")


def test_load_real_example_workflow(repo_root):
    real_workflow = (
        repo_root / "config" / "app_registry" / "workflows" / "produce-gate-repair-demo" / "1.0.0.yaml"
    )
    workflow = load_workflow(real_workflow)
    assert workflow.ref == "produce-gate-repair-demo@1.0.0"
    assert [n["id"] for n in workflow.nodes] == ["produce", "check", "repair"]
    assert workflow.budgets["maxRepairIterations"] == 3
