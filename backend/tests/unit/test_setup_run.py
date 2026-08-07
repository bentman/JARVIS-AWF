import shutil

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
