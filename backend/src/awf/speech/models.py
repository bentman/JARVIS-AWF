"""Voice artifact resolution and acquisition (ADR-0007, ADR-0008).

Maps a device (an `awf.hardware.readiness` result, not a profile ID) to STT
runtime parameters, and acquires whatever `models/<function>/` artifacts are
missing. `speech/cli.py` and `speech/pipeline.py` read from this module
rather than holding model paths as literals.
"""

import importlib.resources
import shutil
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from awf.paths import models_dir
from awf.registry.hardware_voice_manifest import (
    FUNCTIONS,
    HardwareVoiceManifest,
    HardwareVoiceManifestError,
    artifact_paths,
    load_hardware_voice_manifest,
    resolve_hardware_voice_manifest_path,
)

# Files-bearing functions (tts/vad/wake); stt names its artifacts through
# `classes`, not `files`, and is acquired through `WhisperModel`'s own cache
# instead of a named download.
_FILE_FUNCTIONS = tuple(function for function in FUNCTIONS if function != "stt")
_KEEP_FILE_NAMES = {".gitkeep"}
_KEEP_STT_NAMES = _KEEP_FILE_NAMES | {".locks", "CACHEDIR.TAG"}


@dataclass(frozen=True)
class SttRuntime:
    runtime: str
    model: str
    local_path: str
    device: str
    compute_type: str


def load_voice_manifest(repo_root: Path, function: str) -> HardwareVoiceManifest:
    return load_hardware_voice_manifest(resolve_hardware_voice_manifest_path(repo_root, function))


def stt_runtime(repo_root: Path, device: str) -> SttRuntime:
    manifest = load_voice_manifest(repo_root, "stt")
    stt_class = manifest.classes.get(device, manifest.classes["cpu"])
    return SttRuntime(
        runtime=stt_class.runtime,
        model=stt_class.model,
        local_path=stt_class.local_path or stt_class.model.replace("/", "--"),
        device=stt_class.device,
        compute_type=stt_class.compute_type,
    )


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


def _remove_path(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()


def _removed_result(function: str, path: Path) -> dict:
    return {"function": function, "name": path.name, "path": str(path), "status": "REMOVED"}


def _reconcile_file_directory(function: str, target_dir: Path, expected_names: set[str]) -> list[dict]:
    """Remove config-obsolete TTS, VAD, or wake artifacts after sync succeeds."""
    removed = []
    for path in target_dir.iterdir():
        if path.name in _KEEP_FILE_NAMES or path.name in expected_names:
            continue
        _remove_path(path)
        removed.append(_removed_result(function, path))
    return removed


def _stt_cache_name(model: str) -> str:
    try:
        from faster_whisper.utils import _MODELS
    except ImportError:
        _MODELS = {}

    repository_id = _MODELS.get(model, model if "/" in model else f"Systran/faster-whisper-{model}")
    return f"models--{repository_id.replace('/', '--')}"


def _onnx_whisper_required_files() -> tuple[str, ...]:
    return (
        "config.json",
        "generation_config.json",
        "preprocessor_config.json",
        "tokenizer.json",
        "tokenizer_config.json",
        "special_tokens_map.json",
        "vocab.json",
        "merges.txt",
        "normalizer.json",
        "added_tokens.json",
    )


def _qnn_whisper_required_files() -> tuple[str, ...]:
    return (
        "encoder/model.onnx",
        "encoder/model.bin",
        "decoder/model.onnx",
        "decoder/model.bin",
    )


def stt_model_path(repo_root: Path, runtime: SttRuntime) -> Path:
    return models_dir(repo_root, "stt") / runtime.local_path


def qnn_whisper_available(repo_root: Path, runtime: SttRuntime | None = None) -> bool:
    runtime = runtime or stt_runtime(repo_root, "qnn")
    target = stt_model_path(repo_root, runtime)
    return all((target / relative).is_file() for relative in _qnn_whisper_required_files())


def _onnx_whisper_available(target: Path) -> bool:
    return (
        all((target / filename).is_file() for filename in _onnx_whisper_required_files())
        and any(target.glob("**/encoder_model.onnx"))
        and any(target.glob("**/decoder_model_merged.onnx"))
    )


def _reconcile_stt_directory(target_dir: Path, model: str) -> list[dict]:
    """Keep only the selected faster-whisper cache and its matching lock."""
    expected_cache_name = _stt_cache_name(model)
    removed = []
    for path in target_dir.iterdir():
        if path.name in _KEEP_STT_NAMES or path.name == expected_cache_name:
            continue
        _remove_path(path)
        removed.append(_removed_result("stt", path))

    locks_dir = target_dir / ".locks"
    if locks_dir.is_dir():
        for path in locks_dir.iterdir():
            if path.name == ".gitkeep" or path.name == expected_cache_name:
                continue
            _remove_path(path)
            removed.append(_removed_result("stt", path))
    return removed


def _reconcile_file_models(repo_root: Path) -> list[dict]:
    """Reconcile config-owned file artifact directories only after acquisition completes."""
    removed = []
    for function in _FILE_FUNCTIONS:
        manifest = load_voice_manifest(repo_root, function)
        removed.extend(
            _reconcile_file_directory(function, models_dir(repo_root, function), {file.name for file in manifest.files})
        )
    return removed


def _reconcile_models(repo_root: Path, stt_model: str) -> list[dict]:
    """Reconcile config-owned model directories only after acquisition completes."""
    removed = _reconcile_file_models(repo_root)
    removed.extend(_reconcile_stt_directory(models_dir(repo_root, "stt"), stt_model))
    return removed


def _sync_onnx_whisper(repo_root: Path, runtime: SttRuntime) -> dict:
    import onnx_asr
    from huggingface_hub import snapshot_download

    target = stt_model_path(repo_root, runtime)
    target.mkdir(parents=True, exist_ok=True)
    if not _onnx_whisper_available(target):
        snapshot_download(
            runtime.model,
            local_dir=target,
            allow_patterns=[
                "config.json",
                "generation_config.json",
                "preprocessor_config.json",
                "tokenizer.json",
                "tokenizer_config.json",
                "special_tokens_map.json",
                "vocab.json",
                "merges.txt",
                "normalizer.json",
                "added_tokens.json",
                "onnx/encoder_model.onnx",
                "onnx/decoder_model_merged.onnx",
            ],
        )
    onnx_asr.load_model(runtime.model, path=target, providers=["CPUExecutionProvider"])
    status = "PRESENT" if _onnx_whisper_available(target) else "SYNCED"
    return {"function": "stt", "name": runtime.model, "path": str(target), "runtime": runtime.runtime, "status": status}


def sync_models(repo_root: Path, stt_device: str) -> list[dict]:
    results = []
    for function in _FILE_FUNCTIONS:
        manifest = load_voice_manifest(repo_root, function)
        target_dir = models_dir(repo_root, function)
        for file in manifest.files:
            target = target_dir / file.name
            if target.is_file():
                results.append({"function": function, "name": file.name, "path": str(target), "status": "PRESENT"})
                continue
            _acquire_file(file, target)
            results.append({"function": function, "name": file.name, "path": str(target), "status": "SYNCED"})

    runtime = stt_runtime(repo_root, stt_device)
    download_root = models_dir(repo_root, "stt")
    download_root.mkdir(parents=True, exist_ok=True)
    if runtime.runtime == "faster_whisper":
        from faster_whisper import WhisperModel

        WhisperModel(runtime.model, download_root=str(download_root))
        results.append({"function": "stt", "name": runtime.model, "path": str(download_root), "status": "SYNCED"})
        results.extend(_reconcile_models(repo_root, runtime.model))
    elif runtime.runtime == "onnx_whisper":
        results.append(_sync_onnx_whisper(repo_root, runtime))
        results.extend(_reconcile_file_models(repo_root))
    elif runtime.runtime == "qnn_whisper" and qnn_whisper_available(repo_root, runtime):
        results.append(
            {
                "function": "stt",
                "name": runtime.model,
                "path": str(stt_model_path(repo_root, runtime)),
                "runtime": runtime.runtime,
                "status": "PRESENT",
            }
        )
    else:
        fallback = stt_runtime(repo_root, "cpu")
        results.append(
            {
                "function": "stt",
                "name": runtime.model,
                "path": str(stt_model_path(repo_root, runtime)),
                "runtime": runtime.runtime,
                "status": "MISSING",
            }
        )
        results.append(
            {
                **_sync_onnx_whisper(repo_root, fallback),
                "fallback_for": runtime.runtime,
            }
        )
        results.extend(_reconcile_file_models(repo_root))

    return results


def verify_models(repo_root: Path) -> list[dict]:
    # every canonical profile shares the same tts/vad/wake artifacts, and stt
    # has no named files to check presence of - it's warmed by `sync_models`,
    # not presence-checked here.
    results = []
    for function in _FILE_FUNCTIONS:
        paths = artifact_paths(repo_root, function)
        for name, path in paths.items():
            status = "OK" if path.is_file() else "MISSING"
            results.append({"function": function, "name": name, "path": str(path), "status": status})
    return results
