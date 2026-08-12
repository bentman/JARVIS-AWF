import pytest

from awf.machine.policy import MachinePolicyError, resolve_allowed_path, validate_command, validate_url
from awf.registry.capability_record import CapabilityRecordValidationError, parse_capability_record


def test_machine_capability_records_require_matching_constraints():
    raw = {
        "identity": {"type": "activity", "provider": "awf", "name": "command_run", "version": "1.0.0"},
        "schema": {"input": "", "output": ""},
        "effects": {"operation": "execute", "reversible": False, "idempotent": False, "external_side_effect": True},
        "risk_class": "R1",
        "approval": "per-invocation",
        "constraints": {"filesystem": {"allowedRoots": ["worktree"]}},
    }

    with pytest.raises(CapabilityRecordValidationError, match="requires command constraints"):
        parse_capability_record(raw)


def test_r0_machine_capabilities_are_read_only():
    raw = {
        "identity": {"type": "activity", "provider": "awf", "name": "fs_write", "version": "1.0.0"},
        "schema": {"input": "", "output": ""},
        "effects": {"operation": "update", "reversible": True, "idempotent": False, "external_side_effect": False},
        "risk_class": "R0",
        "approval": "never",
        "constraints": {"filesystem": {"allowedRoots": ["worktree"]}},
    }

    with pytest.raises(CapabilityRecordValidationError, match="read-only"):
        parse_capability_record(raw)


def test_network_fetch_capability_requires_non_empty_allowed_hosts():
    raw = {
        "identity": {"type": "activity", "provider": "awf", "name": "network_fetch", "version": "1.0.0"},
        "schema": {"input": "", "output": ""},
        "effects": {"operation": "communicate", "reversible": False, "idempotent": True, "external_side_effect": True},
        "risk_class": "R2",
        "approval": "per-invocation",
        "constraints": {"network": {"allowedHosts": [], "allowedMethods": ["GET"], "maxResponseBytes": 1024}},
    }

    with pytest.raises(CapabilityRecordValidationError, match="non-empty allowedHosts"):
        parse_capability_record(raw)


def test_filesystem_policy_blocks_worktree_escape_and_denied_globs(tmp_path):
    repo_root = tmp_path / "repo"
    worktree = tmp_path / "worktree"
    external_root = tmp_path / "operator-root"
    repo_root.mkdir()
    worktree.mkdir()
    external_root.mkdir()
    external_file = external_root / "allowed.txt"
    external_file.write_text("allowed\n")
    (worktree / ".env").write_text("secret\n")
    (worktree / "data" / "awf_db").mkdir(parents=True)
    (worktree / "data" / "awf_db" / "awf.db").write_text("sqlite\n")
    (worktree / "src").mkdir()
    (worktree / "src" / "allowed.py").write_text("print('ok')\n")

    with pytest.raises(MachinePolicyError, match="outside allowed roots"):
        resolve_allowed_path(
            repo_root=repo_root,
            worktree=worktree,
            run_id="run-1",
            relative_or_absolute="../outside.txt",
            constraints={"allowedRoots": ["worktree"]},
        )

    with pytest.raises(MachinePolicyError, match="path denied"):
        resolve_allowed_path(
            repo_root=repo_root,
            worktree=worktree,
            run_id="run-1",
            relative_or_absolute=".env",
            constraints={"allowedRoots": ["worktree"]},
            must_exist=True,
        )

    with pytest.raises(MachinePolicyError, match="path denied"):
        resolve_allowed_path(
            repo_root=repo_root,
            worktree=worktree,
            run_id="run-1",
            relative_or_absolute="data/awf_db/awf.db",
            constraints={"allowedRoots": ["worktree"]},
            must_exist=True,
        )

    assert (
        resolve_allowed_path(
            repo_root=repo_root,
            worktree=worktree,
            run_id="run-1",
            relative_or_absolute="src/allowed.py",
            constraints={"allowedRoots": ["worktree"], "allowedGlobs": ["src/**"]},
            must_exist=True,
        )
        == worktree / "src" / "allowed.py"
    )

    assert (
        resolve_allowed_path(
            repo_root=repo_root,
            worktree=worktree,
            run_id="run-1",
            relative_or_absolute=str(external_file),
            constraints={"allowedRoots": [str(external_root)]},
            must_exist=True,
        )
        == external_file
    )


def test_command_policy_uses_exact_executable_and_argument_patterns(tmp_path):
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    constraints = {
        "executable": "/bin/echo",
        "allowedArgs": [["hello", "*"]],
        "cwdRoot": "worktree",
        "timeoutSeconds": 5,
    }

    validate_command(argv=["/bin/echo", "hello", "world"], cwd=worktree, worktree=worktree, constraints=constraints)

    with pytest.raises(MachinePolicyError, match="does not match policy"):
        validate_command(argv=["/bin/sh", "-c", "echo bad"], cwd=worktree, worktree=worktree, constraints=constraints)

    with pytest.raises(MachinePolicyError, match="shell metacharacters"):
        validate_command(argv=["/bin/echo", "hello", "world;rm"], cwd=worktree, worktree=worktree, constraints=constraints)


def test_network_policy_requires_allowed_host_method_and_public_address():
    constraints = {"allowedHosts": ["example.com", "*.example.org"], "allowedMethods": ["GET"], "maxResponseBytes": 1024}

    validate_url("https://example.com/docs", "GET", constraints)
    validate_url("https://api.example.org/docs", "GET", constraints)

    with pytest.raises(MachinePolicyError, match="is not allowed"):
        validate_url("https://example.com/docs", "POST", constraints)
    with pytest.raises(MachinePolicyError, match="is not allowed"):
        validate_url("https://example.net/docs", "GET", constraints)
    with pytest.raises(MachinePolicyError, match="private network"):
        validate_url(
            "http://127.0.0.1:8000/docs",
            "GET",
            {"allowedHosts": ["127.0.0.1"], "allowedMethods": ["GET"], "maxResponseBytes": 1024},
        )
