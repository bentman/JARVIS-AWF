"""Model Profile schema, loading, and validation (Section 11)."""

from dataclasses import dataclass
from pathlib import Path

import yaml

from awf.registry.schema import validate_json_schema, validate_registry_identity
from awf.registry.schemas.model_profiles import SCHEMA


class ModelProfileValidationError(ValueError):
    pass


@dataclass(frozen=True)
class Privacy:
    maximum_data_class: str
    local_only: bool


@dataclass(frozen=True)
class Candidate:
    provider: str
    model: str
    priority: int
    enabled: bool
    api_base: str | None = None
    api_key_secret_name: str | None = None

    @property
    def litellm_model(self) -> str:
        return f"{self.provider}/{self.model}"


@dataclass(frozen=True)
class Fallback:
    mode: str
    allow_quality_degrade: bool


@dataclass(frozen=True)
class Limits:
    max_input_tokens_per_call: int
    max_output_tokens_per_call: int
    max_cost_usd_per_call: float


@dataclass(frozen=True)
class ModelProfile:
    name: str
    version: str
    purpose: str
    privacy: Privacy
    candidates: tuple[Candidate, ...]
    fallback: Fallback
    limits: Limits

    @property
    def ref(self) -> str:
        return f"{self.name}@{self.version}"

    def enabled_candidates_by_priority(self) -> tuple[Candidate, ...]:
        return tuple(sorted((c for c in self.candidates if c.enabled), key=lambda c: c.priority))


def parse_model_profile(raw: dict) -> ModelProfile:
    validate_json_schema(raw, SCHEMA, "model profile", error=ModelProfileValidationError)
    privacy_raw = raw["privacy"]
    candidates_raw = raw["candidates"]
    fallback_raw = raw["fallback"]
    limits_raw = raw["limits"]

    privacy = Privacy(
        maximum_data_class=privacy_raw["maximum_data_class"],
        local_only=privacy_raw["local_only"],
    )

    candidates = tuple(
        Candidate(
            provider=c["provider"],
            model=c["model"],
            priority=c["priority"],
            enabled=c["enabled"],
            api_base=c.get("api_base"),
            api_key_secret_name=c.get("api_key_secret_name"),
        )
        for c in candidates_raw
    )

    fallback = Fallback(
        mode=fallback_raw["mode"],
        allow_quality_degrade=fallback_raw["allow_quality_degrade"],
    )

    limits = Limits(
        max_input_tokens_per_call=limits_raw["max_input_tokens_per_call"],
        max_output_tokens_per_call=limits_raw["max_output_tokens_per_call"],
        max_cost_usd_per_call=limits_raw["max_cost_usd_per_call"],
    )

    return ModelProfile(
        name=raw["name"],
        version=raw["version"],
        purpose=raw["purpose"],
        privacy=privacy,
        candidates=candidates,
        fallback=fallback,
        limits=limits,
    )


def load_model_profile(path: Path) -> ModelProfile:
    """`path` is `model-profiles/<name>/<version>.yaml` - the parsed `name`
    and `version` MUST match the containing directory and the file's own
    stem, per the rule `load_skill` already applies to `SKILL.md`."""
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict):
        raise ModelProfileValidationError(f"{path}: model profile must be a YAML mapping")
    profile = parse_model_profile(raw)
    validate_registry_identity(
        name=profile.name,
        version=profile.version,
        path=path,
        context="model profile",
        error=ModelProfileValidationError,
    )
    return profile
