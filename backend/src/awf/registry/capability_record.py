"""Capability Record schema, loading, and validation (Section 9.1)."""

from dataclasses import dataclass
from functools import partial
from pathlib import Path

import yaml

from awf.registry.schema import require, require_enum

IDENTITY_TYPES = ("mcp-tool", "activity", "cli-adapter-action")
OPERATIONS = ("read", "create", "update", "delete", "execute", "communicate")
RISK_CLASSES = ("R0", "R1", "R2", "R3")
APPROVAL_MODES = ("never", "per-run", "per-invocation")


class CapabilityRecordValidationError(ValueError):
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
    constraints: dict

    @property
    def ref(self) -> str:
        return f"{self.identity.name}@{self.identity.version}"


_require = partial(require, error=CapabilityRecordValidationError)
_require_enum = partial(require_enum, error=CapabilityRecordValidationError)


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

    constraints = raw.get("constraints", {})
    _validate_constraints(identity, effects, risk_class, constraints)
    return CapabilityRecord(
        identity=identity,
        schema_input=_require(schema_raw, "input", "schema"),
        schema_output=_require(schema_raw, "output", "schema"),
        effects=effects,
        risk_class=_require_enum(risk_class, RISK_CLASSES, "risk_class"),
        approval=_require_enum(approval, APPROVAL_MODES, "approval"),
        constraints=constraints,
    )


def _validate_constraints(identity: Identity, effects: Effects, risk_class: str, constraints: dict) -> None:
    if not isinstance(constraints, dict):
        raise CapabilityRecordValidationError("constraints must be a mapping")
    machine_names = {"fs_read", "fs_write", "fs_delete", "command_run", "network_fetch"}
    if identity.type != "activity" or identity.name not in machine_names:
        return
    families = [name for name in ("filesystem", "command", "network") if name in constraints]
    if len(families) != 1:
        raise CapabilityRecordValidationError(f"{identity.name}: exactly one machine constraint family is required")
    family = families[0]
    if identity.name.startswith("fs_") and family != "filesystem":
        raise CapabilityRecordValidationError(f"{identity.name}: requires filesystem constraints")
    if identity.name == "command_run" and family != "command":
        raise CapabilityRecordValidationError("command_run: requires command constraints")
    if identity.name == "network_fetch" and family != "network":
        raise CapabilityRecordValidationError("network_fetch: requires network constraints")
    if risk_class == "R0" and effects.operation != "read":
        raise CapabilityRecordValidationError("R0 machine capabilities must be read-only")
    if family == "network":
        network_constraints = constraints[family]
        if not network_constraints.get("allowedMethods"):
            raise CapabilityRecordValidationError("network constraints require allowedMethods")
        allowed_hosts = network_constraints.get("allowedHosts")
        if not isinstance(allowed_hosts, list) or not allowed_hosts:
            raise CapabilityRecordValidationError("network constraints require non-empty allowedHosts")
    if family == "command" and int(constraints[family].get("timeoutSeconds", 0)) < 1:
        raise CapabilityRecordValidationError("command constraints require positive timeoutSeconds")


def load_capability_record(path: Path) -> CapabilityRecord:
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict):
        raise CapabilityRecordValidationError(f"{path}: capability record must be a YAML mapping")
    return parse_capability_record(raw)
