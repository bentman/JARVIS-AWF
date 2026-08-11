import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from awf.registry.hardware_voice_manifest import (
    FUNCTIONS,
    HardwareVoiceManifestError,
    load_hardware_voice_manifest,
    parse_hardware_voice_manifest,
    resolve_hardware_voice_manifest_path,
)
from awf.speech import models
from awf.speech.models import artifact_paths, stt_runtime, verify_models

FILE_FUNCTIONS = ("tts", "vad", "wake")


def test_parse_url_file():
    manifest = parse_hardware_voice_manifest(
        {"function": "wake", "files": [{"name": "model.onnx", "url": "https://example.com/model.onnx"}]}
    )
    assert manifest.function == "wake"
    assert manifest.files[0].name == "model.onnx"
    assert manifest.files[0].url == "https://example.com/model.onnx"
    assert manifest.files[0].package is None


def test_parse_package_file():
    manifest = parse_hardware_voice_manifest(
        {"function": "vad", "files": [{"name": "silero_vad.onnx", "package": "silero-vad"}]}
    )
    assert manifest.files[0].package == "silero-vad"
    assert manifest.files[0].url is None


def test_parse_rejects_file_with_neither_url_nor_package():
    with pytest.raises(HardwareVoiceManifestError):
        parse_hardware_voice_manifest({"function": "wake", "files": [{"name": "model.onnx"}]})


def test_parse_rejects_file_with_both_url_and_package():
    with pytest.raises(HardwareVoiceManifestError):
        parse_hardware_voice_manifest(
            {
                "function": "wake",
                "files": [{"name": "model.onnx", "url": "https://example.com/x", "package": "x"}],
            }
        )


def test_parse_rejects_unknown_function():
    with pytest.raises(HardwareVoiceManifestError):
        parse_hardware_voice_manifest({"function": "smell"})


def test_parse_stt_classes():
    manifest = parse_hardware_voice_manifest(
        {
            "function": "stt",
            "classes": {
                "cpu": {"model": "small", "device": "cpu", "compute_type": "int8"},
                "cuda": {"model": "big/model", "device": "cuda", "compute_type": "float16"},
            },
        }
    )
    assert manifest.classes["cpu"].model == "small"
    assert manifest.classes["cuda"].device == "cuda"


def test_four_real_shipped_manifests_parse_cleanly(repo_root):
    for function in FUNCTIONS:
        path = resolve_hardware_voice_manifest_path(repo_root, function)
        manifest = load_hardware_voice_manifest(path)
        assert manifest.function == function


def test_every_file_function_resolves_to_a_nonempty_artifact_set(repo_root):
    # tts/vad/wake artifacts don't vary by profile - one non-empty set per
    # function covers every canonical profile ID.
    for function in FILE_FUNCTIONS:
        assert artifact_paths(repo_root, function)


def test_cpu_device_resolves_to_the_cpu_entry(repo_root):
    runtime = stt_runtime(repo_root, "cpu")
    assert runtime.runtime == "onnx_whisper"
    assert runtime.model == "onnx-community/whisper-small"
    assert runtime.device == "cpu"
    assert runtime.compute_type == "int8"


def test_gpu_device_resolves_to_the_cpu_entry(repo_root):
    cpu_runtime = stt_runtime(repo_root, "cpu")
    gpu_runtime = stt_runtime(repo_root, "gpu")
    assert gpu_runtime == cpu_runtime


def test_qnn_device_resolves_to_the_qnn_entry(repo_root):
    runtime = stt_runtime(repo_root, "qnn")
    assert runtime.runtime == "qnn_whisper"
    assert runtime.model == "whisper-qualcomm-qnn"
    assert runtime.device == "qnn"


def test_cuda_device_resolves_to_the_cuda_entry(repo_root):
    runtime = stt_runtime(repo_root, "cuda")
    assert runtime.runtime == "faster_whisper"
    assert runtime.model == "deepdml/faster-whisper-large-v3-turbo-ct2"
    assert runtime.device == "cuda"
    assert runtime.compute_type == "float16"


def test_reconcile_stt_directory_removes_an_obsolete_small_cache(tmp_path):
    target_dir = tmp_path / "stt"
    target_dir.mkdir()
    (target_dir / ".gitkeep").write_text("")
    (target_dir / "CACHEDIR.TAG").write_text("cache")
    active = target_dir / "models--deepdml--faster-whisper-large-v3-turbo-ct2"
    obsolete = target_dir / "models--Systran--faster-whisper-small"
    active.mkdir()
    obsolete.mkdir()
    locks_dir = target_dir / ".locks"
    (locks_dir / active.name).mkdir(parents=True)
    stale_lock = locks_dir / obsolete.name
    stale_lock.mkdir()

    removed = models._reconcile_stt_directory(target_dir, "deepdml/faster-whisper-large-v3-turbo-ct2")

    assert active.is_dir()
    assert (locks_dir / active.name).is_dir()
    assert not obsolete.exists()
    assert not stale_lock.exists()
    assert {result["status"] for result in removed} == {"REMOVED"}


def test_sync_reconciles_config_obsolete_file_artifacts_and_reports_removals(tmp_path, repo_root, monkeypatch):
    shutil.copytree(repo_root / "config", tmp_path / "config")
    stale_tts = tmp_path / "models" / "tts" / "old-model.onnx"
    stale_tts.parent.mkdir(parents=True)
    stale_tts.write_bytes(b"old")
    stale_stt = tmp_path / "models" / "stt" / "models--Systran--faster-whisper-small"
    stale_stt.mkdir(parents=True)

    def acquire(file, target):
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(file.name.encode())

    class FakeWhisperModel:
        def __init__(self, model, *, download_root):
            (Path(download_root) / models._stt_cache_name(model)).mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(models, "_acquire_file", acquire)
    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=FakeWhisperModel))

    results = models.sync_models(tmp_path, "cuda")

    assert not stale_tts.exists()
    assert not stale_stt.exists()
    assert {result["path"] for result in results if result["status"] == "REMOVED"} == {str(stale_tts), str(stale_stt)}


def test_sync_leaves_existing_models_untouched_when_acquisition_fails(tmp_path, repo_root, monkeypatch):
    shutil.copytree(repo_root / "config", tmp_path / "config")
    stale_tts = tmp_path / "models" / "tts" / "old-model.onnx"
    stale_tts.parent.mkdir(parents=True)
    stale_tts.write_bytes(b"old")

    monkeypatch.setattr(
        models, "_acquire_file", lambda file, target: (_ for _ in ()).throw(RuntimeError("download failed"))
    )

    with pytest.raises(RuntimeError, match="download failed"):
        models.sync_models(tmp_path, "cuda")

    assert stale_tts.is_file()


@pytest.mark.live
def test_verify_models_against_the_real_shipped_manifests(repo_root, models_present):
    if not models_present(
        "wake/hey_jarvis_v0.1.onnx",
        "wake/melspectrogram.onnx",
        "wake/embedding_model.onnx",
        "vad/silero_vad.onnx",
        "tts/kokoro-v1.0.onnx",
        "tts/voices-v1.0.bin",
    ):
        pytest.skip("voice models not present under models/ on this host")

    results = verify_models(repo_root)

    assert results
    assert all(result["status"] == "OK" for result in results)
