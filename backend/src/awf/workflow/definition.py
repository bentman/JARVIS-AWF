"""Workflow Definition contract (Section 12.1): parsing and validation.

The registry envelope MUST include `apiVersion`, `kind`, and `metadata` with
`name`, `version`, and `digest`. The `spec` MUST contain `inputSchema`,
`outputSchema`, `budgets`, `nodes`, and `outputs`.
"""

from dataclasses import dataclass
from pathlib import Path

import yaml

from awf.registry.schema import validate_json_schema, validate_registry_identity
from awf.registry.schemas.workflows import SCHEMA
from awf.workflow.nodes import NodeValidationError, validate_node


class WorkflowValidationError(ValueError):
    pass


@dataclass(frozen=True)
class WorkflowMetadata:
    name: str
    version: str
    digest: str


@dataclass(frozen=True)
class WorkflowDefinition:
    api_version: str
    kind: str
    metadata: WorkflowMetadata
    input_schema: dict
    output_schema: dict
    budgets: dict
    nodes: tuple[dict, ...]
    outputs: dict

    @property
    def ref(self) -> str:
        return f"{self.metadata.name}@{self.metadata.version}"

    def node(self, node_id: str) -> dict:
        for node in self.nodes:
            if node["id"] == node_id:
                return node
        raise WorkflowValidationError(f"no node with id '{node_id}'")


def parse_workflow(raw: dict) -> WorkflowDefinition:
    validate_json_schema(raw, SCHEMA, "workflow", error=WorkflowValidationError)
    metadata_raw = raw["metadata"]
    spec_raw = raw["spec"]

    metadata = WorkflowMetadata(
        name=metadata_raw["name"],
        version=metadata_raw["version"],
        digest=metadata_raw["digest"],
    )

    nodes_raw = spec_raw["nodes"]
    for node in nodes_raw:
        try:
            validate_node(node)
        except NodeValidationError as exc:
            raise WorkflowValidationError(str(exc)) from exc
    node_ids = [node["id"] for node in nodes_raw]
    if len(node_ids) != len(set(node_ids)):
        raise WorkflowValidationError("spec.nodes contains duplicate node ids")

    return WorkflowDefinition(
        api_version=raw["apiVersion"],
        kind=raw["kind"],
        metadata=metadata,
        input_schema=spec_raw["inputSchema"],
        output_schema=spec_raw["outputSchema"],
        budgets=spec_raw["budgets"],
        nodes=tuple(nodes_raw),
        outputs=spec_raw["outputs"],
    )


def load_workflow(path: Path) -> WorkflowDefinition:
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict):
        raise WorkflowValidationError(f"{path}: workflow must be a YAML mapping")
    workflow = parse_workflow(raw)
    validate_registry_identity(
        name=workflow.metadata.name,
        version=workflow.metadata.version,
        path=path,
        context="workflow",
        error=WorkflowValidationError,
    )
    return workflow
