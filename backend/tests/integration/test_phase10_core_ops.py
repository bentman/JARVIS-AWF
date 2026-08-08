from pathlib import Path

import pytest
import yaml
from cryptography.fernet import Fernet

from awf.cli.core_ops import (
    CoreOpError,
    op_approval_approve,
    op_approval_list,
    op_approval_reject,
    op_artifact_list,
    op_artifact_read,
    op_registry_get,
    op_registry_list,
    op_registry_publish,
    op_registry_reindex,
    op_registry_retire,
    op_registry_trust,
    op_registry_validate,
    op_run_list,
    op_run_resume,
    op_run_start,
    op_run_status,
    op_secret_list_names,
    op_secret_set,
)
from awf.db.bootstrap import init_db
from awf.db.connection import get_connection
from awf.engine.run import create_run, create_step
from awf.gates.artifacts import write_finding_artifact
from awf.gates.schema import Finding
from awf.ids import uuid7
from awf.registry.mcp_server import McpServerValidationError


@pytest.fixture
def real_repo_root(repo_root):
    # This module's own test bodies use `repo_root` as a local name for
    # `make_repo(tmp_path)`'s fake registry root, so the real project root
    # (the `repo_root` conftest fixture) is aliased here to avoid a name
    # clash with that convention.
    return repo_root


@pytest.fixture
def real_agent_manifest(real_repo_root):
    return real_repo_root / "config" / "app_registry" / "agents" / "builder" / "1.0.0.md"


@pytest.fixture
def real_mcp_server(real_repo_root):
    return real_repo_root / "config" / "app_registry" / "mcp" / "context7" / "1.0.0.yaml"


@pytest.fixture
def real_skill_dir(real_repo_root):
    return real_repo_root / "data" / "registry" / "skills" / "demo-skill" / "1.0.0"


def make_repo(tmp_path):
    repo_root = tmp_path / "repo"
    (repo_root / "data" / "awf_db").mkdir(parents=True)
    (repo_root / "data" / "registry").mkdir(parents=True)
    (repo_root / "config" / "app_registry").mkdir(parents=True)
    db_path = repo_root / "data" / "awf_db" / "awf.db"
    init_db(db_path)
    conn = get_connection(db_path)
    return repo_root, conn


def test_run_status_raises_for_unknown_run(tmp_path):
    _repo_root, conn = make_repo(tmp_path)
    with pytest.raises(CoreOpError):
        op_run_status(conn, run_id="does-not-exist")


def test_run_status_and_list_reflect_real_rows(tmp_path):
    _repo_root, conn = make_repo(tmp_path)
    create_run(conn, run_id="run-1", workflow_ref="demo@1.0.0")
    create_step(conn, step_id="s1", run_id="run-1", node_id="n1")

    status = op_run_status(conn, run_id="run-1")
    assert status["run_id"] == "run-1"
    assert len(status["steps"]) == 1

    listed = op_run_list(conn)
    assert [r["run_id"] for r in listed] == ["run-1"]


def make_approval(conn, approval_id="ap-1", run_id="run-1", status="pending"):
    conn.execute(
        "INSERT INTO approvals (approval_id, run_id, step_id, action_digest, status, requested_at) "
        "VALUES (?, ?, 's1', 'sha256:deadbeef', ?, '2026-01-01T00:00:00Z')",
        (approval_id, run_id, status),
    )
    conn.commit()


def test_approval_list_shows_only_pending(tmp_path):
    _repo_root, conn = make_repo(tmp_path)
    create_run(conn, run_id="run-1", workflow_ref="demo@1.0.0")
    create_step(conn, step_id="s1", run_id="run-1", node_id="n1")
    make_approval(conn, "ap-1", status="pending")
    make_approval(conn, "ap-2", status="approved")

    pending = op_approval_list(conn)
    assert [a["approval_id"] for a in pending] == ["ap-1"]


def test_approve_then_reject_raises_already_decided(tmp_path):
    _repo_root, conn = make_repo(tmp_path)
    create_run(conn, run_id="run-1", workflow_ref="demo@1.0.0")
    create_step(conn, step_id="s1", run_id="run-1", node_id="n1")
    make_approval(conn, "ap-1")

    result = op_approval_approve(conn, approval_id="ap-1")
    assert result["status"] == "approved"

    with pytest.raises(CoreOpError):
        op_approval_reject(conn, approval_id="ap-1", reason="too late")


def test_reject_records_reason(tmp_path):
    _repo_root, conn = make_repo(tmp_path)
    create_run(conn, run_id="run-1", workflow_ref="demo@1.0.0")
    create_step(conn, step_id="s1", run_id="run-1", node_id="n1")
    make_approval(conn, "ap-1")

    result = op_approval_reject(conn, approval_id="ap-1", reason="not safe")
    assert result == {"approval_id": "ap-1", "status": "rejected", "reason": "not safe"}


def test_approval_actions_raise_for_unknown_id(tmp_path):
    _repo_root, conn = make_repo(tmp_path)
    with pytest.raises(CoreOpError):
        op_approval_approve(conn, approval_id="does-not-exist")


def test_artifact_list_and_read(tmp_path):
    repo_root, conn = make_repo(tmp_path)
    create_run(conn, run_id="run-1", workflow_ref="demo@1.0.0")
    create_step(conn, step_id="s1", run_id="run-1", node_id="check")
    artifacts_root = repo_root / "data" / "artifacts"
    finding = Finding(role="verifier", category="correctness", severity="low", summary="ok")
    artifact_id = write_finding_artifact(
        conn, artifacts_root=artifacts_root, run_id="run-1", step_id="s1", finding=finding
    )

    listed = op_artifact_list(conn, run_id="run-1")
    assert [a["artifact_id"] for a in listed] == [artifact_id]

    read = op_artifact_read(conn, artifact_id=artifact_id, artifacts_root=artifacts_root)
    assert '"summary": "ok"' in read["content"]


def test_registry_validate_recognizes_capability_record(fixtures_dir):
    result = op_registry_validate(
        fixtures_dir / "test_phase1" / "test_phase1_read_file_r0.yaml", kind="capabilities"
    )
    assert result["kind"] == "CapabilityRecord"
    assert result["valid"] is True


def test_registry_validate_rejects_garbage(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("just: a random mapping\n")
    with pytest.raises(CoreOpError):
        op_registry_validate(bad)


def test_registry_publish_capability_record_writes_data_registry_and_index(tmp_path, fixtures_dir):
    repo_root, conn = make_repo(tmp_path)
    source = fixtures_dir / "test_phase1" / "test_phase1_read_file_r0.yaml"

    result = op_registry_publish(repo_root, conn, path=source, kind="capabilities")

    assert result["kind"] == "capabilities"
    published_path = Path(result["path"])
    assert published_path.is_file()
    assert published_path.read_bytes() == source.read_bytes()

    row = conn.execute(
        "SELECT * FROM registry_index WHERE kind = ? AND name = ? AND version = ?",
        (result["kind"], result["name"], result["version"]),
    ).fetchone()
    assert row["source"] == "data"
    assert row["trust_status"] == "local"
    assert row["digest"] == result["digest"]


def test_registry_publish_rejects_a_kind_that_does_not_match_the_parsed_object(tmp_path, fixtures_dir):
    # test_phase1_read_file_r0.yaml is a Capability Record - it has no
    # "type" field, which the mcp loader requires, so asking to publish it
    # as kind="mcp" fails through that loader's own validation.
    repo_root, conn = make_repo(tmp_path)
    source = fixtures_dir / "test_phase1" / "test_phase1_read_file_r0.yaml"

    with pytest.raises(McpServerValidationError):
        op_registry_publish(repo_root, conn, path=source, kind="mcp")


def test_registry_publish_then_list_and_get_find_it(tmp_path, fixtures_dir):
    repo_root, conn = make_repo(tmp_path)
    source = fixtures_dir / "test_phase1" / "test_phase1_read_file_r0.yaml"
    published = op_registry_publish(repo_root, conn, path=source, kind="capabilities")

    listed = op_registry_list(repo_root, kind="capabilities")
    assert {"source": "data", "kind": "capabilities", "name": published["name"], "version": published["version"]} in listed

    fetched = op_registry_get(repo_root, conn, kind="capabilities", name=published["name"], version=published["version"])
    assert fetched["source"] == "data"


def test_registry_validate_recognizes_agent_manifest(real_agent_manifest):
    result = op_registry_validate(real_agent_manifest)
    assert result["kind"] == "AgentManifest"
    assert result["ref"] == "builder@1.0.0"
    assert result["valid"] is True


def test_registry_publish_agent_manifest_writes_data_registry_and_index(tmp_path, real_agent_manifest):
    repo_root, conn = make_repo(tmp_path)

    result = op_registry_publish(repo_root, conn, path=real_agent_manifest, kind="agents")

    assert result["kind"] == "agents"
    assert result["name"] == "builder"
    published_path = Path(result["path"])
    assert published_path.suffix == ".md"
    assert published_path.read_bytes() == real_agent_manifest.read_bytes()

    row = conn.execute(
        "SELECT * FROM registry_index WHERE kind = ? AND name = ? AND version = ?",
        (result["kind"], result["name"], result["version"]),
    ).fetchone()
    assert row["source"] == "data"
    assert row["digest"] == result["digest"]

    fetched = op_registry_get(repo_root, conn, kind="agents", name="builder", version="1.0.0")
    assert fetched["source"] == "data"


def test_registry_list_agents_finds_the_real_shipped_config_defaults(real_repo_root):
    # ADR-0002: /agents lists the shipped config defaults.
    listed = op_registry_list(real_repo_root, kind="agents")

    names = {row["name"] for row in listed if row["source"] == "config"}
    assert {"builder", "verifier", "adversary"} <= names


def test_registry_validate_recognizes_mcp_server(real_mcp_server):
    result = op_registry_validate(real_mcp_server)
    assert result["kind"] == "McpServer"
    assert result["ref"] == "context7@1.0.0"
    assert result["valid"] is True


def test_registry_publish_mcp_server_writes_data_registry_and_index(tmp_path, real_mcp_server):
    repo_root, conn = make_repo(tmp_path)

    result = op_registry_publish(repo_root, conn, path=real_mcp_server, kind="mcp")

    assert result["kind"] == "mcp"
    assert result["name"] == "context7"
    published_path = Path(result["path"])
    assert published_path.read_bytes() == real_mcp_server.read_bytes()

    row = conn.execute(
        "SELECT * FROM registry_index WHERE kind = ? AND name = ? AND version = ?",
        (result["kind"], result["name"], result["version"]),
    ).fetchone()
    assert row["source"] == "data"
    assert row["digest"] == result["digest"]


def test_registry_list_mcp_finds_the_real_shipped_config_defaults(real_repo_root):
    listed = op_registry_list(real_repo_root, kind="mcp")

    names = {row["name"] for row in listed if row["source"] == "config"}
    assert {"context7"} <= names


def test_registry_validate_recognizes_skill_directory(real_skill_dir):
    result = op_registry_validate(real_skill_dir)
    assert result["kind"] == "Skill"
    assert result["ref"] == "demo-skill@1.0.0"
    assert result["valid"] is True


def test_registry_validate_recognizes_skill_md_file(real_skill_dir):
    result = op_registry_validate(real_skill_dir / "SKILL.md")
    assert result["kind"] == "Skill"
    assert result["ref"] == "demo-skill@1.0.0"


def test_registry_publish_skill_writes_data_registry_and_index(tmp_path):
    repo_root, conn = make_repo(tmp_path)
    source_dir = tmp_path / "authoring" / "other-skill" / "1.0.0"
    source_dir.mkdir(parents=True)
    (source_dir / "SKILL.md").write_text(
        "---\nname: other-skill\ndescription: A minimal authored skill.\n---\n\nDo the other thing.\n"
    )
    (source_dir / "scripts").mkdir()
    (source_dir / "scripts" / "run.sh").write_text("echo hi\n")

    result = op_registry_publish(repo_root, conn, path=source_dir, kind="skills")

    assert result["kind"] == "skills"
    assert result["name"] == "other-skill"
    assert result["version"] == "1.0.0"
    published_dir = Path(result["path"])
    assert (published_dir / "SKILL.md").is_file()
    assert (published_dir / "scripts" / "run.sh").is_file()

    row = conn.execute(
        "SELECT * FROM registry_index WHERE kind = 'skills' AND name = 'other-skill' AND version = '1.0.0'"
    ).fetchone()
    assert row["source"] == "data"
    assert row["digest"] == result["digest"]

    fetched_list = op_registry_list(repo_root, kind="skills")
    assert {"source": "data", "kind": "skills", "name": "other-skill", "version": "1.0.0"} in fetched_list


def test_registry_publish_voice_profile_round_trips_through_get_and_list(tmp_path):
    repo_root, conn = make_repo(tmp_path)
    source = tmp_path / "authoring" / "demo-voice.yaml"
    source.parent.mkdir(parents=True)
    source.write_text(
        "name: demo-voice\nversion: 1.0.0\n"
        "persona: {name: Demo, description: x, style_prompt: y}\n"
        "tts:\n"
        "  candidates:\n"
        "    - {engine: kokoro, model: kokoro-v1.0, voice_id: bf_isabella, speed: 1.0, priority: 1, enabled: true}\n"
        "  fallback: {mode: none, allow_quality_degrade: false}\n"
        "privacy: {local_only: true}\n"
        "limits: {max_seconds_per_utterance: 30}\n"
    )

    result = op_registry_publish(repo_root, conn, path=source, kind="voice-profiles")

    assert result["kind"] == "voice-profiles"
    assert result["name"] == "demo-voice"
    assert result["version"] == "1.0.0"

    fetched = op_registry_get(repo_root, conn, kind="voice-profiles", name="demo-voice", version="1.0.0")
    assert fetched["object"]["persona"]["name"] == "Demo"

    listed = op_registry_list(repo_root, kind="voice-profiles")
    assert {"source": "data", "kind": "voice-profiles", "name": "demo-voice", "version": "1.0.0"} in listed


def test_registry_publish_model_profile_round_trips_through_get_and_list(tmp_path):
    repo_root, conn = make_repo(tmp_path)
    source = tmp_path / "authoring" / "demo-model.yaml"
    source.parent.mkdir(parents=True)
    source.write_text(
        "name: demo-model\nversion: 1.0.0\n"
        "purpose: coding\n"
        "privacy: {maximum_data_class: internal, local_only: true}\n"
        "candidates:\n  - {provider: ollama, model: phi4-mini, priority: 1, enabled: true}\n"
        "fallback: {mode: none, allow_quality_degrade: false}\n"
        "limits: {max_input_tokens_per_call: 1, max_output_tokens_per_call: 1, max_cost_usd_per_call: 0}\n"
    )

    result = op_registry_publish(repo_root, conn, path=source, kind="model-profiles")

    assert result["kind"] == "model-profiles"
    assert result["name"] == "demo-model"

    fetched = op_registry_get(repo_root, conn, kind="model-profiles", name="demo-model", version="1.0.0")
    assert fetched["object"]["purpose"] == "coding"

    listed = op_registry_list(repo_root, kind="model-profiles")
    assert {"source": "data", "kind": "model-profiles", "name": "demo-model", "version": "1.0.0"} in listed


def test_registry_get_returns_digest_trust_status_and_object(tmp_path, fixtures_dir):
    repo_root, conn = make_repo(tmp_path)
    source = fixtures_dir / "test_phase1" / "test_phase1_read_file_r0.yaml"
    published = op_registry_publish(repo_root, conn, path=source, kind="capabilities")

    fetched = op_registry_get(
        repo_root, conn, kind="capabilities", name=published["name"], version=published["version"]
    )

    assert fetched["digest"] == published["digest"]
    assert fetched["trust_status"] == "local"
    assert fetched["object"]["risk_class"] == "R0"


def test_registry_retire_then_trust_restores_resolution(tmp_path, fixtures_dir):
    repo_root, conn = make_repo(tmp_path)
    source = fixtures_dir / "test_phase1" / "test_phase1_read_file_r0.yaml"
    published = op_registry_publish(repo_root, conn, path=source, kind="capabilities")

    retired = op_registry_retire(conn, kind="capabilities", name=published["name"], version=published["version"])
    assert retired["trust_status"] == "blocked"

    from awf.registry.resolve import RegistryBlockedError, resolve_registry_object

    with pytest.raises(RegistryBlockedError):
        resolve_registry_object(
            repo_root, "capabilities", published["name"], published["version"], conn=conn
        )

    trusted = op_registry_trust(
        conn, kind="capabilities", name=published["name"], version=published["version"], status="local"
    )
    assert trusted["trust_status"] == "local"

    path, source_side = resolve_registry_object(
        repo_root, "capabilities", published["name"], published["version"], conn=conn
    )
    assert source_side == "data"


def test_registry_trust_raises_for_an_unindexed_object(tmp_path):
    _repo_root, conn = make_repo(tmp_path)
    with pytest.raises(CoreOpError):
        op_registry_trust(conn, kind="capabilities", name="missing", version="1.0.0", status="blocked")


def test_registry_reindex_covers_shipped_config_defaults(real_repo_root):
    from awf.db.schema import DDL_STATEMENTS

    conn = get_connection(":memory:")
    for statement in DDL_STATEMENTS:
        conn.execute(statement)

    counts = op_registry_reindex(real_repo_root, conn)

    assert counts["agents"]["config"] >= 3
    assert counts["mcp"]["config"] >= 1


def test_registry_list_never_shows_config_side_model_profiles(tmp_path):
    # Section 9.3: model-profiles has no config/app_registry/ counterpart -
    # ADR-0001's reference examples under config/app_registry/model-profiles/
    # MUST NOT appear in a listing as if they were real, resolvable objects.
    repo_root, conn = make_repo(tmp_path)
    example_dir = repo_root / "config" / "app_registry" / "model-profiles" / "example-demo"
    example_dir.mkdir(parents=True)
    (example_dir / "1.0.0.yaml").write_text("purpose: coding\n")

    assert op_registry_list(repo_root, kind="model-profiles") == []


def test_secret_set_and_list_names_roundtrip(tmp_path):
    repo_root, conn = make_repo(tmp_path)
    key = Fernet.generate_key().decode("ascii")
    (repo_root / ".env").write_text(f"AWF_SECRET_KEY={key}\n")

    op_secret_set(repo_root, conn, name="api-key", value="sekret")

    assert op_secret_list_names(conn) == ["api-key"]


def make_git_repo(tmp_path):
    import subprocess

    repo_root, conn = make_repo(tmp_path)
    subprocess.run(["git", "init", "-q"], cwd=repo_root, check=True)
    subprocess.run(["git", "config", "user.email", "t@e.com"], cwd=repo_root, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=repo_root, check=True)
    (repo_root / "README.md").write_text("x\n")
    subprocess.run(["git", "add", "-A"], cwd=repo_root, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=repo_root, check=True)
    return repo_root, conn


def publish_workflow(repo_root, raw: dict) -> None:
    target = repo_root / "config" / "app_registry" / "workflows" / raw["metadata"]["name"] / f"{raw['metadata']['version']}.yaml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(yaml.safe_dump(raw))


def test_op_run_start_fails_cleanly_for_an_unknown_activity_name(tmp_path):
    # All eight Section 12.2 node types have an executor - this exercises
    # the same "MUST NOT let an exception escape uncaught" safety net via a
    # runtime error instead (an `activity` node naming a function that
    # isn't registered): op_run_start still marks the Run FAILED cleanly
    # rather than propagating the raw exception.
    repo_root, conn = make_git_repo(tmp_path)
    publish_workflow(
        repo_root,
        {
            "apiVersion": "awf/v1",
            "kind": "Workflow",
            "metadata": {"name": "unbuilt-node-demo", "version": "1.0.0", "digest": "sha256:demo"},
            "spec": {
                "inputSchema": {}, "outputSchema": {}, "budgets": {},
                "nodes": [{"id": "a", "type": "activity", "function": "not-a-real-activity", "next": None}],
                "outputs": {},
            },
        },
    )

    result = op_run_start(repo_root, conn, workflow_ref="unbuilt-node-demo@1.0.0", input_data={})

    assert result["status"] == "FAILED"
    assert "error" in result
    row = conn.execute("SELECT status FROM runs WHERE run_id = ?", (result["run_id"],)).fetchone()
    assert row["status"] == "FAILED"


def _single_gate_workflow(name: str, version: str, digest: str) -> dict:
    return {
        "apiVersion": "awf/v1",
        "kind": "Workflow",
        "metadata": {"name": name, "version": version, "digest": digest},
        "spec": {
            "inputSchema": {}, "outputSchema": {}, "budgets": {},
            "nodes": [{"id": "check", "type": "gate", "checkCommand": "true", "next": None}],
            "outputs": {},
        },
    }


def test_op_run_start_with_a_bare_name_resolves_and_pins_the_latest_version(tmp_path):
    repo_root, conn = make_git_repo(tmp_path)
    publish_workflow(repo_root, _single_gate_workflow("pin-demo", "1.0.0", "sha256:demo"))

    result = op_run_start(repo_root, conn, workflow_ref="pin-demo", input_data={})

    assert result["status"] == "SUCCEEDED"
    row = conn.execute("SELECT workflow_ref FROM runs WHERE run_id = ?", (result["run_id"],)).fetchone()
    assert row["workflow_ref"] == "pin-demo@1.0.0"


def test_run_resume_uses_the_pinned_version_not_a_newer_publish(tmp_path):
    # v1.0.0 always succeeds (gate checkCommand "true"); v2.0.0 always fails
    # immediately (an unregistered activity function) - if resume picked up
    # the newer version instead of the pin stored at start time, the run
    # would come back FAILED instead of SUCCEEDED.
    repo_root, conn = make_git_repo(tmp_path)
    publish_workflow(repo_root, _single_gate_workflow("resume-demo", "1.0.0", "sha256:v1"))

    started = op_run_start(repo_root, conn, workflow_ref="resume-demo@1.0.0", input_data={})
    assert started["status"] == "SUCCEEDED"

    publish_workflow(
        repo_root,
        {
            "apiVersion": "awf/v1",
            "kind": "Workflow",
            "metadata": {"name": "resume-demo", "version": "2.0.0", "digest": "sha256:v2"},
            "spec": {
                "inputSchema": {}, "outputSchema": {}, "budgets": {},
                "nodes": [{"id": "a", "type": "activity", "function": "not-a-real-activity", "next": None}],
                "outputs": {},
            },
        },
    )

    # simulate a crash that left the (already-SUCCEEDED) run's row RUNNING,
    # so scan_incomplete_runs picks it back up for this test's purposes.
    conn.execute("UPDATE runs SET status = 'RUNNING' WHERE run_id = ?", (started["run_id"],))
    conn.commit()

    results = op_run_resume(repo_root, conn)

    assert len(results) == 1
    assert results[0]["status"] == "SUCCEEDED"


def test_op_run_start_rejects_input_that_violates_inputschema(tmp_path):
    repo_root, conn = make_git_repo(tmp_path)
    publish_workflow(
        repo_root,
        {
            "apiVersion": "awf/v1",
            "kind": "Workflow",
            "metadata": {"name": "requires-objective", "version": "1.0.0", "digest": "sha256:demo"},
            "spec": {
                "inputSchema": {"type": "object", "required": ["objective"]},
                "outputSchema": {}, "budgets": {},
                "nodes": [{"id": "check", "type": "gate", "checkCommand": "true", "next": None}],
                "outputs": {},
            },
        },
    )

    with pytest.raises(CoreOpError):
        op_run_start(repo_root, conn, workflow_ref="requires-objective@1.0.0", input_data={})

    assert conn.execute("SELECT 1 FROM runs").fetchone() is None  # never created


def test_op_run_start_renders_and_validates_real_outputs(tmp_path):
    repo_root, conn = make_git_repo(tmp_path)
    publish_workflow(
        repo_root,
        {
            "apiVersion": "awf/v1",
            "kind": "Workflow",
            "metadata": {"name": "reports-repairs", "version": "1.0.0", "digest": "sha256:demo"},
            "spec": {
                "inputSchema": {}, "budgets": {},
                "outputSchema": {
                    "type": "object",
                    "properties": {"repairs_used": {"type": "integer"}},
                    "required": ["repairs_used"],
                },
                "nodes": [{"id": "check", "type": "gate", "checkCommand": "true", "next": None}],
                "outputs": {"repairs_used": "{{ engine.repairs_used }}"},
            },
        },
    )

    result = op_run_start(repo_root, conn, workflow_ref="reports-repairs@1.0.0", input_data={})

    assert result["status"] == "SUCCEEDED"
    assert result["outputs"] == {"repairs_used": 0}


def test_op_run_start_fails_run_when_rendered_outputs_violate_outputschema(tmp_path):
    repo_root, conn = make_git_repo(tmp_path)
    publish_workflow(
        repo_root,
        {
            "apiVersion": "awf/v1",
            "kind": "Workflow",
            "metadata": {"name": "unresolvable-output", "version": "1.0.0", "digest": "sha256:demo"},
            "spec": {
                "inputSchema": {}, "budgets": {},
                "outputSchema": {
                    "type": "object",
                    "properties": {"totally_unresolvable": {"type": "integer"}},
                    "required": ["totally_unresolvable"],
                },
                "nodes": [{"id": "check", "type": "gate", "checkCommand": "true", "next": None}],
                "outputs": {"totally_unresolvable": "{{ engine.nonexistent_field }}"},
            },
        },
    )

    result = op_run_start(repo_root, conn, workflow_ref="unresolvable-output@1.0.0", input_data={})

    assert result["status"] == "FAILED"
    row = conn.execute("SELECT status FROM runs WHERE run_id = ?", (result["run_id"],)).fetchone()
    assert row["status"] == "FAILED"


def publish_trivial_gate_workflow(repo_root, *, name: str, version: str = "1.0.0") -> None:
    publish_workflow(
        repo_root,
        {
            "apiVersion": "awf/v1",
            "kind": "Workflow",
            "metadata": {"name": name, "version": version, "digest": "sha256:demo"},
            "spec": {
                "inputSchema": {}, "outputSchema": {}, "budgets": {},
                "nodes": [{"id": "check", "type": "gate", "checkCommand": "true", "next": None}],
                "outputs": {},
            },
        },
    )


def test_op_run_start_runs_a_real_subworkflow_node_to_completion(tmp_path):
    repo_root, conn = make_git_repo(tmp_path)
    publish_trivial_gate_workflow(repo_root, name="child-ok")
    publish_workflow(
        repo_root,
        {
            "apiVersion": "awf/v1",
            "kind": "Workflow",
            "metadata": {"name": "delegates-to-child", "version": "1.0.0", "digest": "sha256:demo"},
            "spec": {
                "inputSchema": {}, "outputSchema": {}, "budgets": {},
                "nodes": [{"id": "delegate", "type": "subworkflow", "workflowRef": "child-ok@1.0.0", "next": None}],
                "outputs": {},
            },
        },
    )

    result = op_run_start(repo_root, conn, workflow_ref="delegates-to-child@1.0.0", input_data={})

    assert result["status"] == "SUCCEEDED"
    # A real, independent child `runs` row was created and completed.
    child_runs = conn.execute(
        "SELECT run_id, status FROM runs WHERE workflow_ref = 'child-ok@1.0.0'"
    ).fetchall()
    assert len(child_runs) == 1
    assert child_runs[0]["status"] == "SUCCEEDED"


def test_op_run_start_runs_a_real_map_node_fanning_out_to_three_children(tmp_path):
    repo_root, conn = make_git_repo(tmp_path)
    publish_trivial_gate_workflow(repo_root, name="child-ok")
    publish_workflow(
        repo_root,
        {
            "apiVersion": "awf/v1",
            "kind": "Workflow",
            "metadata": {"name": "fan-out-demo", "version": "1.0.0", "digest": "sha256:demo"},
            "spec": {
                "inputSchema": {}, "outputSchema": {}, "budgets": {},
                "nodes": [
                    {
                        "id": "fan-out", "type": "map", "workflowRef": "child-ok@1.0.0",
                        "items": ["a", "b", "c"], "maxItems": 5, "maxConcurrency": 2, "next": None,
                    }
                ],
                "outputs": {},
            },
        },
    )

    result = op_run_start(repo_root, conn, workflow_ref="fan-out-demo@1.0.0", input_data={})

    assert result["status"] == "SUCCEEDED"
    child_runs = conn.execute(
        "SELECT run_id, status FROM runs WHERE workflow_ref = 'child-ok@1.0.0'"
    ).fetchall()
    assert len(child_runs) == 3
    assert all(row["status"] == "SUCCEEDED" for row in child_runs)


def test_op_run_start_runs_a_real_loop_node_until_max_iterations(tmp_path):
    # The trivial gate child always passes, so `conditionField: "passed"`
    # never goes false - the loop re-runs a child Run each iteration and
    # waits for operator disposition instead of looping forever or
    # silently succeeding.
    repo_root, conn = make_git_repo(tmp_path)
    publish_trivial_gate_workflow(repo_root, name="child-ok")
    publish_workflow(
        repo_root,
        {
            "apiVersion": "awf/v1",
            "kind": "Workflow",
            "metadata": {"name": "retry-loop-demo", "version": "1.0.0", "digest": "sha256:demo"},
            "spec": {
                "inputSchema": {}, "outputSchema": {}, "budgets": {},
                "nodes": [
                    {
                        "id": "retry", "type": "loop", "workflowRef": "child-ok@1.0.0",
                        "maxIterations": 2, "conditionField": "passed", "next": None,
                    }
                ],
                "outputs": {},
            },
        },
    )

    result = op_run_start(repo_root, conn, workflow_ref="retry-loop-demo@1.0.0", input_data={})

    assert result["status"] == "WAITING_INPUT"
    child_runs = conn.execute(
        "SELECT run_id, status FROM runs WHERE workflow_ref = 'child-ok@1.0.0'"
    ).fetchall()
    assert len(child_runs) == 2
    assert all(row["status"] == "SUCCEEDED" for row in child_runs)
