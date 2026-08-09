import hashlib

import yaml
from backend.tests.support import make_awf_repo

from awf.cli.core_ops import (
    op_memory_block,
    op_memory_propose,
    op_memory_publish,
    op_memory_search,
    op_registry_get,
    op_registry_publish,
    op_registry_validate,
)


def memory_profile_yaml() -> str:
    return yaml.safe_dump(
        {
            "apiVersion": "awf/v1",
            "kind": "MemoryProfile",
            "metadata": {"name": "default", "version": "1.0.0", "digest": "sha256:test"},
            "spec": {
                "enabled": True,
                "maximum_data_class": "internal",
                "retrieval": {
                    "maxItems": 10,
                    "maxTokens": 2000,
                    "includeEpisodic": True,
                    "includeSemantic": True,
                    "minConfidence": 0.0,
                },
                "retention": {"activeSessionTtlHours": 24, "requireExplicitSemanticPublish": True},
                "embedding": {"enabled": False, "modelProfileRef": None, "version": "none"},
            },
        }
    )


def memory_yaml(name: str = "operator-prefers-targeted-tests", value: str = "targeted tests") -> str:
    return yaml.safe_dump(
        {
            "apiVersion": "awf/v1",
            "kind": "SemanticMemory",
            "metadata": {"name": name, "version": "1.0.0", "digest": "sha256:test"},
            "spec": {
                "subject": "operator",
                "predicate": "prefers",
                "value": value,
                "memoryType": "preference",
                "scope": "repo",
                "confidence": 0.9,
                "data_classification": "internal",
                "provenance": {
                    "sourceType": "operator",
                    "sourceRef": "manual-note",
                    "artifactId": None,
                    "runId": None,
                    "eventId": None,
                    "observedAt": "2026-08-09T00:00:00Z",
                },
                "validity": {"validFrom": "2026-08-09T00:00:00Z", "validUntil": None},
                "correction": {"supersedes": None, "correctedBy": None, "correctionReason": None},
                "pinned": False,
                "enabled": True,
            },
        }
    )


def seed_profile(repo_root):
    path = repo_root / "config" / "app_registry" / "memory-profiles" / "default" / "1.0.0.yaml"
    path.parent.mkdir(parents=True)
    path.write_text(memory_profile_yaml(), encoding="utf-8")
    return path


def test_memory_profile_and_semantic_memory_validate_publish_get_and_search(tmp_path):
    repo_root, conn = make_awf_repo(tmp_path)
    profile_path = seed_profile(repo_root)
    source = tmp_path / "memory.yaml"
    source.write_text(memory_yaml(), encoding="utf-8")

    assert op_registry_validate(profile_path, kind="memory-profiles")["kind"] == "MemoryProfile"
    assert op_registry_validate(source, kind="semantic-memories")["kind"] == "SemanticMemory"
    published = op_registry_publish(repo_root, conn, path=source, kind="semantic-memories")

    fetched = op_registry_get(repo_root, conn, kind="semantic-memories", name=published["name"], version="1.0.0")
    assert fetched["object"]["subject"] == "operator"
    result = op_memory_search(repo_root, conn, query="targeted", profile_ref="default@1.0.0")
    assert result["semantic"][0]["ref"] == "operator-prefers-targeted-tests@1.0.0"

    blocked = op_memory_block(conn, ref="operator-prefers-targeted-tests@1.0.0")
    assert blocked["trust_status"] == "blocked"
    assert op_memory_search(repo_root, conn, query="targeted", profile_ref="default@1.0.0")["semantic"] == []


def test_memory_proposal_publishes_through_digest_gate(tmp_path):
    repo_root, conn = make_awf_repo(tmp_path)
    seed_profile(repo_root)
    source = tmp_path / "memory.yaml"
    source.write_text(memory_yaml(name="operator-prefers-small-scope", value="small scope"), encoding="utf-8")

    proposal = op_memory_propose(repo_root, conn, path=source, summary="remember test preference")

    digest = hashlib.sha256((repo_root / proposal["draft_path"]).read_bytes()).hexdigest()
    assert proposal["kind"] == "semantic-memories"
    published = op_memory_publish(repo_root, conn, proposal_id=proposal["proposal_id"], digest=digest)
    assert published["proposal"]["status"] == "published"
    assert published["published"]["kind"] == "semantic-memories"
