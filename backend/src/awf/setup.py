"""Phase 0 bootstrap: populate .env, create cache/sandbox/, create data/awf_db/awf.db.

Exit condition (Section 6, Phase 0): a fresh checkout plus one setup command
produces a valid empty data/awf_db/awf.db and a populated .env.

`--provision`/`--install`/`--verify` (ADR-0008) are the hardware-selected
dependency step `awf-setup` previously had no command for: `--provision`
names the `hw-ort-*` extra `hardware.provisioning.explain_ort_extra` selects
for this host and the reason, without installing anything; `--install` runs
the `pip install -e .[<extra>,dev]` command `--provision` prints; `--verify`
reports what resolution actually produced - the installed ONNX Runtime
distribution name and version, its available execution providers, and
`pip check`. With no flag, `awf-setup` does the original bootstrap.
"""

import argparse
import base64
import os
import subprocess
import sys
from pathlib import Path

from awf.db.bootstrap import init_db
from awf.paths import REPO_ROOT, db_path, env_path, sandbox_dir

PLACEHOLDER = "<your-secret-key-here>"

_ORT_DISTRIBUTIONS = ("onnxruntime", "onnxruntime-gpu", "onnxruntime-directml")


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

    init_db(db_path(repo_root))


def _resolve_extra() -> tuple[str, str]:
    from awf.hardware.profiler import collect_inventory
    from awf.hardware.provisioning import explain_ort_extra

    return explain_ort_extra(collect_inventory())


def cmd_provision(_repo_root: Path) -> int:
    extra, reason = _resolve_extra()
    print(f"extra: {extra}")
    print(f"reason: {reason}")
    print(f"command: pip install -e .[{extra},dev]")
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
    extra, reason = _resolve_extra()
    print(f"extra: {extra}")
    print(f"reason: {reason}")

    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-e", f".[{extra},dev]"],
        cwd=repo_root,
    )
    if result.returncode != 0:
        return result.returncode

    target = _EXTRA_TARGET_PACKAGE[extra]
    if target is None:
        return 0

    target_distribution = target.split(">=")[0].split("==")[0]
    for loser in _ORT_DISTRIBUTIONS:
        if loser == target_distribution:
            continue
        subprocess.run(
            [sys.executable, "-m", "pip", "uninstall", "-y", loser], cwd=repo_root, capture_output=True
        )

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


# kokoro-onnx/openwakeword/faster-whisper each hard-pin the literal
# distribution name `onnxruntime`, which pip has no way to know
# `onnxruntime-gpu`/`onnxruntime-directml` also satisfy (there is no PyPI
# "provides" mechanism for that). `pip check` reports exactly this
# complaint whenever a non-base extra is selected - expected, not a defect,
# since `import onnxruntime` and its providers are what actually matters.
_KNOWN_ORT_NAME_CONFLICT = "requires onnxruntime, which is not installed"


def cmd_verify(_repo_root: Path) -> int:
    distribution_name, version = _installed_ort_distribution()
    print(f"distribution: {distribution_name}")
    print(f"version: {version}")

    try:
        import onnxruntime as ort

        providers = list(ort.get_available_providers())
    except ImportError as exc:
        providers = None
        print(f"onnxruntime not importable: {exc}")
    print(f"available_providers: {providers}")

    pip_check = subprocess.run([sys.executable, "-m", "pip", "check"], capture_output=True, text=True)
    check_lines = [line for line in pip_check.stdout.splitlines() if line.strip()]
    unexpected_lines = [line for line in check_lines if _KNOWN_ORT_NAME_CONFLICT not in line]

    if not check_lines:
        print("pip_check: OK")
    elif not unexpected_lines:
        print("pip_check: reports the onnxruntime distribution-name conflict below (expected, not a defect):")
        print(pip_check.stdout)
    else:
        print("pip_check: FAILED")
        print(pip_check.stdout)
        print(pip_check.stderr)

    healthy = distribution_name is not None and providers is not None
    if healthy and not unexpected_lines:
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
