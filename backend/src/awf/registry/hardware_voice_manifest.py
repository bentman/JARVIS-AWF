"""Voice artifact manifest schema (Section 16.4, ADR-0007).

`config/voice/{stt,tts,vad,wake}.yaml` - one manifest per function, naming
the artifacts that function needs. `tts`, `vad`, and `wake` declare `files`,
each a `name` under `models/<function>/` sourced from a `url` or an
installed `package`. `stt` declares `classes` instead: one entry per
acceleration class (the final segment of a canonical Hardware Profiler
profile ID - `cpu`, `gpu`, `cuda`, `qnn`) naming the `model`/`device`/
`compute_type` `WhisperModel` runs with on that class. A class with no entry
resolves to the `cpu` entry, which is `awf.speech.models.stt_runtime`'s job,
not this module's.
"""

from dataclasses import dataclass, field
from pathlib import Path

import yaml

FUNCTIONS = ("stt", "tts", "vad", "wake")


class HardwareVoiceManifestError(ValueError):
    pass


@dataclass(frozen=True)
class ArtifactFile:
    name: str
    url: str | None = None
    package: str | None = None
    notes: str | None = None


@dataclass(frozen=True)
class SttClass:
    model: str
    device: str
    compute_type: str


@dataclass(frozen=True)
class HardwareVoiceManifest:
    function: str
    files: tuple[ArtifactFile, ...] = field(default_factory=tuple)
    classes: dict[str, SttClass] = field(default_factory=dict)
    notes: str | None = None


def _require(mapping: dict, key: str, context: str) -> object:
    if key not in mapping:
        raise HardwareVoiceManifestError(f"{context}: missing required field '{key}'")
    return mapping[key]


def _parse_file(raw: dict) -> ArtifactFile:
    name = _require(raw, "name", "artifact file")
    url = raw.get("url")
    package = raw.get("package")
    if (url is None) == (package is None):
        raise HardwareVoiceManifestError(f"artifact file '{name}': exactly one of 'url' or 'package' is required")
    return ArtifactFile(name=name, url=url, package=package, notes=raw.get("notes"))


def _parse_class(class_name: str, raw: dict) -> SttClass:
    return SttClass(
        model=_require(raw, "model", f"stt class '{class_name}'"),
        device=_require(raw, "device", f"stt class '{class_name}'"),
        compute_type=_require(raw, "compute_type", f"stt class '{class_name}'"),
    )


def parse_hardware_voice_manifest(raw: dict) -> HardwareVoiceManifest:
    function = _require(raw, "function", "hardware voice manifest")
    if function not in FUNCTIONS:
        raise HardwareVoiceManifestError(f"function '{function}' not in {FUNCTIONS}")

    files = tuple(_parse_file(file_raw) for file_raw in raw.get("files", []))
    classes = {name: _parse_class(name, class_raw) for name, class_raw in raw.get("classes", {}).items()}

    return HardwareVoiceManifest(function=function, files=files, classes=classes, notes=raw.get("notes"))


def load_hardware_voice_manifest(path: Path) -> HardwareVoiceManifest:
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict):
        raise HardwareVoiceManifestError(f"{path}: hardware voice manifest must be a YAML mapping")
    return parse_hardware_voice_manifest(raw)


def resolve_hardware_voice_manifest_path(repo_root: Path, function: str) -> Path:
    return repo_root / "config" / "voice" / f"{function}.yaml"
