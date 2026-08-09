"""Memory Profile schema, loading, and validation (ADR-0020)."""

from dataclasses import dataclass
from functools import partial
from pathlib import Path

import yaml

from awf.registry.model_profile import DATA_CLASSES
from awf.registry.schema import require, require_enum


class MemoryProfileValidationError(ValueError):
    pass


_require = partial(require, error=MemoryProfileValidationError)
_require_enum = partial(require_enum, error=MemoryProfileValidationError)


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
    api_version = _require(raw, "apiVersion", "memory profile")
    kind = _require(raw, "kind", "memory profile")
    metadata_raw = _require(raw, "metadata", "memory profile")
    spec_raw = _require(raw, "spec", "memory profile")
    retrieval_raw = _require(spec_raw, "retrieval", "spec")
    retention_raw = _require(spec_raw, "retention", "spec")
    embedding_raw = _require(spec_raw, "embedding", "spec")

    if api_version != "awf/v1":
        raise MemoryProfileValidationError("memory profile apiVersion must be awf/v1")
    if kind != "MemoryProfile":
        raise MemoryProfileValidationError("memory profile kind must be MemoryProfile")

    retrieval = MemoryRetrieval(
        max_items=int(_require(retrieval_raw, "maxItems", "spec.retrieval")),
        max_tokens=int(_require(retrieval_raw, "maxTokens", "spec.retrieval")),
        include_episodic=bool(_require(retrieval_raw, "includeEpisodic", "spec.retrieval")),
        include_semantic=bool(_require(retrieval_raw, "includeSemantic", "spec.retrieval")),
        min_confidence=float(_require(retrieval_raw, "minConfidence", "spec.retrieval")),
    )
    if retrieval.max_items < 1 or retrieval.max_tokens < 1:
        raise MemoryProfileValidationError("memory profile retrieval limits must be positive")
    if not 0.0 <= retrieval.min_confidence <= 1.0:
        raise MemoryProfileValidationError("memory profile minConfidence must be between 0.0 and 1.0")

    return MemoryProfile(
        api_version=api_version,
        kind=kind,
        metadata=MemoryProfileMetadata(
            name=_require(metadata_raw, "name", "metadata"),
            version=_require(metadata_raw, "version", "metadata"),
            digest=_require(metadata_raw, "digest", "metadata"),
        ),
        enabled=bool(_require(spec_raw, "enabled", "spec")),
        maximum_data_class=_require_enum(
            _require(spec_raw, "maximum_data_class", "spec"), DATA_CLASSES, "spec.maximum_data_class"
        ),
        retrieval=retrieval,
        retention=MemoryRetention(
            active_session_ttl_hours=int(_require(retention_raw, "activeSessionTtlHours", "spec.retention")),
            require_explicit_semantic_publish=bool(
                _require(retention_raw, "requireExplicitSemanticPublish", "spec.retention")
            ),
        ),
        embedding=MemoryEmbedding(
            enabled=bool(_require(embedding_raw, "enabled", "spec.embedding")),
            model_profile_ref=embedding_raw.get("modelProfileRef"),
            version=str(_require(embedding_raw, "version", "spec.embedding")),
        ),
    )


def load_memory_profile(path: Path) -> MemoryProfile:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise MemoryProfileValidationError(f"{path}: memory profile must be a YAML mapping")
    profile = parse_memory_profile(raw)
    if profile.metadata.name != path.parent.name:
        raise MemoryProfileValidationError(
            f"memory profile name '{profile.metadata.name}' does not match its registry directory '{path.parent.name}'"
        )
    if profile.metadata.version != path.stem:
        raise MemoryProfileValidationError(
            f"memory profile version '{profile.metadata.version}' does not match its file name '{path.stem}'"
        )
    return profile
