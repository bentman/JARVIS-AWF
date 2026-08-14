"""Voice artifact manifest registry objects (Section 16.4, ADR-0007).

`config/app_registry/hardware-voice-manifests/{stt,tts,vad,wake}/1.0.0.yaml`
is the source of truth for speech model artifacts. The registry envelope owns
identity; `spec` owns the hardware manifest for that function.
"""

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from awf.paths import config_registry_dir, models_dir
from awf.registry.schema import validate_json_schema, validate_registry_identity
from awf.registry.schemas.hardware_voice_manifests import FUNCTIONS, SCHEMA, VERSION


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
    runtime: str
    model: str
    local_path: str | None
    device: str
    compute_type: str


@dataclass(frozen=True)
class HardwareVoiceManifest:
    name: str
    version: str
    function: str
    files: tuple[ArtifactFile, ...] = field(default_factory=tuple)
    classes: dict[str, SttClass] = field(default_factory=dict)
    notes: str | None = None


def _parse_file(raw: dict) -> ArtifactFile:
    name = raw["name"]
    url = raw.get("url")
    package = raw.get("package")
    if (url is None) == (package is None):
        raise HardwareVoiceManifestError(f"artifact file '{name}': exactly one of 'url' or 'package' is required")
    return ArtifactFile(name=name, url=url, package=package, notes=raw.get("notes"))


def _parse_class(class_name: str, raw: dict) -> SttClass:
    return SttClass(
        runtime=str(raw.get("runtime", "faster_whisper")),
        model=raw["model"],
        local_path=str(raw["local_path"]) if raw.get("local_path") is not None else None,
        device=raw["device"],
        compute_type=raw["compute_type"],
    )


def parse_hardware_voice_manifest(raw: dict) -> HardwareVoiceManifest:
    validate_json_schema(raw, SCHEMA, "hardware voice manifest", error=HardwareVoiceManifestError)
    metadata = raw["metadata"]
    spec = raw["spec"]
    function = spec["function"]
    if metadata["name"] != function:
        raise HardwareVoiceManifestError(
            f"hardware voice manifest name '{metadata['name']}' does not match function '{function}'"
        )

    files = tuple(_parse_file(file_raw) for file_raw in spec.get("files", []))
    classes = {name: _parse_class(name, class_raw) for name, class_raw in spec.get("classes", {}).items()}

    return HardwareVoiceManifest(
        name=metadata["name"],
        version=metadata["version"],
        function=function,
        files=files,
        classes=classes,
        notes=spec.get("notes"),
    )


def load_hardware_voice_manifest(path: Path) -> HardwareVoiceManifest:
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict):
        raise HardwareVoiceManifestError(f"{path}: hardware voice manifest must be a YAML mapping")
    manifest = parse_hardware_voice_manifest(raw)
    validate_registry_identity(
        name=manifest.name,
        version=manifest.version,
        path=path,
        context="hardware voice manifest",
        error=HardwareVoiceManifestError,
    )
    return manifest


def resolve_hardware_voice_manifest_path(repo_root: Path, function: str) -> Path:
    return config_registry_dir(repo_root) / "hardware-voice-manifests" / function / f"{VERSION}.yaml"


def artifact_paths(repo_root: Path, function: str) -> dict[str, Path]:
    manifest = load_hardware_voice_manifest(resolve_hardware_voice_manifest_path(repo_root, function))
    target_dir = models_dir(repo_root, function)
    return {file.name: target_dir / file.name for file in manifest.files}


__all__ = (
    "FUNCTIONS",
    "ArtifactFile",
    "HardwareVoiceManifest",
    "HardwareVoiceManifestError",
    "SttClass",
    "artifact_paths",
    "load_hardware_voice_manifest",
    "parse_hardware_voice_manifest",
    "resolve_hardware_voice_manifest_path",
)
