"""Hardware-profile-pinned artifact manifest schema (Section 16.4).

`config/voice/{stt,tts,vad,wake}/<profile-id>.yaml` - one per canonical
Hardware Profiler profile ID (`hardware/profiler.py::CANONICAL_PROFILES`)
per function - pins the exact artifact(s) each function needs on that
profile, and is the authority for bytes. Git-tracked, single-root (unlike
`config/app_registry/`/`data/registry/`, this tree has no operator-owned
counterpart - Section 16.4's own pins are not something an operator adds
to).

Three acquisition shapes exist across the real, verified artifacts this
project actually uses: a plain downloadable `url` with a `sha256` (the
authority for those bytes), a `huggingface` repo pinned to a `revision`
(a multi-file repo has no single meaningful file hash), and a
`pip-package`-sourced file (still hash-pinned - the package name documents
where it came from, the hash is still the real authority). A profile with
no real published upstream artifact (see `stt/*-qnn.yaml`) declares
`fallback_to` another profile instead of a fabricated pin, per Section
16.4's own "every profile falls back to its arch's `*64-cpu` floor" rule.
"""

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

import yaml

ACQUISITION_TYPES = ("url", "huggingface", "pip-package")
FUNCTIONS = ("stt", "tts", "vad", "wake")


class HardwareVoiceManifestError(ValueError):
    pass


@dataclass(frozen=True)
class ArtifactPin:
    acquisition: str
    target_relative_path: str | None = None
    sha256: str | None = None
    url: str | None = None
    repo_id: str | None = None
    revision: str | None = None
    package: str | None = None


@dataclass(frozen=True)
class HardwareVoiceManifest:
    function: str
    profile: str
    files: tuple[ArtifactPin, ...] = field(default_factory=tuple)
    fallback_to: str | None = None
    notes: str = ""


def _require(mapping: dict, key: str, context: str) -> object:
    if key not in mapping:
        raise HardwareVoiceManifestError(f"{context}: missing required field '{key}'")
    return mapping[key]


def parse_hardware_voice_manifest(raw: dict) -> HardwareVoiceManifest:
    function = _require(raw, "function", "hardware voice manifest")
    if function not in FUNCTIONS:
        raise HardwareVoiceManifestError(f"function '{function}' not in {FUNCTIONS}")

    files = []
    for file_raw in raw.get("files", []):
        acquisition = _require(file_raw, "acquisition", "artifact pin")
        if acquisition not in ACQUISITION_TYPES:
            raise HardwareVoiceManifestError(f"acquisition '{acquisition}' not in {ACQUISITION_TYPES}")
        files.append(
            ArtifactPin(
                acquisition=acquisition,
                target_relative_path=file_raw.get("target_relative_path"),
                sha256=file_raw.get("sha256"),
                url=file_raw.get("url"),
                repo_id=file_raw.get("repo_id"),
                revision=file_raw.get("revision"),
                package=file_raw.get("package"),
            )
        )

    return HardwareVoiceManifest(
        function=function,
        profile=_require(raw, "profile", "hardware voice manifest"),
        files=tuple(files),
        fallback_to=raw.get("fallback_to"),
        notes=raw.get("notes", ""),
    )


def load_hardware_voice_manifest(path: Path) -> HardwareVoiceManifest:
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict):
        raise HardwareVoiceManifestError(f"{path}: hardware voice manifest must be a YAML mapping")
    return parse_hardware_voice_manifest(raw)


def resolve_hardware_voice_manifest_path(repo_root: Path, function: str, profile_id: str) -> Path:
    return repo_root / "config" / "voice" / function / f"{profile_id}.yaml"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_profile_models(repo_root: Path, function: str, profile_id: str, models_root: Path) -> dict:
    """Resolves `config/voice/<function>/<profile_id>.yaml` (following one
    `fallback_to` hop if the profile has no real pin of its own, e.g. the
    `*-qnn` STT profiles) and verifies every hash-pinned file against what's
    actually in `models_root`."""
    manifest = load_hardware_voice_manifest(
        resolve_hardware_voice_manifest_path(repo_root, function, profile_id)
    )
    resolved_profile_id = profile_id
    if not manifest.files and manifest.fallback_to:
        resolved_profile_id = manifest.fallback_to
        manifest = load_hardware_voice_manifest(
            resolve_hardware_voice_manifest_path(repo_root, function, resolved_profile_id)
        )
    return {
        "function": function,
        "profile_id": profile_id,
        "resolved_profile_id": resolved_profile_id,
        "results": verify_pinned_files(models_root, manifest),
    }


def verify_pinned_files(models_root: Path, manifest: HardwareVoiceManifest) -> list[dict]:
    """Checks each hash-pinned file in `manifest` against what's actually on
    disk under `models_root` (e.g. `models/stt/`). Returns one result dict
    per pinned file with a real sha256 - `acquisition: huggingface` pins
    with no single-file hash (the `cuda` STT class) and `fallback_to`
    manifests with no files are not directly verifiable this way and are
    skipped, not silently reported as passing."""
    results = []
    for pin in manifest.files:
        if pin.sha256 is None or pin.target_relative_path is None:
            continue
        target = models_root / pin.target_relative_path
        if not target.is_file():
            results.append({"path": str(target), "status": "MISSING"})
            continue
        actual = sha256_file(target)
        results.append(
            {
                "path": str(target),
                "status": "OK" if actual == pin.sha256 else "HASH_MISMATCH",
                "expected_sha256": pin.sha256,
                "actual_sha256": actual,
            }
        )
    return results
