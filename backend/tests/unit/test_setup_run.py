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
    monkeypatch.setattr(awf_setup, "_resolve_extras", lambda: (["hw-ort-cpu", "speech", "wake-word", "dev"], "test reason"))

    exit_code = awf_setup.cmd_provision(fake_repo)

    assert exit_code == 0
    assert "command: pip install -e .[hw-ort-cpu,speech,wake-word,dev]" in capsys.readouterr().out


def test_install_uses_selected_hardware_speech_and_dev_extras(fake_repo, monkeypatch):
    calls = []
    monkeypatch.setattr(awf_setup, "_resolve_extras", lambda: (["hw-ort-cpu", "speech", "wake-word", "dev"], "test reason"))

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(awf_setup.subprocess, "run", fake_run)

    exit_code = awf_setup.cmd_install(fake_repo)

    assert exit_code == 0
    assert calls[0][0][-1] == ".[hw-ort-cpu,speech,wake-word,dev]"


def test_linux_openwakeword_install_uses_no_deps_for_tflite_metadata_gap(fake_repo, monkeypatch):
    (fake_repo / "pyproject.toml").write_text(
        """
[project]
dependencies = ["PyYAML>=6"]

[project.optional-dependencies]
speech = ["onnx-asr>=0.8"]
wake-word = ["openwakeword==0.6.0", "requests>=2.32", "scikit-learn>=1.5", "scipy>=1.11"]
hw-ort-cpu = ["onnxruntime>=1.28"]
dev = ["ruff>=0.15.22"]
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(awf_setup.sys, "platform", "linux")

    commands = awf_setup._install_commands(fake_repo, ["hw-ort-cpu", "speech", "wake-word", "dev"])

    assert commands[0][-2:] == ["-y", "openwakeword"]
    assert commands[1][-2:] == [".[hw-ort-cpu,speech,wake-word,dev]", "--no-deps"]
    assert "openwakeword==0.6.0" not in commands[2]
    assert "requests>=2.32" in commands[2]
    assert "scikit-learn>=1.5" in commands[2]
    assert "scipy>=1.11" in commands[2]
    assert commands[3][-2:] == ["--no-deps", "openwakeword==0.6.0"]


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
    output = capsys.readouterr().out
    assert "qnn_distribution_version: x" in output
    assert "ruff_version: None" in output
    assert calls[0][1]["cwd"] == fake_repo
    assert calls[0][1]["env"]["PIP_CACHE_DIR"] == str(fake_repo / "cache" / "pip")


def test_verify_accepts_successful_pip_check_output(fake_repo, monkeypatch, capsys):
    monkeypatch.setattr(awf_setup, "_installed_ort_distribution", lambda: ("onnxruntime", "1.28.0"))
    monkeypatch.setattr(awf_setup, "_installed_distribution_version", lambda name: "0.16.2")
    activated = []
    monkeypatch.setattr(awf_setup, "_activate_optional_providers_for_verify", lambda: activated.append(True))

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
    assert activated == [True]
    assert "pip_check: OK" in capsys.readouterr().out


def test_verify_accepts_linux_openwakeword_tflite_metadata_gap(fake_repo, monkeypatch, capsys):
    monkeypatch.setattr(awf_setup.sys, "platform", "linux")
    monkeypatch.setattr(awf_setup, "_installed_ort_distribution", lambda: ("onnxruntime", "1.28.0"))
    monkeypatch.setattr(awf_setup, "_installed_distribution_version", lambda name: "0.16.2")
    monkeypatch.setattr(awf_setup, "_package_importable", lambda name: name in {"openwakeword", "onnxruntime"})

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
            1,
            stdout="openwakeword 0.6.0 requires tflite-runtime, which is not installed.\n",
            stderr="",
        ),
    )

    exit_code = awf_setup.cmd_verify(fake_repo)

    assert exit_code == 0
    assert "known runtime metadata conflicts" in capsys.readouterr().out


def test_verify_rejects_unexpected_linux_openwakeword_dependency_gap(fake_repo, monkeypatch, capsys):
    monkeypatch.setattr(awf_setup.sys, "platform", "linux")
    monkeypatch.setattr(awf_setup, "_installed_ort_distribution", lambda: ("onnxruntime", "1.28.0"))
    monkeypatch.setattr(awf_setup, "_installed_distribution_version", lambda name: "0.16.2")
    monkeypatch.setattr(awf_setup, "_package_importable", lambda name: name in {"openwakeword", "onnxruntime"})

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
            1,
            stdout=(
                "openwakeword 0.6.0 requires requests, which is not installed.\n"
                "openwakeword 0.6.0 requires tflite-runtime, which is not installed.\n"
            ),
            stderr="",
        ),
    )

    exit_code = awf_setup.cmd_verify(fake_repo)

    assert exit_code == 1
    assert "pip_check: FAILED" in capsys.readouterr().out
