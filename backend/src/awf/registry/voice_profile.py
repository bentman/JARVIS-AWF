"""Voice Profile schema, loading, and validation (Section 16.5)."""

from dataclasses import dataclass
from pathlib import Path

import yaml

FALLBACK_MODES = ("none", "ordered")


class VoiceProfileValidationError(ValueError):
    pass


@dataclass(frozen=True)
class Persona:
    name: str
    description: str
    style_prompt: str


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
    persona: Persona
    candidates: tuple[TtsCandidate, ...]
    fallback: Fallback
    privacy: Privacy
    limits: Limits

    def enabled_candidates_by_priority(self) -> tuple[TtsCandidate, ...]:
        return tuple(sorted((c for c in self.candidates if c.enabled), key=lambda c: c.priority))


def _require(mapping: dict, key: str, context: str) -> object:
    if key not in mapping:
        raise VoiceProfileValidationError(f"{context}: missing required field '{key}'")
    return mapping[key]


def parse_voice_profile(raw: dict) -> VoiceProfile:
    persona_raw = _require(raw, "persona", "voice profile")
    tts_raw = _require(raw, "tts", "voice profile")
    privacy_raw = _require(raw, "privacy", "voice profile")
    limits_raw = _require(raw, "limits", "voice profile")

    persona = Persona(
        name=_require(persona_raw, "name", "persona"),
        description=_require(persona_raw, "description", "persona"),
        style_prompt=_require(persona_raw, "style_prompt", "persona"),
    )

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
        mode=fallback_raw.get("mode", "none"),
        allow_quality_degrade=bool(fallback_raw.get("allow_quality_degrade", False)),
    )
    if fallback.mode not in FALLBACK_MODES:
        raise VoiceProfileValidationError(f"tts.fallback.mode: '{fallback.mode}' not in {FALLBACK_MODES}")

    privacy = Privacy(local_only=bool(_require(privacy_raw, "local_only", "privacy")))
    limits = Limits(
        max_seconds_per_utterance=int(_require(limits_raw, "max_seconds_per_utterance", "limits"))
    )

    return VoiceProfile(persona=persona, candidates=candidates, fallback=fallback, privacy=privacy, limits=limits)


def load_voice_profile(path: Path) -> VoiceProfile:
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict):
        raise VoiceProfileValidationError(f"{path}: voice profile must be a YAML mapping")
    return parse_voice_profile(raw)
