"""Backend validation harness (ADR-0006).

Six commands, each returning a code from one shared contract:

  0 = PASS
  1 = FAIL
  2 = SKIPPED                  (pytest return code 5, no tests collected)
  3 = ENVIRONMENT_UNSATISFIED  (pytest not importable)

| Command       | Runs                                            | Writes                                |
|---------------|--------------------------------------------------|----------------------------------------|
| profile       | environment fingerprint, no tests                 | reports/diagnostics/<ts>-profile.txt   |
| unit          | python -m pytest -q backend/tests/unit            | -                                       |
| integration   | python -m pytest -q backend/tests/integration     | -                                       |
| runtime       | python -m pytest -q -m live backend/tests         | -                                       |
| regression    | the always-safe minimal set (backend/tests/unit)  | reports/validation/<ts>-regression.txt |
| ci            | python -m pytest -q -m "not live" backend/tests   | -                                       |

`runtime` scans the whole suite filtered by the `live` marker rather than
only `backend/tests/runtime/`: some modules keep one `live`-marked test
alongside otherwise-deterministic tests in `unit/`/`integration/` (per
module, not per directory), so marker filtering across the whole tree is
what actually selects every host-dependent check.
"""

import argparse
import datetime
import platform
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
REPORTS_DIR = REPO_ROOT / "reports"
CACHE_DIR = REPO_ROOT / "cache" / "validate_backend"

EXIT_PASS = 0
EXIT_FAIL = 1
EXIT_SKIPPED = 2
EXIT_ENVIRONMENT_UNSATISFIED = 3

_PYTEST_NO_TESTS_COLLECTED = 5

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


def _pytest_importable() -> bool:
    try:
        import pytest  # noqa: F401
    except ImportError:
        return False
    return True


def _map_pytest_return_code(code: int) -> int:
    if code == 0:
        return EXIT_PASS
    if code == _PYTEST_NO_TESTS_COLLECTED:
        return EXIT_SKIPPED
    return EXIT_FAIL


def _run_pytest(args: list[str]) -> subprocess.CompletedProcess:
    command = [sys.executable, "-m", "pytest", *args]
    return subprocess.run(command, cwd=REPO_ROOT, capture_output=True, text=True)


def _run_pytest_command(args: list[str]) -> int:
    if not _pytest_importable():
        print("pytest is not importable in this environment", file=sys.stderr)
        return EXIT_ENVIRONMENT_UNSATISFIED
    result = _run_pytest(args)
    print(result.stdout, end="")
    print(result.stderr, end="", file=sys.stderr)
    return _map_pytest_return_code(result.returncode)


def cmd_profile(_args: argparse.Namespace) -> int:
    lines = [
        f"os={platform.system()}",
        f"arch={platform.machine()}",
        f"python={platform.python_version()}",
    ]
    try:
        from awf.hardware.profiler import resolve_hardware_profile_id
    except Exception as exc:
        lines.append(f"awf_import_error={type(exc).__name__}: {exc}")
    else:
        try:
            profile_id, evidence = resolve_hardware_profile_id()
            lines.append(f"hardware_profile_id={profile_id}")
            lines.append(f"hardware_profile_evidence={evidence}")
        except Exception as exc:
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
    return _run_pytest_command(["-q", "backend/tests/unit"])


def cmd_integration(_args: argparse.Namespace) -> int:
    return _run_pytest_command(["-q", "backend/tests/integration"])


def cmd_runtime(_args: argparse.Namespace) -> int:
    return _run_pytest_command(["-q", "-m", "live", "backend/tests"])


def cmd_ci(_args: argparse.Namespace) -> int:
    return _run_pytest_command(["-q", "-m", "not live", "backend/tests"])


def cmd_regression(_args: argparse.Namespace) -> int:
    started_at = _utc_now_rfc3339()
    command = "python -m pytest -q backend/tests/unit"

    if not _pytest_importable():
        validator_return_code = EXIT_ENVIRONMENT_UNSATISFIED
        pytest_return_code = ""
        stdout, stderr = "", "pytest is not importable in this environment"
    else:
        result = _run_pytest(["-q", "backend/tests/unit"])
        pytest_return_code = result.returncode
        validator_return_code = _map_pytest_return_code(result.returncode)
        stdout, stderr = result.stdout, result.stderr

    validation_dir = REPORTS_DIR / "validation"
    validation_dir.mkdir(parents=True, exist_ok=True)
    out_path = validation_dir / f"{_timestamp()}-regression.txt"
    report = (
        f"started_at: {started_at}\n"
        f"command: {command}\n"
        f"pytest_return_code: {pytest_return_code}\n"
        f"validator_return_code: {validator_return_code}\n"
        f"summary: {_SUMMARY_BY_CODE[validator_return_code]}\n"
        f"stdout:\n{stdout}\n"
        f"stderr:\n{stderr}\n"
    )
    out_path.write_text(report)
    print(report, end="")
    print(f"wrote {out_path}")
    return validator_return_code


COMMANDS = {
    "profile": cmd_profile,
    "unit": cmd_unit,
    "integration": cmd_integration,
    "runtime": cmd_runtime,
    "regression": cmd_regression,
    "ci": cmd_ci,
}


def main(argv: list[str] | None = None) -> int:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    parser = argparse.ArgumentParser(description="AWF backend validation harness (ADR-0006)")
    parser.add_argument("command", choices=sorted(COMMANDS))
    args = parser.parse_args(argv)
    return COMMANDS[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
