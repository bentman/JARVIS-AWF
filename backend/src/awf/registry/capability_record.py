"""Capability Record schema, loading, and validation (Section 9.1)."""

from dataclasses import dataclass
from pathlib import Path

import yaml

from awf.registry.schema import validate_json_schema, validate_registry_identity
from awf.registry.schemas.capability_records import SCHEMA


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


def parse_capability_record(raw: dict) -> CapabilityRecord:
    validate_json_schema(raw, SCHEMA, "capability record", error=CapabilityRecordValidationError)
    identity_raw = raw["identity"]
    schema_raw = raw["schema"]
    effects_raw = raw["effects"]

    identity = Identity(
        type=identity_raw["type"],
        provider=identity_raw["provider"],
        name=identity_raw["name"],
        version=identity_raw["version"],
    )
    effects = Effects(
        operation=effects_raw["operation"],
        reversible=effects_raw["reversible"],
        idempotent=effects_raw["idempotent"],
        external_side_effect=effects_raw["external_side_effect"],
    )

    constraints = raw.get("constraints", {})
    _validate_constraints(identity, effects, raw["risk_class"], constraints)
    return CapabilityRecord(
        identity=identity,
        schema_input=schema_raw["input"],
        schema_output=schema_raw["output"],
        effects=effects,
        risk_class=raw["risk_class"],
        approval=raw["approval"],
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
    record = parse_capability_record(raw)
    validate_registry_identity(
        name=record.identity.name,
        version=record.identity.version,
        path=path,
        context="capability record",
        error=CapabilityRecordValidationError,
    )
    return record
