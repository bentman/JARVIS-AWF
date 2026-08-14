import ast
import importlib.util
from pathlib import Path

from awf.protocol.methods import METHOD_NAMES
from awf.server import stdio


def _load_generator(repo_root: Path):
    path = repo_root / "scripts" / "generate_protocol.py"
    spec = importlib.util.spec_from_file_location("generate_protocol_under_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_stdio_method_names_are_generated_from_manifest():
    assert stdio.METHOD_NAMES == METHOD_NAMES


def test_generated_protocol_files_are_current(repo_root):
    generator = _load_generator(repo_root)

    assert generator.check_generated() == 0


def test_manifest_cli_paths_exist_in_argparse(repo_root):
    generator = _load_generator(repo_root)

    assert generator.check_argparse_parity() == 0


def test_check_mode_only_checks_generated_files(repo_root, monkeypatch):
    generator = _load_generator(repo_root)
    calls = []
    monkeypatch.setattr(generator, "check_generated", lambda: calls.append("generated") or 0)
    monkeypatch.setattr(generator, "check_argparse_parity", lambda: calls.append("argparse") or 1)

    assert generator.main(["--check"]) == 0
    assert calls == ["generated"]


def test_non_cli_awf_modules_do_not_import_awf_cli(repo_root):
    src_root = repo_root / "backend" / "src" / "awf"
    offenders = []
    for path in src_root.rglob("*.py"):
        relative = path.relative_to(src_root)
        if relative.parts[0] == "cli":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("awf.cli"):
                offenders.append(f"{path.relative_to(repo_root)}:{node.lineno}")
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("awf.cli"):
                        offenders.append(f"{path.relative_to(repo_root)}:{node.lineno}")

    assert offenders == []
