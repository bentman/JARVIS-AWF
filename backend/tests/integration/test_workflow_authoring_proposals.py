import json

import pytest
import yaml

from awf.authoring import workflow as workflow_authoring
from awf.cli.core_ops import (
    CoreOpError,
    op_proposal_publish,
    op_proposal_reject,
    op_proposal_update,
    op_workflow_author_draft,
)
from awf.db.bootstrap import init_db
from awf.db.connection import get_connection
from awf.registry.resolve import RegistryObjectNotFoundError, resolve_registry_object


def make_repo(tmp_path):
    repo_root = tmp_path / "repo"
    (repo_root / "data" / "awf_db").mkdir(parents=True)
    (repo_root / "data" / "registry" / "model-profiles" / "resident-mind").mkdir(parents=True)
    db_path = repo_root / "data" / "awf_db" / "awf.db"
    init_db(db_path)
    profile = {
        "name": "resident-mind",
        "version": "1.0.0",
        "purpose": "general-reasoning",
        "privacy": {"maximum_data_class": "internal", "local_only": True},
        "candidates": [
            {
                "provider": "openai",
                "model": "local-model",
                "priority": 1,
                "enabled": True,
                "api_base": "http://127.0.0.1:8080/v1",
            }
        ],
        "fallback": {"mode": "none", "allow_quality_degrade": False},
        "limits": {
            "max_input_tokens_per_call": 8192,
            "max_output_tokens_per_call": 1024,
            "max_cost_usd_per_call": 0.0,
        },
    }
    (repo_root / "data" / "registry" / "model-profiles" / "resident-mind" / "1.0.0.yaml").write_text(
        yaml.safe_dump(profile, sort_keys=False),
        encoding="utf-8",
    )
    return repo_root, get_connection(db_path)


def authoring_payload(name: str = "demo-authored", version: str = "0.1.0") -> dict:
    return {
        "summary": "A simple generated workflow.",
        "workflow": {
            "apiVersion": "awf/v1",
            "kind": "Workflow",
            "metadata": {"name": name, "version": version, "digest": "sha256:model"},
            "spec": {
                "inputSchema": {},
                "outputSchema": {},
                "budgets": {},
                "nodes": [{"id": "check", "type": "gate", "checkCommand": "true", "next": None}],
                "outputs": {},
            },
        },
    }


def test_author_workflow_draft_stores_valid_proposal(monkeypatch, tmp_path):
    repo_root, conn = make_repo(tmp_path)

    def fake_complete_structured(*args, **kwargs):
        assert kwargs["schema_name"] == "awf_workflow_proposal"
        return authoring_payload()

    monkeypatch.setattr(workflow_authoring, "complete_structured", fake_complete_structured)

    proposal = op_workflow_author_draft(repo_root, conn, objective="make a demo")

    assert proposal["kind"] == "workflows"
    assert proposal["status"] == "draft"
    assert proposal["name"] == "demo-authored"
    assert proposal["draft_digest"]
    assert "apiVersion: awf/v1" in proposal["content"]
    assert len(proposal["events"]) == 1
    assert proposal["events"][0]["event_type"] == "created"


def test_default_author_profile_resolves_from_shipped_config_profile(repo_root):
    profile = workflow_authoring._load_profile(repo_root, workflow_authoring.DEFAULT_AUTHOR_PROFILE)

    assert profile.ref == workflow_authoring.DEFAULT_AUTHOR_PROFILE
    assert profile.privacy.local_only is True


def test_update_then_publish_requires_current_digest_and_uses_registry(monkeypatch, tmp_path):
    repo_root, conn = make_repo(tmp_path)
    monkeypatch.setattr(workflow_authoring, "complete_structured", lambda *args, **kwargs: authoring_payload())
    proposal = op_workflow_author_draft(repo_root, conn, objective="make a demo")

    edited = yaml.safe_load(proposal["content"])
    edited["metadata"]["version"] = "0.2.0"
    edited["spec"]["nodes"][0]["checkCommand"] = "python -V"
    updated = op_proposal_update(repo_root, conn, proposal_id=proposal["proposal_id"], content=yaml.safe_dump(edited))

    with pytest.raises(CoreOpError, match="draft digest mismatch"):
        op_proposal_publish(repo_root, conn, proposal_id=proposal["proposal_id"], digest=proposal["draft_digest"])

    published = op_proposal_publish(repo_root, conn, proposal_id=proposal["proposal_id"], digest=updated["draft_digest"])

    assert published["proposal"]["status"] == "published"
    assert published["published"]["kind"] == "workflows"
    assert published["verification"]["status"] == "passed"
    path, source = resolve_registry_object(repo_root, "workflows", "demo-authored", "0.2.0", conn=conn)
    assert source == "data"
    assert path.read_text(encoding="utf-8") == updated["content"]


def test_publish_rehashes_draft_file_before_registry_write(monkeypatch, tmp_path):
    repo_root, conn = make_repo(tmp_path)
    monkeypatch.setattr(workflow_authoring, "complete_structured", lambda *args, **kwargs: authoring_payload())
    proposal = op_workflow_author_draft(repo_root, conn, objective="make a demo")
    draft_path = repo_root / proposal["draft_path"]
    draft_path.write_text(draft_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    with pytest.raises(CoreOpError, match="draft file digest mismatch"):
        op_proposal_publish(repo_root, conn, proposal_id=proposal["proposal_id"], digest=proposal["draft_digest"])

    with pytest.raises(RegistryObjectNotFoundError):
        resolve_registry_object(repo_root, "workflows", "demo-authored", "0.1.0", conn=conn)


def test_publish_runs_deterministic_verifier_before_registry_write(monkeypatch, tmp_path):
    repo_root, conn = make_repo(tmp_path)
    payload = authoring_payload()
    payload["workflow"]["spec"]["nodes"] = [
        {"id": "fetch", "type": "activity", "function": "missing_capability", "args": {}, "next": None}
    ]
    monkeypatch.setattr(workflow_authoring, "complete_structured", lambda *args, **kwargs: payload)
    proposal = op_workflow_author_draft(repo_root, conn, objective="make a demo")

    with pytest.raises(CoreOpError, match="missing_capability"):
        op_proposal_publish(repo_root, conn, proposal_id=proposal["proposal_id"], digest=proposal["draft_digest"])

    assert conn.execute("SELECT 1 FROM registry_proposal_events WHERE event_type = 'published'").fetchone() is None


def test_rejected_proposal_cannot_publish(monkeypatch, tmp_path):
    repo_root, conn = make_repo(tmp_path)
    monkeypatch.setattr(workflow_authoring, "complete_structured", lambda *args, **kwargs: authoring_payload())
    proposal = op_workflow_author_draft(repo_root, conn, objective="make a demo")

    rejected = op_proposal_reject(repo_root, conn, proposal_id=proposal["proposal_id"], reason="not useful")

    assert rejected["status"] == "rejected"
    assert rejected["rejection_reason"] == "not useful"
    with pytest.raises(CoreOpError, match="not draft"):
        op_proposal_publish(repo_root, conn, proposal_id=proposal["proposal_id"], digest=proposal["draft_digest"])


def test_proposal_event_payloads_are_json(monkeypatch, tmp_path):
    repo_root, conn = make_repo(tmp_path)
    monkeypatch.setattr(workflow_authoring, "complete_structured", lambda *args, **kwargs: authoring_payload())
    proposal = op_workflow_author_draft(repo_root, conn, objective="make a demo")

    payloads = [
        json.loads(row["payload_json"])
        for row in conn.execute(
            "SELECT payload_json FROM registry_proposal_events WHERE proposal_id = ?",
            (proposal["proposal_id"],),
        ).fetchall()
    ]

    assert payloads[0]["draft_digest"] == proposal["draft_digest"]
