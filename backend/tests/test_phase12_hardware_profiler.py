import json

from awf.db.bootstrap import init_db
from awf.db.connection import get_connection
from awf.hardware.profiler import (
    CANONICAL_PROFILES,
    SYSTEM_RUN_ID,
    _detect_arch,
    _detect_os,
    resolve_hardware_profile_id,
    run_hardware_profiler,
)


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
