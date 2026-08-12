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


def test_registry_publish_rejects_stale_workflow_metadata_digest(tmp_path):
    repo_root, conn = make_awf_repo(tmp_path)
    source = tmp_path / "stale-workflow.yaml"
    source.write_text(
        "\n".join(
            [
                "apiVersion: awf/v1",
                "kind: Workflow",
                "metadata:",
                "  name: stale",
                "  version: 1.0.0",
                "  digest: sha256:not-real",
                "spec:",
                "  inputSchema: {}",
                "  outputSchema: {}",
                "  budgets: {}",
                "  nodes:",
                "    - id: check",
                "      type: gate",
                "      checkCommand: 'true'",
                "      next: null",
                "  outputs: {}",
                "",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(CoreOpError, match=r"metadata\.digest mismatch"):
        op_registry_publish(repo_root, conn, path=source, kind="workflows")


def test_registry_validate_representative_shipped_kinds(repo_root):
    agent = op_registry_validate(repo_root / "config" / "app_registry" / "agents" / "builder" / "1.0.0.md")
    mcp = op_registry_validate(repo_root / "config" / "app_registry" / "mcp" / "context7" / "1.0.0.yaml")
    skill = op_registry_validate(repo_root / "config" / "app_registry" / "skills" / "demo-skill" / "1.0.0")
    model_profile = op_registry_validate(
        repo_root / "config" / "app_registry" / "model-profiles" / "resident-mind" / "1.0.0.yaml"
    )
    workflow = op_registry_validate(
        repo_root / "config" / "app_registry" / "workflows" / "assistant-default" / "1.0.0.yaml"
    )
    network_fetch = op_registry_validate(
        repo_root / "config" / "app_registry" / "capabilities" / "network_fetch" / "1.0.0.yaml"
    )

    assert agent["kind"] == "AgentManifest"
    assert mcp["kind"] == "McpServer"
    assert skill["kind"] == "Skill"
    assert model_profile["ref"] == "resident-mind@1.0.0"
    assert workflow["ref"] == "assistant-default@1.0.0"
    assert network_fetch["ref"] == "network_fetch@1.0.0"


def test_data_registry_scaffolds_all_declared_data_roots(repo_root):
    expected = {
        "agents",
        "capabilities",
        "mcp",
        "memory-profiles",
        "model-profiles",
        "personas",
        "semantic-memories",
        "skills",
        "voice-profiles",
        "workflows",
    }

    actual = {path.name for path in (repo_root / "data" / "registry").iterdir() if path.is_dir()}

    assert expected <= actual


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


def test_registry_reindex_and_config_model_profiles_are_resolvable(tmp_path, repo_root):
    from awf.db.schema import DDL_STATEMENTS

    conn = get_connection(":memory:")
    for statement in DDL_STATEMENTS:
        conn.execute(statement)

    counts = op_registry_reindex(repo_root, conn)

    assert counts["agents"]["config"] >= 3
    assert counts["mcp"]["config"] >= 1
    assert counts["model-profiles"]["config"] >= 7

    fake_root, _conn = make_awf_repo(tmp_path)
    example_dir = fake_root / "config" / "app_registry" / "model-profiles" / "example-demo"
    example_dir.mkdir(parents=True)
    (example_dir / "1.0.0.yaml").write_text(
        "\n".join(
            [
                "name: example-demo",
                "version: 1.0.0",
                "purpose: coding",
                "privacy: {maximum_data_class: internal, local_only: true}",
                "candidates:",
                "  - {provider: ollama, model: local, priority: 1, enabled: true}",
                "fallback: {mode: none, allow_quality_degrade: false}",
                "limits: {max_input_tokens_per_call: 1, max_output_tokens_per_call: 1, max_cost_usd_per_call: 0}",
                "",
            ]
        )
    )
    assert op_registry_list(fake_root, kind="model-profiles") == [
        {"source": "config", "kind": "model-profiles", "name": "example-demo", "version": "1.0.0"}
    ]
