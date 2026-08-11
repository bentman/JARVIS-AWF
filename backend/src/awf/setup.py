"""Phase 0 bootstrap: populate .env, create cache/sandbox/, create data/awf_db/awf.db.

Exit condition (Section 6, Phase 0): a fresh checkout plus one setup command
produces a valid empty data/awf_db/awf.db and a populated .env.

`--provision`/`--install`/`--verify` (ADR-0008) are the hardware-selected
dependency step `awf-setup` previously had no command for: `--provision`
names the extras `hardware.provisioning.resolve_required_extras` selects for
this host and the reason, without installing anything; `--install` runs the
matching `pip install -e .[...]` command; `--verify`
reports what resolution actually produced - the installed ONNX Runtime
distribution name and version, its available execution providers, and
`pip check`; it also verifies the dev-tooling floor needed by the validation
harness, including Ruff. With no flag, `awf-setup` does the original bootstrap.
"""

import argparse
import base64
import importlib.util
import os
import subprocess
import sys
import tomllib
from pathlib import Path

from awf.db.bootstrap import init_db
from awf.paths import REPO_ROOT, db_path, env_path, sandbox_dir

PLACEHOLDER = "<your-secret-key-here>"

_ORT_DISTRIBUTIONS = ("onnxruntime", "onnxruntime-gpu", "onnxruntime-directml")
_OPENWAKEWORD_DISTRIBUTION = "openwakeword"


def _generate_secret_key() -> str:
    return base64.urlsafe_b64encode(os.urandom(32)).decode("ascii")


def bootstrap_repo(repo_root: Path) -> None:
    dot_env_path = env_path(repo_root)
    example_path = repo_root / ".env.example"

    if not dot_env_path.exists():
        if not example_path.exists():
            raise FileNotFoundError(f"missing template: {example_path}")
        content = example_path.read_text()
        content = content.replace(PLACEHOLDER, _generate_secret_key())
        dot_env_path.write_text(content)

    sandbox_dir(repo_root).mkdir(parents=True, exist_ok=True)
    (repo_root / "cache" / "temp").mkdir(parents=True, exist_ok=True)

    init_db(db_path(repo_root))


def _resolve_extras() -> tuple[list[str], str]:
    from awf.hardware.profiler import collect_inventory
    from awf.hardware.provisioning import explain_ort_extra, resolve_required_extras

    inventory = collect_inventory()
    _extra, reason = explain_ort_extra(inventory)
    return resolve_required_extras(inventory), reason


def cmd_provision(_repo_root: Path) -> int:
    extras, reason = _resolve_extras()
    print(f"extras: {','.join(extras)}")
    print(f"reason: {reason}")
    print(f"command: pip install -e .[{','.join(extras)}]")
    return 0


# onnxruntime/onnxruntime-gpu/onnxruntime-directml all provide the same
# `onnxruntime` import name, so at most one may survive an install. But
# `kokoro-onnx` and `openwakeword` (Context) each hard-depend on plain
# `onnxruntime` regardless of which extra is requested, so a single
# `pip install -e .[<extra>,dev]` installs both it and the accelerator wheel
# side by side - both provide the same import name and collide on disk, and
# pip's own bookkeeping (`pip list`) keeps listing the loser as installed
# even once its files are overwritten. Uninstalling the loser's now-stale
# metadata, then a forced, dependency-free reinstall of the selected
# distribution, leaves both the files on disk and pip's own record correct.
_EXTRA_TARGET_PACKAGE = {
    "hw-ort-cpu": None,  # already what kokoro-onnx/openwakeword installed
    "hw-ort-cuda": "onnxruntime-gpu>=1.28",
    "hw-ort-directml": "onnxruntime-directml>=1.28",
    "hw-ort-qnn": None,  # onnxruntime-qnn has a distinct import name, no clobber
}


def cmd_install(repo_root: Path) -> int:
    extras, reason = _resolve_extras()
    extra = next(item for item in extras if item in _EXTRA_TARGET_PACKAGE)
    print(f"extras: {','.join(extras)}")
    print(f"reason: {reason}")

    for command in _install_commands(repo_root, extras):
        result = subprocess.run(command, cwd=repo_root)
        if result.returncode != 0:
            return result.returncode

    target = _EXTRA_TARGET_PACKAGE[extra]
    if target is None:
        return 0

    target_distribution = target.split(">=")[0].split("==")[0]
    for loser in _ORT_DISTRIBUTIONS:
        if loser == target_distribution:
            continue
        subprocess.run([sys.executable, "-m", "pip", "uninstall", "-y", loser], cwd=repo_root, capture_output=True)

    force_result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--force-reinstall", "--no-deps", target],
        cwd=repo_root,
    )
    return force_result.returncode


def _installed_ort_distribution() -> tuple[str | None, str | None]:
    import importlib.metadata

    for name in _ORT_DISTRIBUTIONS:
        try:
            return name, importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            continue
    return None, None


def _installed_distribution_version(name: str) -> str | None:
    import importlib.metadata

    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


# kokoro-onnx/openwakeword/faster-whisper each hard-pin the literal
# distribution name `onnxruntime`, which pip has no way to know
# `onnxruntime-gpu`/`onnxruntime-directml` also satisfy (there is no PyPI
# "provides" mechanism for that). `pip check` reports exactly this
# complaint whenever a non-base extra is selected - expected, not a defect,
# since `import onnxruntime` and its providers are what actually matters.
_KNOWN_ORT_NAME_CONFLICT = "requires onnxruntime, which is not installed"
_KNOWN_LINUX_OPENWAKEWORD_TFLITE_METADATA = "requires tflite-runtime, which is not installed"


def _read_pyproject(repo_root: Path) -> dict:
    return tomllib.loads((repo_root / "pyproject.toml").read_text(encoding="utf-8"))


def _requirement_applies(requirement: str) -> bool:
    _specifier, separator, marker = requirement.partition(";")
    if not separator:
        return True
    try:
        from packaging.markers import Marker
    except ImportError:
        from pip._vendor.packaging.markers import Marker

    return Marker(marker.strip()).evaluate()


def _distribution_name(requirement: str) -> str:
    candidate = requirement.split(";", 1)[0].strip()
    if "[" in candidate:
        candidate = candidate.split("[", 1)[0]
    for separator in ("<", ">", "=", "!", " "):
        if separator in candidate:
            candidate = candidate.split(separator, 1)[0]
    return candidate.strip().lower().replace("_", "-")


def _selected_requirement_specs(repo_root: Path, extras: list[str]) -> list[str]:
    data = _read_pyproject(repo_root)
    project = data.get("project", {})
    optional = project.get("optional-dependencies", {})
    requirements = [
        *project.get("dependencies", []),
        *(requirement for extra in extras for requirement in optional.get(extra, [])),
    ]
    return [str(requirement).strip() for requirement in requirements if _requirement_applies(str(requirement))]


def _linux_openwakeword_requirement(repo_root: Path, extras: list[str]) -> str | None:
    requirements = [
        requirement.split(";", 1)[0].strip()
        for requirement in _selected_requirement_specs(repo_root, extras)
        if _distribution_name(requirement) == _OPENWAKEWORD_DISTRIBUTION
    ]
    if len(requirements) > 1:
        raise ValueError("Linux OpenWakeWord provisioning requires one declared package")
    return requirements[0] if requirements else None


def _install_commands(repo_root: Path, extras: list[str]) -> list[list[str]]:
    editable = [sys.executable, "-m", "pip", "install", "-e", f".[{','.join(extras)}]"]
    if sys.platform != "linux":
        return [editable]

    openwakeword_requirement = _linux_openwakeword_requirement(repo_root, extras)
    if openwakeword_requirement is None:
        return [editable]

    requirements = [
        requirement
        for requirement in _selected_requirement_specs(repo_root, extras)
        if _distribution_name(requirement) != _OPENWAKEWORD_DISTRIBUTION
    ]
    return [
        [sys.executable, "-m", "pip", "uninstall", "-y", _OPENWAKEWORD_DISTRIBUTION],
        [*editable, "--no-deps"],
        [sys.executable, "-m", "pip", "install", *requirements],
        [sys.executable, "-m", "pip", "install", "--no-deps", openwakeword_requirement],
    ]


def _package_importable(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def _activate_optional_providers_for_verify():
    try:
        from awf.hardware.preflight import activate_qnn_execution_provider
    except Exception:
        return None
    try:
        return activate_qnn_execution_provider()
    except Exception:
        return None


def _linux_openwakeword_tflite_waiver_applies() -> bool:
    return (
        sys.platform == "linux"
        and _installed_distribution_version(_OPENWAKEWORD_DISTRIBUTION) is not None
        and _package_importable("openwakeword")
        and _package_importable("onnxruntime")
    )


def _known_pip_check_line(line: str) -> bool:
    normalized = line.strip().lower()
    if _KNOWN_ORT_NAME_CONFLICT in normalized:
        return True
    return (
        normalized.startswith(f"{_OPENWAKEWORD_DISTRIBUTION} ")
        and _KNOWN_LINUX_OPENWAKEWORD_TFLITE_METADATA in normalized
        and _linux_openwakeword_tflite_waiver_applies()
    )


def cmd_verify(repo_root: Path) -> int:
    distribution_name, version = _installed_ort_distribution()
    qnn_version = _installed_distribution_version("onnxruntime-qnn")
    ruff_version = _installed_distribution_version("ruff")
    print(f"distribution: {distribution_name}")
    print(f"version: {version}")
    print(f"qnn_distribution_version: {qnn_version}")
    print(f"ruff_version: {ruff_version}")

    try:
        qnn_activation = _activate_optional_providers_for_verify()
        if qnn_activation is not None:
            print(f"qnn_provider_registered: {qnn_activation.provider_registered}")
            print(f"qnn_provider_library_path: {qnn_activation.provider_library_path}")
            print(f"qnn_backend_path: {qnn_activation.backend_path}")
            print(f"qnn_activation_error: {qnn_activation.error}")
        import onnxruntime as ort

        providers = list(ort.get_available_providers())
    except ImportError as exc:
        providers = None
        print(f"onnxruntime not importable: {exc}")
    print(f"available_providers: {providers}")

    pip_check_env = os.environ.copy()
    pip_check_env["PIP_CACHE_DIR"] = str(repo_root / "cache" / "pip")
    pip_check = subprocess.run(
        [sys.executable, "-m", "pip", "check"],
        cwd=repo_root,
        env=pip_check_env,
        capture_output=True,
        text=True,
    )
    check_lines = [line for line in pip_check.stdout.splitlines() if line.strip()]
    unexpected_lines = [line for line in check_lines if not _known_pip_check_line(line)]

    if pip_check.returncode == 0:
        print("pip_check: OK")
    elif not unexpected_lines:
        print("pip_check: reports known runtime metadata conflicts below (expected, not a defect):")
        print(pip_check.stdout)
    else:
        print("pip_check: FAILED")
        print(pip_check.stdout)
        print(pip_check.stderr)

    healthy = distribution_name is not None and providers is not None and ruff_version is not None
    if healthy and (pip_check.returncode == 0 or not unexpected_lines):
        return 0
    return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="awf-setup")
    parser.add_argument("--provision", action="store_true")
    parser.add_argument("--install", action="store_true")
    parser.add_argument("--verify", action="store_true")
    return parser


def run(argv: list[str], repo_root: Path) -> int:
    args = build_parser().parse_args(argv)

    commands = []
    if args.provision:
        commands.append(cmd_provision)
    if args.install:
        commands.append(cmd_install)
    if args.verify:
        commands.append(cmd_verify)

    if not commands:
        bootstrap_repo(repo_root)
        print(f"AWF bootstrap complete: {db_path(repo_root)}")
        return 0

    return max(command(repo_root) for command in commands)


def main() -> int:
    return run(sys.argv[1:], REPO_ROOT)


if __name__ == "__main__":
    sys.exit(main())
