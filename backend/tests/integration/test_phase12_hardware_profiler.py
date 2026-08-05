import json

import pytest

from awf.db.bootstrap import init_db
from awf.db.connection import get_connection
from awf.hardware.profiler import (
    CANONICAL_PROFILES,
    SYSTEM_RUN_ID,
    _detect_arch,
    _detect_os,
    _inventory_id,
    _normalize_arch,
    collect_inventory,
    reset_inventory_cache,
    resolve_hardware_profile_id,
    run_hardware_profiler,
)


@pytest.fixture(autouse=True)
def _clean_inventory_cache():
    # The inventory is cached for the process lifetime (Part A, ADR-0006) -
    # reset around every test in this module so one test's detector patches
    # never leak into the next.
    reset_inventory_cache()
    yield
    reset_inventory_cache()


@pytest.mark.live
def test_resolve_hardware_profile_id_returns_a_canonical_profile():
    profile_id, evidence = resolve_hardware_profile_id()
    assert profile_id in CANONICAL_PROFILES
    assert isinstance(evidence, dict)


def test_resolved_profile_matches_detected_os_and_arch():
    profile_id, _evidence = resolve_hardware_profile_id()
    os_name = _detect_os()
    arch = _detect_arch()
    assert profile_id.startswith(f"{os_name}-{arch}-")


def test_profile_falls_back_to_cpu_floor_when_no_provider_verified(monkeypatch):
    import awf.hardware.profiler as profiler

    monkeypatch.setattr(profiler, "_probe_evidence", lambda arch: {"cuda_verified": False, "gpu_verified": False})
    profile_id, _evidence = resolve_hardware_profile_id()
    assert profile_id.endswith("-cpu")


def test_profile_escalates_to_cuda_when_verified(monkeypatch):
    import awf.hardware.profiler as profiler

    monkeypatch.setattr(profiler, "_detect_arch", lambda: "x64")
    monkeypatch.setattr(profiler, "_probe_evidence", lambda arch: {"cuda_verified": True, "gpu_verified": False})
    profile_id, _evidence = resolve_hardware_profile_id()
    assert profile_id.endswith("-cuda")


def test_run_hardware_profiler_writes_event_and_creates_system_run(tmp_path):
    db_path = tmp_path / "awf.db"
    init_db(db_path)
    conn = get_connection(db_path)

    profile_id = run_hardware_profiler(conn)

    run_row = conn.execute("SELECT * FROM runs WHERE run_id = ?", (SYSTEM_RUN_ID,)).fetchone()
    assert run_row is not None

    event_row = conn.execute(
        "SELECT * FROM events WHERE run_id = ? AND reason_code = 'hardware_profile_resolved'", (SYSTEM_RUN_ID,)
    ).fetchone()
    assert event_row is not None
    payload = json.loads(event_row["payload_json"])
    assert payload["profile_id"] == profile_id


def test_run_hardware_profiler_reuses_existing_system_run(tmp_path):
    db_path = tmp_path / "awf.db"
    init_db(db_path)
    conn = get_connection(db_path)

    run_hardware_profiler(conn)
    run_hardware_profiler(conn)

    rows = conn.execute("SELECT COUNT(*) AS n FROM runs WHERE run_id = ?", (SYSTEM_RUN_ID,)).fetchone()
    assert rows["n"] == 1
    events = conn.execute(
        "SELECT COUNT(*) AS n FROM events WHERE run_id = ? AND reason_code = 'hardware_profile_resolved'",
        (SYSTEM_RUN_ID,),
    ).fetchone()
    assert events["n"] == 2


@pytest.mark.parametrize(
    "spelling,expected",
    [
        ("amd64", "x64"),
        ("x86_64", "x64"),
        ("x64", "x64"),
        ("AMD64", "x64"),
        ("arm64", "arm64"),
        ("aarch64", "arm64"),
        ("ARM64", "arm64"),
        ("", "unknown"),
        (None, "unknown"),
        ("mips", "unknown"),
    ],
)
def test_normalize_arch_maps_accepted_spellings(spelling, expected):
    assert _normalize_arch(spelling) == expected


def test_inventory_id_is_stable_for_identical_fields():
    fields = {"os_name": "linux", "arch": "x64", "cpu_name": "demo"}
    assert _inventory_id(fields) == _inventory_id(dict(fields))


def test_inventory_id_changes_when_a_field_changes():
    base = {"os_name": "linux", "arch": "x64", "cpu_name": "demo"}
    changed = {**base, "cpu_name": "other"}
    assert _inventory_id(base) != _inventory_id(changed)


def test_inventory_id_ignores_volatile_fields():
    base = {"os_name": "linux", "arch": "x64"}
    with_volatile = {**base, "inventory_id": "inv-aaa", "profiled_at": "t1", "detector_errors": {"cpu": "boom"}}
    other_volatile = {**base, "inventory_id": "inv-bbb", "profiled_at": "t2", "detector_errors": {}}
    assert _inventory_id(with_volatile) == _inventory_id(other_volatile)


def test_collect_inventory_caches_for_process_lifetime(monkeypatch):
    import awf.hardware.profiler as profiler

    calls = {"n": 0}

    def fake_detect_os_info():
        calls["n"] += 1
        return {"os_name": "linux", "os_version": "1", "device_class": "desktop"}

    monkeypatch.setattr(profiler, "detect_os_info", fake_detect_os_info)

    first = collect_inventory()
    second = collect_inventory()

    assert first is second
    assert calls["n"] == 1


def test_collect_inventory_refresh_true_bypasses_the_cache(monkeypatch):
    import awf.hardware.profiler as profiler

    calls = {"n": 0}

    def fake_detect_os_info():
        calls["n"] += 1
        return {"os_name": "linux", "os_version": "1", "device_class": "desktop"}

    monkeypatch.setattr(profiler, "detect_os_info", fake_detect_os_info)

    collect_inventory()
    collect_inventory(refresh=True)

    assert calls["n"] == 2


def test_a_raising_detector_lands_in_detector_errors_without_failing_the_profiler(monkeypatch):
    import awf.hardware.profiler as profiler

    def raising_detect_gpu_info():
        raise RuntimeError("boom")

    monkeypatch.setattr(profiler, "detect_gpu_info", raising_detect_gpu_info)

    inventory = collect_inventory()

    assert "gpu" in inventory.detector_errors
    assert "boom" in inventory.detector_errors["gpu"]
    assert inventory.gpu_available is False


@pytest.mark.live
def test_probe_evidence_carries_the_required_keys():
    import awf.hardware.profiler as profiler

    evidence = profiler._probe_evidence(_detect_arch())

    for key in ("available_providers", "cuda_verified", "gpu_verified", "qnn_verified"):
        assert key in evidence
    assert isinstance(evidence["available_providers"], list)


@pytest.mark.parametrize(
    "evidence,expected_suffix",
    [
        ({"cuda_verified": True, "gpu_verified": False}, "cuda"),
        ({"cuda_verified": False, "gpu_verified": True}, "gpu"),
        ({"cuda_verified": False, "gpu_verified": False}, "cpu"),
    ],
)
def test_resolution_ladder_on_x64(monkeypatch, evidence, expected_suffix):
    import awf.hardware.profiler as profiler

    monkeypatch.setattr(profiler, "_detect_arch", lambda: "x64")
    monkeypatch.setattr(profiler, "_probe_evidence", lambda arch: evidence)

    profile_id, _evidence = resolve_hardware_profile_id()

    assert profile_id.endswith(f"-{expected_suffix}")


@pytest.mark.parametrize(
    "evidence,expected_suffix",
    [
        ({"qnn_verified": True, "gpu_verified": False}, "qnn"),
        ({"qnn_verified": False, "gpu_verified": True}, "gpu"),
        ({"qnn_verified": False, "gpu_verified": False}, "cpu"),
    ],
)
def test_resolution_ladder_on_arm64(monkeypatch, evidence, expected_suffix):
    import awf.hardware.profiler as profiler

    monkeypatch.setattr(profiler, "_detect_arch", lambda: "arm64")
    monkeypatch.setattr(profiler, "_probe_evidence", lambda arch: evidence)

    profile_id, _evidence = resolve_hardware_profile_id()

    assert profile_id.endswith(f"-{expected_suffix}")
