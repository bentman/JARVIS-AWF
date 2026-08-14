"""Semantic Memory schema, loading, and validation (ADR-0020)."""

from dataclasses import dataclass
from pathlib import Path

import yaml

from awf.registry.schema import validate_json_schema, validate_registry_identity
from awf.registry.schemas.semantic_memories import SCHEMA


class SemanticMemoryValidationError(ValueError):
    pass


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
    validate_json_schema(raw, SCHEMA, "semantic memory", error=SemanticMemoryValidationError)
    metadata_raw = raw["metadata"]
    spec_raw = raw["spec"]
    provenance_raw = spec_raw["provenance"]
    validity_raw = spec_raw["validity"]
    correction_raw = spec_raw["correction"]

    value = spec_raw["value"]
    _reject_secret_like(value)

    provenance = MemoryProvenance(
        source_type=provenance_raw["sourceType"],
        source_ref=provenance_raw["sourceRef"],
        artifact_id=provenance_raw.get("artifactId"),
        run_id=provenance_raw.get("runId"),
        event_id=provenance_raw.get("eventId"),
        observed_at=provenance_raw["observedAt"],
    )
    if not any((provenance.source_ref, provenance.artifact_id, provenance.run_id, provenance.event_id)):
        raise SemanticMemoryValidationError("semantic memory provenance must identify a source")

    return SemanticMemory(
        api_version=raw["apiVersion"],
        kind=raw["kind"],
        metadata=SemanticMemoryMetadata(
            name=metadata_raw["name"],
            version=metadata_raw["version"],
            digest=metadata_raw["digest"],
        ),
        subject=spec_raw["subject"],
        predicate=spec_raw["predicate"],
        value=value,
        memory_type=spec_raw["memoryType"],
        scope=spec_raw["scope"],
        confidence=spec_raw["confidence"],
        data_classification=spec_raw["data_classification"],
        provenance=provenance,
        validity=MemoryValidity(
            valid_from=validity_raw["validFrom"],
            valid_until=validity_raw.get("validUntil"),
        ),
        correction=MemoryCorrection(
            supersedes=correction_raw.get("supersedes"),
            corrected_by=correction_raw.get("correctedBy"),
            correction_reason=correction_raw.get("correctionReason"),
        ),
        pinned=spec_raw["pinned"],
        enabled=spec_raw["enabled"],
    )


def load_semantic_memory(path: Path) -> SemanticMemory:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise SemanticMemoryValidationError(f"{path}: semantic memory must be a YAML mapping")
    memory = parse_semantic_memory(raw)
    validate_registry_identity(
        name=memory.metadata.name,
        version=memory.metadata.version,
        path=path,
        context="semantic memory",
        error=SemanticMemoryValidationError,
    )
    return memory
