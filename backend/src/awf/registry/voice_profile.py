"""Voice Profile schema, loading, and validation (Section 16.5)."""

from dataclasses import dataclass
from functools import partial
from pathlib import Path

import yaml

from awf.registry.persona import Persona, load_persona
from awf.registry.resolve import resolve_registry_object
from awf.registry.schema import require, require_enum

FALLBACK_MODES = ("none", "ordered")

DEFAULT_VOICE_PROFILE_REF = "narrator@1.0.0"


class VoiceProfileValidationError(ValueError):
    pass


_require = partial(require, error=VoiceProfileValidationError)
_require_enum = partial(require_enum, error=VoiceProfileValidationError)


@dataclass(frozen=True)
class TtsCandidate:
    engine: str
    model: str
    voice_id: str
    speed: float
    style: dict
    priority: int
    enabled: bool


@dataclass(frozen=True)
class Fallback:
    mode: str
    allow_quality_degrade: bool


@dataclass(frozen=True)
class Privacy:
    local_only: bool


@dataclass(frozen=True)
class Limits:
    max_seconds_per_utterance: int


@dataclass(frozen=True)
class VoiceProfile:
    name: str
    version: str
    persona_ref: str
    persona: Persona | None
    candidates: tuple[TtsCandidate, ...]
    fallback: Fallback
    privacy: Privacy
    limits: Limits

    @property
    def ref(self) -> str:
        return f"{self.name}@{self.version}"

    def enabled_candidates_by_priority(self) -> tuple[TtsCandidate, ...]:
        return tuple(sorted((c for c in self.candidates if c.enabled), key=lambda c: c.priority))


def parse_voice_profile(raw: dict) -> VoiceProfile:
    if "persona" in raw:
        raise VoiceProfileValidationError("voice profile: 'persona' is replaced by 'persona_ref' (ADR-0018)")
    name = _require(raw, "name", "voice profile")
    version = _require(raw, "version", "voice profile")
    persona_ref = _require(raw, "persona_ref", "voice profile")
    tts_raw = _require(raw, "tts", "voice profile")
    privacy_raw = _require(raw, "privacy", "voice profile")
    limits_raw = _require(raw, "limits", "voice profile")

    candidates_raw = _require(tts_raw, "candidates", "tts")
    if not isinstance(candidates_raw, list) or not candidates_raw:
        raise VoiceProfileValidationError("tts.candidates must be a non-empty list")
    candidates = tuple(
        TtsCandidate(
            engine=_require(c, "engine", "candidate"),
            model=_require(c, "model", "candidate"),
            voice_id=_require(c, "voice_id", "candidate"),
            speed=float(_require(c, "speed", "candidate")),
            style=c.get("style", {}),
            priority=int(_require(c, "priority", "candidate")),
            enabled=bool(_require(c, "enabled", "candidate")),
        )
        for c in candidates_raw
    )

    fallback_raw = _require(tts_raw, "fallback", "tts")
    fallback = Fallback(
        mode=_require_enum(fallback_raw.get("mode", "none"), FALLBACK_MODES, "tts.fallback.mode"),
        allow_quality_degrade=bool(fallback_raw.get("allow_quality_degrade", False)),
    )

    privacy = Privacy(local_only=bool(_require(privacy_raw, "local_only", "privacy")))
    limits = Limits(
        max_seconds_per_utterance=int(_require(limits_raw, "max_seconds_per_utterance", "limits"))
    )

    return VoiceProfile(
        name=name, version=version, persona_ref=persona_ref, persona=None, candidates=candidates,
        fallback=fallback, privacy=privacy, limits=limits,
    )


def _resolve_persona(repo_root: Path, persona_ref: str) -> Persona:
    name, sep, version = persona_ref.partition("@")
    if not sep or not name or not version:
        raise VoiceProfileValidationError(f"voice profile persona_ref must be '<name>@<version>', got {persona_ref!r}")
    path, _source = resolve_registry_object(repo_root, "personas", name, version)
    return load_persona(path)


def load_voice_profile(repo_root: Path, path: Path) -> VoiceProfile:
    """`path` is `voice-profiles/<name>/<version>.yaml` - the parsed `name`
    and `version` MUST match the containing directory and the file's own
    stem, per the rule `load_skill` already applies to `SKILL.md`."""
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict):
        raise VoiceProfileValidationError(f"{path}: voice profile must be a YAML mapping")
    profile = parse_voice_profile(raw)

    expected_name = path.parent.name
    if profile.name != expected_name:
        raise VoiceProfileValidationError(
            f"voice profile name '{profile.name}' does not match its registry directory '{expected_name}'"
        )
    expected_version = path.stem
    if profile.version != expected_version:
        raise VoiceProfileValidationError(
            f"voice profile version '{profile.version}' does not match its file name '{expected_version}'"
        )
    persona = _resolve_persona(repo_root, profile.persona_ref)
    return VoiceProfile(
        name=profile.name,
        version=profile.version,
        persona_ref=profile.persona_ref,
        persona=persona,
        candidates=profile.candidates,
        fallback=profile.fallback,
        privacy=profile.privacy,
        limits=profile.limits,
    )


def resolve_default_voice_id(repo_root: Path) -> str:
    name, _, version = DEFAULT_VOICE_PROFILE_REF.partition("@")
    path, _source = resolve_registry_object(repo_root, "voice-profiles", name, version)
    profile = load_voice_profile(repo_root, path)
    candidates = profile.enabled_candidates_by_priority()
    if not candidates:
        raise VoiceProfileValidationError(
            f"voice profile '{DEFAULT_VOICE_PROFILE_REF}' has no enabled candidates"
        )
    return candidates[0].voice_id
