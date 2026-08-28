import importlib.util
import os
from pathlib import Path

from awf.hardware.profiler import HardwareInventory


def _load_validator(repo_root: Path):
    path = repo_root / "scripts" / "validate_backend.py"
    spec = importlib.util.spec_from_file_location("validate_backend_under_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_parse_pytest_summary_counts_includes_all_reported_outcomes(repo_root):
    validator = _load_validator(repo_root)

    counts = validator._parse_pytest_summary_counts(
        "1 passed, 2 failed, 3 skipped, 4 deselected, 5 warnings, 6 errors\n"
    )

    assert counts == {
        "passed": 1,
        "failed": 2,
        "skipped": 3,
        "deselected": 4,
        "errors": 6,
        "warnings": 5,
    }


def test_test_report_has_host_header_output_and_final_summary(repo_root):
    validator = _load_validator(repo_root)

    report = validator._build_test_report(
        command_name="unit",
        started_at="2026-08-08T12:00:00Z",
        host_class_id="linux-x64-cpu",
        pytest_args=["backend/tests/unit"],
        pytest_return_code=0,
        validator_return_code=validator.EXIT_PASS,
        pytest_output="backend/tests/unit/test_example.py::test_example PASSED [100%]\n1 passed, 1 warning in 0.01s\n",
    )

    assert "host_class_id: linux-x64-cpu" in report
    assert "pytest_command: python -u -m pytest -o cache_dir=" in report
    assert "test_example PASSED [100%]" in report
    assert report.endswith("final_summary: PASS passed=1 failed=0 skipped=0 deselected=0 errors=0 warnings=1\n")


def test_trim_report_files_keeps_the_newest_files_per_directory(repo_root, tmp_path):
    validator = _load_validator(repo_root)
    validation_dir = tmp_path / "validation"
    diagnostics_dir = tmp_path / "diagnostics"
    validation_dir.mkdir()
    diagnostics_dir.mkdir()
    for index in range(4):
        path = validation_dir / f"validation-{index}.txt"
        path.write_text(str(index))
        os.utime(path, (index, index))
    diagnostic = diagnostics_dir / "diagnostic.txt"
    diagnostic.write_text("kept independently")

    removed = validator._trim_report_files(tmp_path, max_files=2)

    assert removed == 2
    assert {path.name for path in validation_dir.glob("*.txt")} == {"validation-2.txt", "validation-3.txt"}
    assert diagnostic.exists()


def test_profile_uses_the_same_inventory_selection_as_awf_setup(repo_root, monkeypatch, tmp_path, capsys):
    validator = _load_validator(repo_root)
    import awf.hardware.profiler as profiler

    monkeypatch.setattr(
        profiler,
        "collect_inventory",
        lambda: HardwareInventory(os_name="linux", arch="x64", gpu_vendor="nvidia", cuda_available=True),
    )
    monkeypatch.setattr(
        profiler,
        "resolve_hardware_profile_id",
        lambda _repo_root: ("linux-x64-cpu", {"readiness": "separate runtime evidence"}),
    )
    monkeypatch.setattr(validator, "REPORTS_DIR", tmp_path / "reports")

    assert validator.cmd_profile(None) == validator.EXIT_PASS

    output = capsys.readouterr().out
    assert "host_class_id=linux-x64-cuda" in output
    assert "hardware_provisioning_extra=hw-ort-cuda" in output
    assert "runtime_readiness_profile_id=linux-x64-cpu" in output


def test_focus_runs_path_target_through_shared_report_contract(repo_root, monkeypatch):
    validator = _load_validator(repo_root)
    captured = {}

    def fake_run_test_command(command_name, pytest_args):
        captured["command_name"] = command_name
        captured["pytest_args"] = pytest_args
        return validator.EXIT_PASS

    monkeypatch.setattr(validator, "_run_test_command", fake_run_test_command)

    result = validator.cmd_focus(type("Args", (), {"target": "backend/tests/unit/test_validate_backend_script.py"})())

    assert result == validator.EXIT_PASS
    assert captured == {
        "command_name": "focus",
        "pytest_args": ["backend/tests/unit/test_validate_backend_script.py"],
    }


def test_focus_runs_keyword_target_with_pytest_k(repo_root, monkeypatch):
    validator = _load_validator(repo_root)
    captured = {}
    monkeypatch.setattr(
        validator,
        "_run_test_command",
        lambda command_name, pytest_args: (
            captured.update({"command_name": command_name, "pytest_args": pytest_args}) or validator.EXIT_PASS
        ),
    )

    result = validator.cmd_focus(type("Args", (), {"target": "memory_sessions"})())

    assert result == validator.EXIT_PASS
    assert captured == {"command_name": "focus", "pytest_args": ["-k", "memory_sessions", "backend/tests"]}


def test_ci_runs_protocol_precheck_before_lint(repo_root, monkeypatch):
    validator = _load_validator(repo_root)
    calls = []
    monkeypatch.setattr(validator, "_run_ci_precheck_command", lambda: calls.append("precheck") or validator.EXIT_FAIL)
    monkeypatch.setattr(validator, "_run_lint_command", lambda: calls.append("lint") or validator.EXIT_PASS)

    assert validator.cmd_ci(None) == validator.EXIT_FAIL
    assert calls == ["precheck"]


def test_regression_is_broader_than_unit(repo_root, monkeypatch):
    validator = _load_validator(repo_root)
    captured = {}
    monkeypatch.setattr(
        validator,
        "_run_test_command",
        lambda command_name, pytest_args: (
            captured.update({"command_name": command_name, "pytest_args": pytest_args}) or validator.EXIT_PASS
        ),
    )

    assert validator.cmd_regression(None) == validator.EXIT_PASS
    assert captured == {"command_name": "regression", "pytest_args": ["-m", "not live", "backend/tests"]}
