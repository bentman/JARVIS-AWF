"""Model Profile schema, loading, and validation (Section 11)."""

from dataclasses import dataclass
from functools import partial
from pathlib import Path

import yaml

from awf.registry.schema import require, require_enum

PURPOSES = ("general-reasoning", "coding", "judge", "adversary", "embedding")
DATA_CLASSES = ("public", "internal", "confidential")
FALLBACK_MODES = ("none", "ordered")


class ModelProfileValidationError(ValueError):
    pass


_require = partial(require, error=ModelProfileValidationError)
_require_enum = partial(require_enum, error=ModelProfileValidationError)


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
        return tuple(
            sorted((c for c in self.candidates if c.enabled), key=lambda c: c.priority)
        )


def parse_model_profile(raw: dict) -> ModelProfile:
    name = _require(raw, "name", "model profile")
    version = _require(raw, "version", "model profile")
    privacy_raw = _require(raw, "privacy", "model profile")
    candidates_raw = _require(raw, "candidates", "model profile")
    fallback_raw = _require(raw, "fallback", "model profile")
    limits_raw = _require(raw, "limits", "model profile")

    if not isinstance(candidates_raw, list) or not candidates_raw:
        raise ModelProfileValidationError("model profile: 'candidates' must be a non-empty list")

    privacy = Privacy(
        maximum_data_class=_require_enum(
            _require(privacy_raw, "maximum_data_class", "privacy"),
            DATA_CLASSES,
            "privacy.maximum_data_class",
        ),
        local_only=bool(_require(privacy_raw, "local_only", "privacy")),
    )

    candidates = tuple(
        Candidate(
            provider=_require(c, "provider", "candidate"),
            model=_require(c, "model", "candidate"),
            priority=int(_require(c, "priority", "candidate")),
            enabled=bool(_require(c, "enabled", "candidate")),
            api_base=c.get("api_base"),
            api_key_secret_name=c.get("api_key_secret_name"),
        )
        for c in candidates_raw
    )

    fallback = Fallback(
        mode=_require_enum(_require(fallback_raw, "mode", "fallback"), FALLBACK_MODES, "fallback.mode"),
        allow_quality_degrade=bool(_require(fallback_raw, "allow_quality_degrade", "fallback")),
    )

    limits = Limits(
        max_input_tokens_per_call=int(_require(limits_raw, "max_input_tokens_per_call", "limits")),
        max_output_tokens_per_call=int(_require(limits_raw, "max_output_tokens_per_call", "limits")),
        max_cost_usd_per_call=float(_require(limits_raw, "max_cost_usd_per_call", "limits")),
    )

    return ModelProfile(
        name=name,
        version=version,
        purpose=_require_enum(_require(raw, "purpose", "model profile"), PURPOSES, "purpose"),
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

    expected_name = path.parent.name
    if profile.name != expected_name:
        raise ModelProfileValidationError(
            f"model profile name '{profile.name}' does not match its registry directory '{expected_name}'"
        )
    expected_version = path.stem
    if profile.version != expected_version:
        raise ModelProfileValidationError(
            f"model profile version '{profile.version}' does not match its file name '{expected_version}'"
        )
    return profile
