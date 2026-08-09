import pytest
from backend.tests.support import make_awf_repo

from awf.cli.core_ops import (
    CoreOpError,
    op_registry_get,
    op_registry_list,
    op_registry_publish,
    op_registry_reindex,
    op_registry_retire,
    op_registry_trust,
    op_registry_validate,
)
from awf.db.connection import get_connection
from awf.registry.mcp_server import McpServerValidationError


def test_registry_validate_recognizes_capability_and_rejects_garbage(tmp_path, fixtures_dir):
    result = op_registry_validate(fixtures_dir / "test_phase1" / "test_phase1_read_file_r0.yaml", kind="capabilities")
    assert result["kind"] == "CapabilityRecord"
    assert result["valid"] is True

    bad = tmp_path / "bad.yaml"
    bad.write_text("just: a random mapping\n")
    with pytest.raises(CoreOpError):
        op_registry_validate(bad)


def test_registry_publish_capability_record_round_trips_and_indexes(tmp_path, fixtures_dir):
    repo_root, conn = make_awf_repo(tmp_path)
    source = fixtures_dir / "test_phase1" / "test_phase1_read_file_r0.yaml"

    published = op_registry_publish(repo_root, conn, path=source, kind="capabilities")

    assert published["kind"] == "capabilities"
    assert {"source": "data", "kind": "capabilities", "name": published["name"], "version": published["version"]} in (
        op_registry_list(repo_root, kind="capabilities")
    )
    fetched = op_registry_get(
        repo_root, conn, kind="capabilities", name=published["name"], version=published["version"]
    )
    assert fetched["digest"] == published["digest"]
    assert fetched["trust_status"] == "local"
    assert fetched["object"]["risk_class"] == "R0"


def test_registry_publish_rejects_kind_mismatch(tmp_path, fixtures_dir):
    repo_root, conn = make_awf_repo(tmp_path)
    source = fixtures_dir / "test_phase1" / "test_phase1_read_file_r0.yaml"

    with pytest.raises(McpServerValidationError):
        op_registry_publish(repo_root, conn, path=source, kind="mcp")


def test_registry_validate_representative_shipped_kinds(repo_root):
    agent = op_registry_validate(repo_root / "config" / "app_registry" / "agents" / "builder" / "1.0.0.md")
    mcp = op_registry_validate(repo_root / "config" / "app_registry" / "mcp" / "context7" / "1.0.0.yaml")
    skill = op_registry_validate(repo_root / "data" / "registry" / "skills" / "demo-skill" / "1.0.0")

    assert agent["kind"] == "AgentManifest"
    assert mcp["kind"] == "McpServer"
    assert skill["kind"] == "Skill"


def test_registry_retire_then_trust_restores_resolution(tmp_path, fixtures_dir):
    from awf.registry.resolve import RegistryBlockedError, resolve_registry_object

    repo_root, conn = make_awf_repo(tmp_path)
    published = op_registry_publish(
        repo_root, conn, path=fixtures_dir / "test_phase1" / "test_phase1_read_file_r0.yaml", kind="capabilities"
    )

    assert op_registry_retire(
        conn, kind="capabilities", name=published["name"], version=published["version"]
    )["trust_status"] == "blocked"
    with pytest.raises(RegistryBlockedError):
        resolve_registry_object(repo_root, "capabilities", published["name"], published["version"], conn=conn)

    assert op_registry_trust(
        conn, kind="capabilities", name=published["name"], version=published["version"], status="local"
    )["trust_status"] == "local"
    assert resolve_registry_object(repo_root, "capabilities", published["name"], published["version"], conn=conn)[1] == "data"


def test_registry_reindex_and_config_model_profile_exclusion(tmp_path, repo_root):
    from awf.db.schema import DDL_STATEMENTS

    conn = get_connection(":memory:")
    for statement in DDL_STATEMENTS:
        conn.execute(statement)

    counts = op_registry_reindex(repo_root, conn)

    assert counts["agents"]["config"] >= 3
    assert counts["mcp"]["config"] >= 1

    fake_root, _conn = make_awf_repo(tmp_path)
    example_dir = fake_root / "config" / "app_registry" / "model-profiles" / "example-demo"
    example_dir.mkdir(parents=True)
    (example_dir / "1.0.0.yaml").write_text("purpose: coding\n")
    assert op_registry_list(fake_root, kind="model-profiles") == []
