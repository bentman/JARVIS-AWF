"""Voice artifact resolution, acquisition, and verification (ADR-0007).

Maps a canonical Hardware Profiler profile ID to artifact paths under
`models/<function>/` and to STT runtime parameters, acquires whatever is
missing, and verifies what is present. `speech/cli.py` and `speech/pipeline.py`
read from this module rather than holding model paths as literals.
"""

import importlib.resources
import shutil
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from awf.registry.hardware_voice_manifest import (
    FUNCTIONS,
    HardwareVoiceManifest,
    HardwareVoiceManifestError,
    load_hardware_voice_manifest,
    resolve_hardware_voice_manifest_path,
)

ACCELERATION_CLASSES = ("cpu", "gpu", "cuda", "qnn")

# Files-bearing functions (tts/vad/wake); stt names its artifacts through
# `classes`, not `files`, and is acquired through `WhisperModel`'s own cache
# instead of a named download.
_FILE_FUNCTIONS = tuple(function for function in FUNCTIONS if function != "stt")


@dataclass(frozen=True)
class SttRuntime:
    model: str
    device: str
    compute_type: str


def acceleration_class(profile_id: str) -> str:
    candidate = profile_id.rsplit("-", 1)[-1]
    if candidate not in ACCELERATION_CLASSES:
        raise HardwareVoiceManifestError(
            f"profile id '{profile_id}' has no recognized acceleration class in {ACCELERATION_CLASSES}"
        )
    return candidate


def load_voice_manifest(repo_root: Path, function: str) -> HardwareVoiceManifest:
    return load_hardware_voice_manifest(resolve_hardware_voice_manifest_path(repo_root, function))


def artifact_paths(repo_root: Path, function: str) -> dict[str, Path]:
    manifest = load_voice_manifest(repo_root, function)
    models_dir = repo_root / "models" / function
    return {file.name: models_dir / file.name for file in manifest.files}


def stt_runtime(repo_root: Path, profile_id: str) -> SttRuntime:
    manifest = load_voice_manifest(repo_root, "stt")
    stt_class = manifest.classes.get(acceleration_class(profile_id), manifest.classes["cpu"])
    return SttRuntime(model=stt_class.model, device=stt_class.device, compute_type=stt_class.compute_type)


def _import_name_for_package(package: str) -> str:
    # PyPI distribution names and their importable top-level module names
    # commonly differ only by hyphen-vs-underscore (true for silero-vad ->
    # silero_vad, the only package-sourced artifact today).
    return package.replace("-", "_")


def _find_package_resource(import_name: str, filename: str):
    stack = [importlib.resources.files(import_name)]
    while stack:
        current = stack.pop()
        if current.is_dir():
            stack.extend(current.iterdir())
        elif current.is_file() and current.name == filename:
            return current
    raise HardwareVoiceManifestError(f"package '{import_name}' has no bundled resource named '{filename}'")


def _acquire_file(file, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if file.url is not None:
        tmp_path = target.with_suffix(target.suffix + ".part")
        with urllib.request.urlopen(file.url) as response, tmp_path.open("wb") as out:
            shutil.copyfileobj(response, out)
        tmp_path.replace(target)
    else:
        resource = _find_package_resource(_import_name_for_package(file.package), file.name)
        with resource.open("rb") as source, target.open("wb") as out:
            shutil.copyfileobj(source, out)


def sync_models(repo_root: Path, profile_id: str) -> list[dict]:
    results = []
    for function in _FILE_FUNCTIONS:
        manifest = load_voice_manifest(repo_root, function)
        models_dir = repo_root / "models" / function
        for file in manifest.files:
            target = models_dir / file.name
            if target.is_file():
                results.append({"function": function, "name": file.name, "path": str(target), "status": "PRESENT"})
                continue
            _acquire_file(file, target)
            results.append({"function": function, "name": file.name, "path": str(target), "status": "SYNCED"})

    from faster_whisper import WhisperModel

    runtime = stt_runtime(repo_root, profile_id)
    download_root = repo_root / "models" / "stt"
    download_root.mkdir(parents=True, exist_ok=True)
    WhisperModel(runtime.model, download_root=str(download_root))
    results.append({"function": "stt", "name": runtime.model, "path": str(download_root), "status": "SYNCED"})

    return results


def verify_models(repo_root: Path, _profile_id: str) -> list[dict]:
    # every canonical profile shares the same tts/vad/wake artifacts, and stt
    # has no named files - the parameter exists for signature symmetry with
    # `sync_models`/`stt_runtime`, which do vary by profile.
    results = []
    for function in _FILE_FUNCTIONS:
        paths = artifact_paths(repo_root, function)
        for name, path in paths.items():
            status = "OK" if path.is_file() else "MISSING"
            results.append({"function": function, "name": name, "path": str(path), "status": status})
    return results
