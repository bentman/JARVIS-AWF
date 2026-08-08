import importlib.util
from pathlib import Path


def _load_validator(repo_root: Path):
    path = repo_root / "scripts" / "validate_backend.py"
    spec = importlib.util.spec_from_file_location("validate_backend_under_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_parse_pytest_summary_counts_includes_all_reported_outcomes(repo_root):
    validator = _load_validator(repo_root)

    counts = validator._parse_pytest_summary_counts("1 passed, 2 failed, 3 skipped, 4 deselected, 5 warnings, 6 errors\n")

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
