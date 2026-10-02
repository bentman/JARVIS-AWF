import pytest

from awf.hardware.profiler import (
    CANONICAL_PROFILES,
    _detect_arch,
    _detect_os,
    resolve_hardware_profile_id,
)

pytestmark = pytest.mark.live


def test_resolve_hardware_profile_id_returns_a_canonical_profile(repo_root):
    profile_id, payload = resolve_hardware_profile_id(repo_root)
    assert profile_id in CANONICAL_PROFILES
    assert isinstance(payload, dict)


def test_resolved_profile_matches_detected_os_and_arch(repo_root):
    profile_id, _payload = resolve_hardware_profile_id(repo_root)
    os_name = _detect_os()
    arch = _detect_arch()
    assert profile_id.startswith(f"{os_name}-{arch}-")


def test_resolve_hardware_profile_id_payload_carries_the_required_keys(repo_root):
    _profile_id, payload = resolve_hardware_profile_id(repo_root)
    assert set(payload.keys()) == {"inventory", "tokens", "readiness"}
    assert isinstance(payload["tokens"], list)
    assert set(payload["readiness"].keys()) == {"stt", "tts", "vad", "wake", "llm"}
