import json

import pytest

from awf.db.bootstrap import init_db
from awf.db.connection import get_connection
from awf.hardware.preflight import reset_preflight_cache
from awf.hardware.profiler import (
    CANONICAL_PROFILES,
    SYSTEM_RUN_ID,
    _detect_arch,
    _detect_os,
    _inventory_id,
    _normalize_arch,
    _powershell,
    collect_inventory,
    detect_cuda_info,
    detect_gpu_info,
    detect_npu_info,
    reset_inventory_cache,
    resolve_hardware_profile_id,
    run_hardware_profiler,
)
from awf.hardware.readiness import Readiness


@pytest.fixture(autouse=True)
def _clean_hardware_caches():
    # Both the inventory and preflight results are cached for the process
    # lifetime - reset around every test in this module so one test's
    # detector/readiness patches never leak into the next.
    reset_inventory_cache()
    reset_preflight_cache()
    yield
    reset_inventory_cache()
    reset_preflight_cache()


@pytest.mark.live
def test_resolve_hardware_profile_id_returns_a_canonical_profile(repo_root):
    profile_id, payload = resolve_hardware_profile_id(repo_root)
    assert profile_id in CANONICAL_PROFILES
    assert isinstance(payload, dict)


@pytest.mark.live
def test_resolved_profile_matches_detected_os_and_arch(repo_root):
    profile_id, _payload = resolve_hardware_profile_id(repo_root)
    os_name = _detect_os()
    arch = _detect_arch()
    assert profile_id.startswith(f"{os_name}-{arch}-")


@pytest.mark.live
def test_resolve_hardware_profile_id_payload_carries_the_required_keys(repo_root):
    _profile_id, payload = resolve_hardware_profile_id(repo_root)
    assert set(payload.keys()) == {"inventory", "tokens", "readiness"}
    assert isinstance(payload["tokens"], list)
    assert set(payload["readiness"].keys()) == {"stt", "tts", "vad", "wake", "llm"}


@pytest.mark.parametrize(
    "stt_device,tts_device,expected_suffix",
    [
        ("cuda", "cpu", "cuda"),
        ("cpu", "cuda", "cuda"),
        ("cpu", "directml", "gpu"),
        ("cpu", "qnn", "qnn"),
        ("cpu", "cpu", "cpu"),
    ],
)
def test_resolution_ladder_uses_the_strongest_readiness_device(
    monkeypatch, repo_root, stt_device, tts_device, expected_suffix
):
    import awf.hardware.profiler as profiler

    monkeypatch.setattr(profiler, "derive_stt_readiness", lambda inventory, tokens: Readiness(stt_device, True, "test"))
    monkeypatch.setattr(profiler, "derive_tts_readiness", lambda inventory, tokens: Readiness(tts_device, True, "test"))

    profile_id, _payload = resolve_hardware_profile_id(repo_root)

    assert profile_id.endswith(f"-{expected_suffix}")


def test_resolution_ladder_uses_opencl_adreno_token_for_gpu_suffix(monkeypatch, repo_root):
    import awf.hardware.profiler as profiler

    monkeypatch.setattr(profiler, "derive_stt_readiness", lambda inventory, tokens: Readiness("cpu", True, "test"))
    monkeypatch.setattr(profiler, "derive_tts_readiness", lambda inventory, tokens: Readiness("cpu", True, "test"))
    monkeypatch.setattr(profiler, "collect_preflight_tokens", lambda inventory, **kwargs: ["opencl:adreno"])

    profile_id, _payload = resolve_hardware_profile_id(repo_root)

    assert profile_id.endswith("-gpu")


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
    assert set(payload.keys()) == {"profile_id", "inventory", "tokens", "readiness"}
    assert set(payload["readiness"].keys()) == {"stt", "tts", "vad", "wake", "llm"}


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


def test_powershell_is_windows_only(monkeypatch):
    import awf.hardware.profiler as profiler

    calls = []
    monkeypatch.setattr(profiler.platform, "system", lambda: "Linux")
    monkeypatch.setattr(profiler, "_run_command", lambda command, timeout=10: calls.append(command) or "unexpected")

    assert _powershell("Get-Thing") == ""
    assert calls == []


def test_linux_cpuinfo_can_report_qualcomm_npu_without_windows_bridge(monkeypatch):
    import awf.hardware.profiler as profiler

    monkeypatch.setattr(profiler.platform, "system", lambda: "Linux")
    monkeypatch.setattr(profiler.platform, "machine", lambda: "aarch64")
    monkeypatch.setattr(profiler.platform, "processor", lambda: "")
    monkeypatch.setattr(profiler, "_powershell", lambda script: "")
    monkeypatch.setattr(profiler, "_read_linux_cpuinfo", lambda: "Hardware\t: Qualcomm Snapdragon X Elite\n")
    monkeypatch.setattr(profiler, "_linux_qualcomm_accelerator_visible", lambda: False)

    assert detect_npu_info() == {"npu_available": True, "npu_vendor": "qualcomm"}


def test_linux_accelerator_sysfs_can_report_qualcomm_npu(monkeypatch):
    import awf.hardware.profiler as profiler

    monkeypatch.setattr(profiler.platform, "system", lambda: "Linux")
    monkeypatch.setattr(profiler.platform, "machine", lambda: "aarch64")
    monkeypatch.setattr(profiler.platform, "processor", lambda: "")
    monkeypatch.setattr(profiler, "_powershell", lambda script: "")
    monkeypatch.setattr(profiler, "_read_linux_cpuinfo", lambda: "")
    monkeypatch.setattr(profiler, "_linux_qualcomm_accelerator_visible", lambda: True)

    assert detect_npu_info() == {"npu_available": True, "npu_vendor": "qualcomm"}


def test_linux_opencl_can_report_qualcomm_gpu_without_drm_sysfs(monkeypatch):
    import awf.hardware.profiler as profiler

    monkeypatch.setattr(profiler.platform, "system", lambda: "Linux")
    monkeypatch.setattr(profiler, "_gpu_from_cli", lambda command, vendor_hint, source: None)
    monkeypatch.setattr(profiler, "_gpu_from_linux_sysfs", lambda: None)
    monkeypatch.setattr(profiler, "_opencl_qualcomm_name", lambda: "Qualcomm Adreno")

    result = detect_gpu_info()

    assert result["gpu_available"] is True
    assert result["gpu_vendor"] == "qualcomm"
    assert result["gpu_vram_source"] == "opencl-platform"


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


def test_windows_npu_does_not_false_positive_on_input_device(monkeypatch):
    import awf.hardware.profiler as profiler

    monkeypatch.setattr(profiler.platform, "system", lambda: "Windows")
    monkeypatch.setattr(profiler.platform, "processor", lambda: "Intel64 Family 6 Model 151 Stepping 2, GenuineIntel")
    monkeypatch.setattr(profiler, "_powershell", lambda script: "")

    assert detect_npu_info() == {"npu_available": False, "npu_vendor": None}


def test_detect_cuda_info_prefers_nvcc_version(monkeypatch):
    import awf.hardware.profiler as profiler

    def fake_run(command, timeout=10):
        if command[0] == "nvcc":
            return "nvcc: NVIDIA (R) Cuda compiler driver\nCuda compilation tools, release 13.3, V13.3.33\n"
        return ""

    monkeypatch.setattr(profiler, "_run_command", fake_run)
    assert detect_cuda_info() == {"cuda_available": True, "cuda_version": "13.3"}


def test_gpu_from_windows_cim_prefers_recognized_vendor(monkeypatch):
    import awf.hardware.profiler as profiler

    cim_output = json.dumps(
        [
            {"Name": "Microsoft Remote Display Adapter", "AdapterRAM": 0},
            {"Name": "Qualcomm Adreno(TM) GPU", "AdapterRAM": 4294967296},
        ]
    )
    monkeypatch.setattr(profiler.platform, "system", lambda: "Windows")
    monkeypatch.setattr(profiler, "_powershell", lambda script: cim_output)

    result = profiler._gpu_from_windows_cim()
    assert result is not None
    assert result["gpu_name"] == "Qualcomm Adreno(TM) GPU"
    assert result["gpu_vendor"] == "qualcomm"


def test_detect_cuda_info_prefers_usr_local_cuda_over_distro_nvcc(monkeypatch):
    import awf.hardware.profiler as profiler

    monkeypatch.setattr(profiler.platform, "system", lambda: "Linux")
    monkeypatch.setattr(profiler.Path, "exists", lambda self: True)

    def fake_run(command, timeout=10):
        if command[0] == "/usr/local/cuda/bin/nvcc":
            return "nvcc: NVIDIA (R) Cuda compiler driver\nCuda compilation tools, release 12.4, V12.4.131\n"
        if command[0] == "nvcc":
            return "nvcc: NVIDIA (R) Cuda compiler driver\nCuda compilation tools, release 11.5, V11.5.119\n"
        return ""

    monkeypatch.setattr(profiler, "_run_command", fake_run)
    assert detect_cuda_info() == {"cuda_available": True, "cuda_version": "12.4"}


def test_gpu_from_linux_sysfs_drm_detection(tmp_path, monkeypatch):
    import awf.hardware.profiler as profiler

    fake_drm = tmp_path / "drm"
    card0 = fake_drm / "card0" / "device"
    card0.mkdir(parents=True)
    (card0 / "vendor").write_text("0x10de\n", encoding="utf-8")

    orig_path = profiler.Path
    monkeypatch.setattr(
        profiler,
        "Path",
        lambda p, *a, **k: fake_drm if str(p) == "/sys/class/drm" else orig_path(p, *a, **k),
    )

    result = profiler._gpu_from_linux_sysfs()
    assert result is not None
    assert result["gpu_available"] is True
    assert result["gpu_vendor"] == "nvidia"
    assert result["gpu_vram_source"] == "linux-sysfs-drm"


def test_gpu_from_linux_sysfs_pci_detection(tmp_path, monkeypatch):
    import awf.hardware.profiler as profiler

    fake_drm = tmp_path / "empty_drm"
    fake_drm.mkdir(parents=True)
    fake_pci = tmp_path / "pci"
    dev0 = fake_pci / "pci_dev0"
    dev0.mkdir(parents=True)
    (dev0 / "class").write_text("0x030000\n", encoding="utf-8")
    (dev0 / "vendor").write_text("0x1002\n", encoding="utf-8")

    orig_path = profiler.Path

    def fake_path_resolver(p, *a, **k):
        if str(p) == "/sys/class/drm":
            return fake_drm
        if str(p) == "/sys/bus/pci/devices":
            return fake_pci
        return orig_path(p, *a, **k)

    monkeypatch.setattr(profiler, "Path", fake_path_resolver)

    result = profiler._gpu_from_linux_sysfs()
    assert result is not None
    assert result["gpu_available"] is True
    assert result["gpu_vendor"] == "amd"
    assert result["gpu_vram_source"] == "linux-sysfs-pci"


def test_gpu_from_linux_sysfs_lspci_fallback(tmp_path, monkeypatch):
    import awf.hardware.profiler as profiler

    fake_empty = tmp_path / "empty"
    fake_empty.mkdir(parents=True)
    orig_path = profiler.Path

    def fake_path_resolver(p, *a, **k):
        if str(p) in ("/sys/class/drm", "/sys/bus/pci/devices"):
            return fake_empty
        return orig_path(p, *a, **k)

    monkeypatch.setattr(profiler, "Path", fake_path_resolver)
    monkeypatch.setattr(
        profiler,
        "_run_command",
        lambda cmd, **k: (
            "00:02.0 VGA compatible controller [0300]: Intel Corporation [8086:9a49] (rev 01)"
            if cmd[0] == "lspci"
            else ""
        ),
    )

    result = profiler._gpu_from_linux_sysfs()
    assert result is not None
    assert result["gpu_available"] is True
    assert result["gpu_vendor"] == "intel"
    assert result["gpu_vram_source"] == "linux-lspci"
