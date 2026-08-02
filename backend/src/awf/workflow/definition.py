"""Workflow Definition contract (Section 12.1): parsing and validation.

The registry envelope MUST include `apiVersion`, `kind`, and `metadata` with
`name`, `version`, and `digest`. The `spec` MUST contain `inputSchema`,
`outputSchema`, `budgets`, `nodes`, and `outputs`.
"""

from dataclasses import dataclass
from pathlib import Path

import yaml

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


def _require(mapping: dict, key: str, context: str) -> object:
    if key not in mapping:
        raise WorkflowValidationError(f"{context}: missing required field '{key}'")
    return mapping[key]


def parse_workflow(raw: dict) -> WorkflowDefinition:
    api_version = _require(raw, "apiVersion", "workflow")
    kind = _require(raw, "kind", "workflow")
    metadata_raw = _require(raw, "metadata", "workflow")
    spec_raw = _require(raw, "spec", "workflow")

    metadata = WorkflowMetadata(
        name=_require(metadata_raw, "name", "metadata"),
        version=_require(metadata_raw, "version", "metadata"),
        digest=_require(metadata_raw, "digest", "metadata"),
    )

    nodes_raw = _require(spec_raw, "nodes", "spec")
    if not isinstance(nodes_raw, list) or not nodes_raw:
        raise WorkflowValidationError("spec.nodes must be a non-empty list")
    for node in nodes_raw:
        try:
            validate_node(node)
        except NodeValidationError as exc:
            raise WorkflowValidationError(str(exc)) from exc
    node_ids = [node["id"] for node in nodes_raw]
    if len(node_ids) != len(set(node_ids)):
        raise WorkflowValidationError("spec.nodes contains duplicate node ids")

    return WorkflowDefinition(
        api_version=api_version,
        kind=kind,
        metadata=metadata,
        input_schema=_require(spec_raw, "inputSchema", "spec"),
        output_schema=_require(spec_raw, "outputSchema", "spec"),
        budgets=_require(spec_raw, "budgets", "spec"),
        nodes=tuple(nodes_raw),
        outputs=_require(spec_raw, "outputs", "spec"),
    )


def load_workflow(path: Path) -> WorkflowDefinition:
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict):
        raise WorkflowValidationError(f"{path}: workflow must be a YAML mapping")
    return parse_workflow(raw)
