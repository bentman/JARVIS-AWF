"""Memory Profile schema, loading, and validation (ADR-0020)."""

from dataclasses import dataclass
from pathlib import Path

import yaml

from awf.registry.schema import validate_json_schema, validate_registry_identity
from awf.registry.schemas.memory_profiles import SCHEMA


class MemoryProfileValidationError(ValueError):
    pass


@dataclass(frozen=True)
class MemoryProfileMetadata:
    name: str
    version: str
    digest: str


@dataclass(frozen=True)
class MemoryRetrieval:
    max_items: int
    max_tokens: int
    include_episodic: bool
    include_semantic: bool
    min_confidence: float


@dataclass(frozen=True)
class MemoryRetention:
    active_session_ttl_hours: int
    require_explicit_semantic_publish: bool


@dataclass(frozen=True)
class MemoryEmbedding:
    enabled: bool
    model_profile_ref: str | None
    version: str


@dataclass(frozen=True)
class MemoryProfile:
    api_version: str
    kind: str
    metadata: MemoryProfileMetadata
    enabled: bool
    maximum_data_class: str
    retrieval: MemoryRetrieval
    retention: MemoryRetention
    embedding: MemoryEmbedding

    @property
    def ref(self) -> str:
        return f"{self.metadata.name}@{self.metadata.version}"


def parse_memory_profile(raw: dict) -> MemoryProfile:
    validate_json_schema(raw, SCHEMA, "memory profile", error=MemoryProfileValidationError)
    metadata_raw = raw["metadata"]
    spec_raw = raw["spec"]
    retrieval_raw = spec_raw["retrieval"]
    retention_raw = spec_raw["retention"]
    embedding_raw = spec_raw["embedding"]

    retrieval = MemoryRetrieval(
        max_items=retrieval_raw["maxItems"],
        max_tokens=retrieval_raw["maxTokens"],
        include_episodic=retrieval_raw["includeEpisodic"],
        include_semantic=retrieval_raw["includeSemantic"],
        min_confidence=retrieval_raw["minConfidence"],
    )

    return MemoryProfile(
        api_version=raw["apiVersion"],
        kind=raw["kind"],
        metadata=MemoryProfileMetadata(
            name=metadata_raw["name"],
            version=metadata_raw["version"],
            digest=metadata_raw["digest"],
        ),
        enabled=spec_raw["enabled"],
        maximum_data_class=spec_raw["maximum_data_class"],
        retrieval=retrieval,
        retention=MemoryRetention(
            active_session_ttl_hours=retention_raw["activeSessionTtlHours"],
            require_explicit_semantic_publish=retention_raw["requireExplicitSemanticPublish"],
        ),
        embedding=MemoryEmbedding(
            enabled=embedding_raw["enabled"],
            model_profile_ref=embedding_raw.get("modelProfileRef"),
            version=embedding_raw["version"],
        ),
    )


def load_memory_profile(path: Path) -> MemoryProfile:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise MemoryProfileValidationError(f"{path}: memory profile must be a YAML mapping")
    profile = parse_memory_profile(raw)
    validate_registry_identity(
        name=profile.metadata.name,
        version=profile.metadata.version,
        path=path,
        context="memory profile",
        error=MemoryProfileValidationError,
    )
    return profile
