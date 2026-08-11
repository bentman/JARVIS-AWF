import shutil
import subprocess

import pytest

from awf import setup as awf_setup


@pytest.fixture
def fake_repo(tmp_path, repo_root):
    shutil.copy(repo_root / ".env.example", tmp_path / ".env.example")
    return tmp_path


def test_run_with_no_flags_still_bootstraps(fake_repo, capsys):
    exit_code = awf_setup.run([], fake_repo)

    assert exit_code == 0
    assert (fake_repo / "cache" / "sandbox").is_dir()
    assert (fake_repo / "data" / "awf_db" / "awf.db").is_file()
    assert "AWF bootstrap complete:" in capsys.readouterr().out


def test_run_invokes_every_requested_flag(fake_repo, monkeypatch):
    called = []

    monkeypatch.setattr(awf_setup, "cmd_provision", lambda repo_root: called.append("provision") or 0)
    monkeypatch.setattr(awf_setup, "cmd_install", lambda repo_root: called.append("install") or 0)
    monkeypatch.setattr(awf_setup, "cmd_verify", lambda repo_root: called.append("verify") or 0)

    exit_code = awf_setup.run(["--provision", "--verify"], fake_repo)

    assert exit_code == 0
    assert called == ["provision", "verify"]


def test_run_returns_max_exit_code_verify_fails(fake_repo, monkeypatch):
    monkeypatch.setattr(awf_setup, "cmd_provision", lambda repo_root: 0)
    monkeypatch.setattr(awf_setup, "cmd_verify", lambda repo_root: 1)

    exit_code = awf_setup.run(["--provision", "--verify"], fake_repo)

    assert exit_code == 1


def test_run_returns_max_exit_code_provision_fails(fake_repo, monkeypatch):
    monkeypatch.setattr(awf_setup, "cmd_provision", lambda repo_root: 1)
    monkeypatch.setattr(awf_setup, "cmd_verify", lambda repo_root: 0)

    exit_code = awf_setup.run(["--provision", "--verify"], fake_repo)

    assert exit_code == 1


def test_run_all_three_flags_invokes_all_in_order(fake_repo, monkeypatch):
    called = []

    monkeypatch.setattr(awf_setup, "cmd_provision", lambda repo_root: called.append("provision") or 0)
    monkeypatch.setattr(awf_setup, "cmd_install", lambda repo_root: called.append("install") or 0)
    monkeypatch.setattr(awf_setup, "cmd_verify", lambda repo_root: called.append("verify") or 0)

    exit_code = awf_setup.run(["--verify", "--install", "--provision"], fake_repo)

    assert exit_code == 0
    assert called == ["provision", "install", "verify"]


def test_provision_prints_install_command_that_includes_host_symmetric_extras(fake_repo, monkeypatch, capsys):
    monkeypatch.setattr(awf_setup, "_resolve_extras", lambda: (["hw-ort-cpu", "speech", "dev"], "test reason"))

    exit_code = awf_setup.cmd_provision(fake_repo)

    assert exit_code == 0
    assert "command: pip install -e .[hw-ort-cpu,speech,dev]" in capsys.readouterr().out


def test_install_uses_selected_hardware_speech_and_dev_extras(fake_repo, monkeypatch):
    calls = []
    monkeypatch.setattr(awf_setup, "_resolve_extras", lambda: (["hw-ort-cpu", "speech", "dev"], "test reason"))

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(awf_setup.subprocess, "run", fake_run)

    exit_code = awf_setup.cmd_install(fake_repo)

    assert exit_code == 0
    assert calls[0][0][-1] == ".[hw-ort-cpu,speech,dev]"


def test_verify_requires_ruff_dev_tooling(fake_repo, monkeypatch, capsys):
    monkeypatch.setattr(awf_setup, "_installed_ort_distribution", lambda: ("onnxruntime", "1.28.0"))
    monkeypatch.setattr(awf_setup, "_installed_distribution_version", lambda name: None if name == "ruff" else "x")
    calls = []

    class FakeOrt:
        @staticmethod
        def get_available_providers():
            return ["CPUExecutionProvider"]

    monkeypatch.setitem(__import__("sys").modules, "onnxruntime", FakeOrt)
    monkeypatch.setattr(
        awf_setup.subprocess,
        "run",
        lambda *args, **kwargs: (
            calls.append((args, kwargs)) or subprocess.CompletedProcess(args, 0, stdout="", stderr="")
        ),
    )

    exit_code = awf_setup.cmd_verify(fake_repo)

    assert exit_code == 1
    assert "ruff_version: None" in capsys.readouterr().out
    assert calls[0][1]["cwd"] == fake_repo
    assert calls[0][1]["env"]["PIP_CACHE_DIR"] == str(fake_repo / "cache" / "pip")


def test_verify_accepts_successful_pip_check_output(fake_repo, monkeypatch, capsys):
    monkeypatch.setattr(awf_setup, "_installed_ort_distribution", lambda: ("onnxruntime", "1.28.0"))
    monkeypatch.setattr(awf_setup, "_installed_distribution_version", lambda name: "0.16.2")

    class FakeOrt:
        @staticmethod
        def get_available_providers():
            return ["CPUExecutionProvider"]

    monkeypatch.setitem(__import__("sys").modules, "onnxruntime", FakeOrt)
    monkeypatch.setattr(
        awf_setup.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args,
            0,
            stdout="No broken requirements found.\n",
            stderr="",
        ),
    )

    exit_code = awf_setup.cmd_verify(fake_repo)

    assert exit_code == 0
    assert "pip_check: OK" in capsys.readouterr().out
