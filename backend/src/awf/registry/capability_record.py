"""Capability Record schema, loading, and validation (Section 9.1)."""

from dataclasses import dataclass
from pathlib import Path

import yaml

IDENTITY_TYPES = ("mcp-tool", "activity", "cli-adapter-action")
OPERATIONS = ("read", "create", "update", "delete", "execute", "communicate")
RISK_CLASSES = ("R0", "R1", "R2", "R3")
APPROVAL_MODES = ("never", "per-run", "per-invocation")


class RegistryValidationError(ValueError):
    pass


@dataclass(frozen=True)
class Identity:
    type: str
    provider: str
    name: str
    version: str


@dataclass(frozen=True)
class Effects:
    operation: str
    reversible: bool
    idempotent: bool
    external_side_effect: bool


@dataclass(frozen=True)
class CapabilityRecord:
    identity: Identity
    schema_input: str
    schema_output: str
    effects: Effects
    risk_class: str
    approval: str

    @property
    def ref(self) -> str:
        return f"{self.identity.name}@{self.identity.version}"


def _require(mapping: dict, key: str, context: str) -> object:
    if key not in mapping:
        raise RegistryValidationError(f"{context}: missing required field '{key}'")
    return mapping[key]


def _require_enum(value: object, allowed: tuple[str, ...], context: str) -> str:
    if value not in allowed:
        raise RegistryValidationError(f"{context}: '{value}' not in {allowed}")
    return value  # type: ignore[return-value]


def parse_capability_record(raw: dict) -> CapabilityRecord:
    identity_raw = _require(raw, "identity", "capability record")
    schema_raw = _require(raw, "schema", "capability record")
    effects_raw = _require(raw, "effects", "capability record")
    risk_class = _require(raw, "risk_class", "capability record")
    approval = _require(raw, "approval", "capability record")

    identity = Identity(
        type=_require_enum(_require(identity_raw, "type", "identity"), IDENTITY_TYPES, "identity.type"),
        provider=_require(identity_raw, "provider", "identity"),
        name=_require(identity_raw, "name", "identity"),
        version=_require(identity_raw, "version", "identity"),
    )
    effects = Effects(
        operation=_require_enum(_require(effects_raw, "operation", "effects"), OPERATIONS, "effects.operation"),
        reversible=bool(_require(effects_raw, "reversible", "effects")),
        idempotent=bool(_require(effects_raw, "idempotent", "effects")),
        external_side_effect=bool(_require(effects_raw, "external_side_effect", "effects")),
    )

    return CapabilityRecord(
        identity=identity,
        schema_input=_require(schema_raw, "input", "schema"),
        schema_output=_require(schema_raw, "output", "schema"),
        effects=effects,
        risk_class=_require_enum(risk_class, RISK_CLASSES, "risk_class"),
        approval=_require_enum(approval, APPROVAL_MODES, "approval"),
    )


def load_capability_record(path: Path) -> CapabilityRecord:
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict):
        raise RegistryValidationError(f"{path}: capability record must be a YAML mapping")
    return parse_capability_record(raw)
