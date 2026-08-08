"""Backend validation harness (ADR-0006).

Six commands, each returning a code from one shared contract:

  0 = PASS
  1 = FAIL
  2 = SKIPPED                  (pytest return code 5 with no tests collected,
                                 or return code 0 with zero tests passed and
                                 at least one skipped - e.g. every `live`
                                 test skipping on a host lacking the
                                 resource it needs)
  3 = ENVIRONMENT_UNSATISFIED  (pytest not importable)

| Command       | Runs                                            | Writes                                |
|---------------|--------------------------------------------------|----------------------------------------|
| profile       | environment fingerprint, no tests                 | reports/diagnostics/<ts>-profile.txt   |
| unit          | python -m pytest -v backend/tests/unit            | reports/validation/<ts>-unit.txt        |
| integration   | python -m pytest -v backend/tests/integration     | reports/validation/<ts>-integration.txt |
| runtime       | python -m pytest -v -m live backend/tests         | reports/validation/<ts>-runtime.txt     |
| regression    | the always-safe minimal set (backend/tests/unit)  | reports/validation/<ts>-regression.txt |
| ci            | python -m pytest -v -m "not live" backend/tests   | reports/validation/<ts>-ci.txt          |

`runtime` scans the whole suite filtered by the `live` marker rather than
only `backend/tests/runtime/`: some modules keep one `live`-marked test
alongside otherwise-deterministic tests in `unit/`/`integration/` (per
module, not per directory), so marker filtering across the whole tree is
what actually selects every host-dependent check.
"""

import argparse
import datetime
import platform
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
REPORTS_DIR = REPO_ROOT / "reports"
CACHE_DIR = REPO_ROOT / "cache" / "validate_backend"
PYTEST_CACHE_DIR = CACHE_DIR / "pytest"
REPORT_FILE_LIMIT = 35

EXIT_PASS = 0
EXIT_FAIL = 1
EXIT_SKIPPED = 2
EXIT_ENVIRONMENT_UNSATISFIED = 3

_PYTEST_NO_TESTS_COLLECTED = 5
_SUMMARY_COUNT_RE = re.compile(r"(\d+) (passed|failed|skipped|deselected|errors?|warnings?)")
_SUMMARY_COUNT_KEYS = ("passed", "failed", "skipped", "deselected", "errors", "warnings")

_SUMMARY_BY_CODE = {
    EXIT_PASS: "PASS",
    EXIT_FAIL: "FAIL",
    EXIT_SKIPPED: "SKIPPED",
    EXIT_ENVIRONMENT_UNSATISFIED: "ENVIRONMENT_UNSATISFIED",
}


def _timestamp() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d%H%M%S")


def _utc_now_rfc3339() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _trim_report_files(reports_dir: Path = REPORTS_DIR, max_files: int = REPORT_FILE_LIMIT) -> int:
    """Keep the newest report text files within each report directory."""
    removed = 0
    if not reports_dir.exists():
        return removed
    directories = [reports_dir, *(path for path in reports_dir.rglob("*") if path.is_dir())]
    for directory in sorted(directories):
        report_files = sorted(
            directory.glob("*.txt"),
            key=lambda path: (path.stat().st_mtime_ns, path.name),
            reverse=True,
        )
        for path in report_files[max_files:]:
            path.unlink()
            removed += 1
    return removed


def _pytest_importable() -> bool:
    try:
        import pytest  # noqa: F401
    except ImportError:
        return False
    return True


def _parse_pytest_summary_counts(stdout: str) -> dict[str, int]:
    """Extract pytest's final outcome counts, normalizing singular labels."""
    lines = [line for line in stdout.strip().splitlines() if line.strip()]
    summary_line = lines[-1] if lines else ""
    counts = {key: 0 for key in _SUMMARY_COUNT_KEYS}
    for count, label in _SUMMARY_COUNT_RE.findall(summary_line):
        normalized_label = {"error": "errors", "warning": "warnings"}.get(label, label)
        counts[normalized_label] = int(count)
    return counts


def _map_pytest_result(result: subprocess.CompletedProcess) -> int:
    if result.returncode == _PYTEST_NO_TESTS_COLLECTED:
        return EXIT_SKIPPED
    if result.returncode != 0:
        return EXIT_FAIL
    counts = _parse_pytest_summary_counts(result.stdout)
    if counts["passed"] == 0 and counts["skipped"] > 0:
        return EXIT_SKIPPED
    return EXIT_PASS


def _pytest_command(args: list[str]) -> list[str]:
    return [sys.executable, "-u", "-m", "pytest", "-o", f"cache_dir={PYTEST_CACHE_DIR}", "-v", *args]


def _run_pytest(args: list[str]) -> subprocess.CompletedProcess:
    """Stream pytest output while retaining its exact terminal transcript."""
    process = subprocess.Popen(
        _pytest_command(args),
        cwd=REPO_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert process.stdout is not None
    output: list[str] = []
    for line in process.stdout:
        print(line, end="")
        output.append(line)
    returncode = process.wait()
    return subprocess.CompletedProcess(_pytest_command(args), returncode, "".join(output), "")


def _resolve_host_class_id() -> str:
    try:
        from awf.hardware.profiler import resolve_hardware_profile_id

        profile_id, _evidence = resolve_hardware_profile_id(REPO_ROOT)
    except Exception as exc:
        return f"unresolved:{type(exc).__name__}"
    return profile_id


def _format_counts(counts: dict[str, int]) -> str:
    return " ".join(f"{key}={counts[key]}" for key in _SUMMARY_COUNT_KEYS)


def _build_test_report(
    *,
    command_name: str,
    started_at: str,
    host_class_id: str,
    pytest_args: list[str],
    pytest_return_code: int | str,
    validator_return_code: int,
    pytest_output: str,
) -> str:
    counts = _parse_pytest_summary_counts(pytest_output)
    command = " ".join(
        ["python", "-u", "-m", "pytest", "-o", f"cache_dir={PYTEST_CACHE_DIR}", "-v", *pytest_args]
    )
    return (
        f"started_at: {started_at}\n"
        f"command: {command_name}\n"
        f"host_class_id: {host_class_id}\n"
        f"pytest_command: {command}\n"
        f"pytest_return_code: {pytest_return_code}\n"
        f"validator_return_code: {validator_return_code}\n"
        "pytest_output:\n"
        f"{pytest_output}"
        f"final_summary: {_SUMMARY_BY_CODE[validator_return_code]} {_format_counts(counts)}\n"
    )


def _run_test_command(command_name: str, pytest_args: list[str]) -> int:
    started_at = _utc_now_rfc3339()
    host_class_id = _resolve_host_class_id()
    if not _pytest_importable():
        validator_return_code = EXIT_ENVIRONMENT_UNSATISFIED
        pytest_return_code: int | str = ""
        pytest_output = "pytest is not importable in this environment\n"
        print(pytest_output, end="", file=sys.stderr)
    else:
        result = _run_pytest(pytest_args)
        pytest_return_code = result.returncode
        validator_return_code = _map_pytest_result(result)
        pytest_output = result.stdout

    report = _build_test_report(
        command_name=command_name,
        started_at=started_at,
        host_class_id=host_class_id,
        pytest_args=pytest_args,
        pytest_return_code=pytest_return_code,
        validator_return_code=validator_return_code,
        pytest_output=pytest_output,
    )
    validation_dir = REPORTS_DIR / "validation"
    validation_dir.mkdir(parents=True, exist_ok=True)
    out_path = validation_dir / f"{_timestamp()}-{command_name}.txt"
    out_path.write_text(report)
    print(f"final_summary: {_SUMMARY_BY_CODE[validator_return_code]} {_format_counts(_parse_pytest_summary_counts(pytest_output))}")
    print(f"wrote {out_path}")
    return validator_return_code


def cmd_profile(_args: argparse.Namespace) -> int:
    lines = [
        f"started_at={_utc_now_rfc3339()}",
        "command=profile",
        f"os={platform.system()}",
        f"arch={platform.machine()}",
        f"python={platform.python_version()}",
    ]
    try:
        from awf.hardware.profiler import resolve_hardware_profile_id
    except Exception as exc:
        lines.append(f"host_class_id=unresolved:{type(exc).__name__}")
        lines.append(f"awf_import_error={type(exc).__name__}: {exc}")
    else:
        try:
            profile_id, evidence = resolve_hardware_profile_id(REPO_ROOT)
            lines.append(f"host_class_id={profile_id}")
            lines.append(f"hardware_profile_id={profile_id}")
            lines.append(f"hardware_profile_evidence={evidence}")
        except Exception as exc:
            lines.append(f"host_class_id=unresolved:{type(exc).__name__}")
            lines.append(f"hardware_profile_error={type(exc).__name__}: {exc}")

    diagnostics_dir = REPORTS_DIR / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    out_path = diagnostics_dir / f"{_timestamp()}-profile.txt"
    content = "\n".join(lines) + "\n"
    out_path.write_text(content)
    print(content, end="")
    print(f"wrote {out_path}")
    return EXIT_PASS


def cmd_unit(_args: argparse.Namespace) -> int:
    return _run_test_command("unit", ["backend/tests/unit"])


def cmd_integration(_args: argparse.Namespace) -> int:
    return _run_test_command("integration", ["backend/tests/integration"])


def cmd_runtime(_args: argparse.Namespace) -> int:
    return _run_test_command("runtime", ["-m", "live", "backend/tests"])


def cmd_ci(_args: argparse.Namespace) -> int:
    return _run_test_command("ci", ["-m", "not live", "backend/tests"])


def cmd_regression(_args: argparse.Namespace) -> int:
    return _run_test_command("regression", ["backend/tests/unit"])


COMMANDS = {
    "profile": cmd_profile,
    "unit": cmd_unit,
    "integration": cmd_integration,
    "runtime": cmd_runtime,
    "regression": cmd_regression,
    "ci": cmd_ci,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AWF backend validation harness (ADR-0006)")
    parser.add_argument("command", choices=sorted(COMMANDS))
    args = parser.parse_args(argv)
    result = COMMANDS[args.command](args)
    _trim_report_files()
    return result


if __name__ == "__main__":
    sys.exit(main())
