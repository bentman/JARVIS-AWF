import hashlib
from pathlib import Path

import pytest

from awf.registry.hardware_voice_manifest import (
    HardwareVoiceManifestError,
    load_hardware_voice_manifest,
    parse_hardware_voice_manifest,
    resolve_hardware_voice_manifest_path,
    sha256_file,
    verify_pinned_files,
    verify_profile_models,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_parse_url_acquisition():
    manifest = parse_hardware_voice_manifest(
        {
            "function": "wake",
            "profile": "linux-x64-cpu",
            "files": [
                {
                    "acquisition": "url",
                    "url": "https://example.com/model.onnx",
                    "target_relative_path": "model.onnx",
                    "sha256": "abc123",
                }
            ],
        }
    )
    assert manifest.function == "wake"
    assert manifest.files[0].acquisition == "url"
    assert manifest.files[0].sha256 == "abc123"


def test_parse_rejects_unknown_acquisition():
    with pytest.raises(HardwareVoiceManifestError):
        parse_hardware_voice_manifest(
            {"function": "wake", "profile": "linux-x64-cpu", "files": [{"acquisition": "ftp"}]}
        )


def test_parse_rejects_unknown_function():
    with pytest.raises(HardwareVoiceManifestError):
        parse_hardware_voice_manifest({"function": "smell", "profile": "linux-x64-cpu"})


def test_parse_fallback_manifest_has_no_files():
    manifest = parse_hardware_voice_manifest(
        {
            "function": "stt",
            "profile": "linux-arm64-qnn",
            "files": [],
            "fallback_to": "linux-arm64-cpu",
            "notes": "no upstream QNN build exists",
        }
    )
    assert manifest.files == ()
    assert manifest.fallback_to == "linux-arm64-cpu"


def test_all_48_real_shipped_manifests_parse_cleanly():
    # every canonical profile x function combination this project actually
    # ships - a real regression check, not a synthetic sample.
    profiles = [
        "windows-x64-cpu", "windows-x64-gpu", "windows-x64-cuda",
        "windows-arm64-cpu", "windows-arm64-gpu", "windows-arm64-qnn",
        "linux-x64-cpu", "linux-x64-gpu", "linux-x64-cuda",
        "linux-arm64-cpu", "linux-arm64-gpu", "linux-arm64-qnn",
    ]
    for function in ("stt", "tts", "vad", "wake"):
        for profile in profiles:
            path = resolve_hardware_voice_manifest_path(REPO_ROOT, function, profile)
            manifest = load_hardware_voice_manifest(path)
            assert manifest.function == function
            assert manifest.profile == profile
            # every manifest either has real files or a real fallback - never neither
            assert manifest.files or manifest.fallback_to


def test_sha256_file_matches_real_hashlib(tmp_path):
    path = tmp_path / "data.bin"
    path.write_bytes(b"some real bytes to hash")
    assert sha256_file(path) == hashlib.sha256(b"some real bytes to hash").hexdigest()


def test_verify_pinned_files_reports_missing(tmp_path):
    manifest = parse_hardware_voice_manifest(
        {
            "function": "wake", "profile": "linux-x64-cpu",
            "files": [{"acquisition": "url", "target_relative_path": "gone.onnx", "sha256": "deadbeef"}],
        }
    )
    results = verify_pinned_files(tmp_path, manifest)
    assert results == [{"path": str(tmp_path / "gone.onnx"), "status": "MISSING"}]


def test_verify_pinned_files_reports_ok_and_mismatch(tmp_path):
    (tmp_path / "real.bin").write_bytes(b"real content")
    real_hash = hashlib.sha256(b"real content").hexdigest()
    manifest = parse_hardware_voice_manifest(
        {
            "function": "wake", "profile": "linux-x64-cpu",
            "files": [
                {"acquisition": "url", "target_relative_path": "real.bin", "sha256": real_hash},
                {"acquisition": "url", "target_relative_path": "real.bin", "sha256": "wrong-hash"},
            ],
        }
    )
    results = verify_pinned_files(tmp_path, manifest)
    assert results[0]["status"] == "OK"
    assert results[1]["status"] == "HASH_MISMATCH"
    assert results[1]["expected_sha256"] == "wrong-hash"
    assert results[1]["actual_sha256"] == real_hash


def test_verify_pinned_files_skips_files_with_no_hash(tmp_path):
    # the cuda-class STT manifests (HF multi-file repo, no single sha256) -
    # must not be silently reported as passing or failing.
    manifest = parse_hardware_voice_manifest(
        {
            "function": "stt", "profile": "linux-x64-cuda",
            "files": [{"acquisition": "huggingface", "repo_id": "x/y", "revision": "main", "sha256": None}],
        }
    )
    assert verify_pinned_files(tmp_path, manifest) == []


def test_verify_profile_models_against_the_real_shipped_linux_x64_cpu_wake_manifest(tmp_path):
    # the real, currently-resolved profile on this host, against the real
    # already-downloaded model files.
    models_root = REPO_ROOT / "models" / "wake"
    if not models_root.is_dir():
        pytest.skip("models/wake/ not present on this host")

    result = verify_profile_models(REPO_ROOT, "wake", "linux-x64-cpu", models_root)

    assert result["resolved_profile_id"] == "linux-x64-cpu"
    assert result["results"]
    assert all(r["status"] == "OK" for r in result["results"])


def test_verify_profile_models_follows_fallback_to_cpu(tmp_path):
    # linux-arm64-qnn's STT manifest has no real files - it must resolve to
    # linux-arm64-cpu's real pin instead of reporting nothing.
    result = verify_profile_models(REPO_ROOT, "stt", "linux-arm64-qnn", tmp_path)
    assert result["profile_id"] == "linux-arm64-qnn"
    assert result["resolved_profile_id"] == "linux-arm64-cpu"
    assert result["results"][0]["status"] == "MISSING"  # tmp_path has nothing in it
