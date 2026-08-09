"""Semantic Memory schema, loading, and validation (ADR-0020)."""

from dataclasses import dataclass
from functools import partial
from pathlib import Path

import yaml

from awf.registry.model_profile import DATA_CLASSES
from awf.registry.schema import require, require_enum

MEMORY_TYPES = ("fact", "preference", "profile", "correction")
SOURCE_TYPES = ("operator", "run", "artifact", "manual")


class SemanticMemoryValidationError(ValueError):
    pass


_require = partial(require, error=SemanticMemoryValidationError)
_require_enum = partial(require_enum, error=SemanticMemoryValidationError)


@dataclass(frozen=True)
class SemanticMemoryMetadata:
    name: str
    version: str
    digest: str


@dataclass(frozen=True)
class MemoryProvenance:
    source_type: str
    source_ref: str
    artifact_id: str | None
    run_id: str | None
    event_id: str | None
    observed_at: str


@dataclass(frozen=True)
class MemoryValidity:
    valid_from: str
    valid_until: str | None


@dataclass(frozen=True)
class MemoryCorrection:
    supersedes: str | None
    corrected_by: str | None
    correction_reason: str | None


@dataclass(frozen=True)
class SemanticMemory:
    api_version: str
    kind: str
    metadata: SemanticMemoryMetadata
    subject: str
    predicate: str
    value: str
    memory_type: str
    scope: str
    confidence: float
    data_classification: str
    provenance: MemoryProvenance
    validity: MemoryValidity
    correction: MemoryCorrection
    pinned: bool
    enabled: bool

    @property
    def ref(self) -> str:
        return f"{self.metadata.name}@{self.metadata.version}"


def _reject_secret_like(value: str) -> None:
    lowered = value.lower()
    if "secret" in lowered or "api_key" in lowered or "api-key" in lowered or "sk-" in value:
        raise SemanticMemoryValidationError("semantic memory value appears to contain a secret")


def parse_semantic_memory(raw: dict) -> SemanticMemory:
    api_version = _require(raw, "apiVersion", "semantic memory")
    kind = _require(raw, "kind", "semantic memory")
    metadata_raw = _require(raw, "metadata", "semantic memory")
    spec_raw = _require(raw, "spec", "semantic memory")
    provenance_raw = _require(spec_raw, "provenance", "spec")
    validity_raw = _require(spec_raw, "validity", "spec")
    correction_raw = _require(spec_raw, "correction", "spec")

    if api_version != "awf/v1":
        raise SemanticMemoryValidationError("semantic memory apiVersion must be awf/v1")
    if kind != "SemanticMemory":
        raise SemanticMemoryValidationError("semantic memory kind must be SemanticMemory")

    value = str(_require(spec_raw, "value", "spec"))
    _reject_secret_like(value)
    confidence = float(_require(spec_raw, "confidence", "spec"))
    if not 0.0 <= confidence <= 1.0:
        raise SemanticMemoryValidationError("semantic memory confidence must be between 0.0 and 1.0")

    provenance = MemoryProvenance(
        source_type=_require_enum(_require(provenance_raw, "sourceType", "spec.provenance"), SOURCE_TYPES, "sourceType"),
        source_ref=str(_require(provenance_raw, "sourceRef", "spec.provenance")),
        artifact_id=provenance_raw.get("artifactId"),
        run_id=provenance_raw.get("runId"),
        event_id=provenance_raw.get("eventId"),
        observed_at=str(_require(provenance_raw, "observedAt", "spec.provenance")),
    )
    if not any((provenance.source_ref, provenance.artifact_id, provenance.run_id, provenance.event_id)):
        raise SemanticMemoryValidationError("semantic memory provenance must identify a source")

    return SemanticMemory(
        api_version=api_version,
        kind=kind,
        metadata=SemanticMemoryMetadata(
            name=_require(metadata_raw, "name", "metadata"),
            version=_require(metadata_raw, "version", "metadata"),
            digest=_require(metadata_raw, "digest", "metadata"),
        ),
        subject=str(_require(spec_raw, "subject", "spec")),
        predicate=str(_require(spec_raw, "predicate", "spec")),
        value=value,
        memory_type=_require_enum(_require(spec_raw, "memoryType", "spec"), MEMORY_TYPES, "memoryType"),
        scope=str(_require(spec_raw, "scope", "spec")),
        confidence=confidence,
        data_classification=_require_enum(
            _require(spec_raw, "data_classification", "spec"), DATA_CLASSES, "data_classification"
        ),
        provenance=provenance,
        validity=MemoryValidity(
            valid_from=str(_require(validity_raw, "validFrom", "spec.validity")),
            valid_until=validity_raw.get("validUntil"),
        ),
        correction=MemoryCorrection(
            supersedes=correction_raw.get("supersedes"),
            corrected_by=correction_raw.get("correctedBy"),
            correction_reason=correction_raw.get("correctionReason"),
        ),
        pinned=bool(_require(spec_raw, "pinned", "spec")),
        enabled=bool(_require(spec_raw, "enabled", "spec")),
    )


def load_semantic_memory(path: Path) -> SemanticMemory:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise SemanticMemoryValidationError(f"{path}: semantic memory must be a YAML mapping")
    memory = parse_semantic_memory(raw)
    if memory.metadata.name != path.parent.name:
        raise SemanticMemoryValidationError(
            f"semantic memory name '{memory.metadata.name}' does not match its registry directory '{path.parent.name}'"
        )
    if memory.metadata.version != path.stem:
        raise SemanticMemoryValidationError(
            f"semantic memory version '{memory.metadata.version}' does not match its file name '{path.stem}'"
        )
    return memory
