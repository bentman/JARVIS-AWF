"""Voice Profile schema, loading, and validation (Section 16.5)."""

import sqlite3
from dataclasses import dataclass
from pathlib import Path

import yaml

from awf.registry.persona import Persona, load_persona
from awf.registry.resolve import resolve_registry_object
from awf.registry.schema import validate_json_schema, validate_registry_identity
from awf.registry.schemas.voice_profiles import SCHEMA

DEFAULT_VOICE_PROFILE_REF = "narrator@1.0.0"


class VoiceProfileValidationError(ValueError):
    pass


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
    validate_json_schema(raw, SCHEMA, "voice profile", error=VoiceProfileValidationError)
    tts_raw = raw["tts"]
    privacy_raw = raw["privacy"]
    limits_raw = raw["limits"]

    candidates_raw = tts_raw["candidates"]
    candidates = tuple(
        TtsCandidate(
            engine=c["engine"],
            model=c["model"],
            voice_id=c["voice_id"],
            speed=c["speed"],
            style=c.get("style", {}),
            priority=c["priority"],
            enabled=c["enabled"],
        )
        for c in candidates_raw
    )

    fallback_raw = tts_raw["fallback"]
    fallback = Fallback(
        mode=fallback_raw.get("mode", "none"),
        allow_quality_degrade=fallback_raw.get("allow_quality_degrade", False),
    )

    privacy = Privacy(local_only=privacy_raw["local_only"])
    limits = Limits(max_seconds_per_utterance=limits_raw["max_seconds_per_utterance"])

    return VoiceProfile(
        name=raw["name"],
        version=raw["version"],
        persona_ref=raw["persona_ref"],
        persona=None,
        candidates=candidates,
        fallback=fallback,
        privacy=privacy,
        limits=limits,
    )


def _resolve_persona(repo_root: Path, persona_ref: str, conn: sqlite3.Connection | None = None) -> Persona:
    name, sep, version = persona_ref.partition("@")
    if not sep or not name or not version:
        raise VoiceProfileValidationError(f"voice profile persona_ref must be '<name>@<version>', got {persona_ref!r}")
    path, _source = resolve_registry_object(repo_root, "personas", name, version, conn=conn)
    return load_persona(path)


def load_voice_profile(repo_root: Path, path: Path, conn: sqlite3.Connection | None = None) -> VoiceProfile:
    """`path` is `voice-profiles/<name>/<version>.yaml` - the parsed `name`
    and `version` MUST match the containing directory and the file's own
    stem, per the rule `load_skill` already applies to `SKILL.md`."""
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict):
        raise VoiceProfileValidationError(f"{path}: voice profile must be a YAML mapping")
    profile = parse_voice_profile(raw)
    validate_registry_identity(
        name=profile.name,
        version=profile.version,
        path=path,
        context="voice profile",
        error=VoiceProfileValidationError,
    )
    persona = _resolve_persona(repo_root, profile.persona_ref, conn=conn)
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
        raise VoiceProfileValidationError(f"voice profile '{DEFAULT_VOICE_PROFILE_REF}' has no enabled candidates")
    return candidates[0].voice_id
