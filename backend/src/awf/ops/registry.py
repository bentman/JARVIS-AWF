"""registry operation implementations."""

import dataclasses
import hashlib
import json
import shutil
import sqlite3
from pathlib import Path

import yaml

from awf.authoring import workflow as workflow_authoring
from awf.clock import utc_now_rfc3339
from awf.cognition.envelope import PromptEnvelope, PromptSegment
from awf.cognition.render import render_chat
from awf.gateway.client import LLM_COMPLETE_CAPABILITY_REF, complete
from awf.llm.servers import load_servers_file, parse_servers
from awf.ops.shared import CoreOpError
from awf.registry import index as registry_index
from awf.registry.agent_manifest import load_agent_manifest
from awf.registry.capability_record import load_capability_record, parse_capability_record
from awf.registry.hardware_voice_manifest import load_hardware_voice_manifest, parse_hardware_voice_manifest
from awf.registry.kinds import (
    AGENTS,
    CAPABILITIES,
    HARDWARE_VOICE_MANIFESTS,
    LLM_SERVERS,
    MCP,
    MEMORY_PROFILES,
    MODEL_PROFILES,
    PERSONAS,
    SEMANTIC_MEMORIES,
    SKILLS,
    VOICE_PROFILES,
    WORKFLOWS,
    UnknownRegistryKindError,
    version_names,
)
from awf.registry.kinds import by_key as kind_by_key
from awf.registry.kinds import object_path as kind_object_path
from awf.registry.mcp_server import load_mcp_server, parse_mcp_server
from awf.registry.memory_profile import load_memory_profile, parse_memory_profile
from awf.registry.model_profile import load_model_profile, parse_model_profile
from awf.registry.persona import load_persona, parse_persona
from awf.registry.resolve import CONFIG_ROOT, DATA_ROOT, resolve_registry_object
from awf.registry.semantic_memory import load_semantic_memory, parse_semantic_memory
from awf.registry.skill import directory_digest, load_skill
from awf.registry.voice_profile import load_voice_profile, parse_voice_profile
from awf.workflow.definition import load_workflow, parse_workflow

_OBJECT_LOADERS = {
    WORKFLOWS: load_workflow,
    AGENTS: load_agent_manifest,
    CAPABILITIES: load_capability_record,
    MCP: load_mcp_server,
    SKILLS: load_skill,
    VOICE_PROFILES: load_voice_profile,
    MODEL_PROFILES: load_model_profile,
    PERSONAS: load_persona,
    MEMORY_PROFILES: load_memory_profile,
    SEMANTIC_MEMORIES: load_semantic_memory,
    HARDWARE_VOICE_MANIFESTS: load_hardware_voice_manifest,
}

_TRUST_STATUSES = ("local", "trusted", "quarantined", "blocked")


def _load_registry_object(repo_root: Path, registry_kind, path: Path):
    if registry_kind is VOICE_PROFILES:
        return load_voice_profile(repo_root, path)
    if registry_kind is LLM_SERVERS:
        default_server, servers = load_servers_file(path)
        return {"default_server": default_server, "servers": servers}
    return _OBJECT_LOADERS[registry_kind](path)


def _skill_md_path(path: Path) -> Path | None:
    # Skills are directory-shaped (<name>/<version>/SKILL.md, Section 9.3),
    # not a single file like every other kind - `path` may point at either
    # the SKILL.md file itself or its containing version directory.
    if path.name == "SKILL.md":
        return path
    if path.is_dir() and (path / "SKILL.md").is_file():
        return path / "SKILL.md"
    return None


def _kind_from_path_position(path: Path) -> str | None:
    # Both registry roots are `<root>/<kind>/<name>/...` (CONFIG_ROOT ends in
    # "app_registry", DATA_ROOT ends in "registry"), so the segment
    # immediately after either anchor is the kind - unambiguous whenever the
    # path is actually under one of them.
    parts = path.parts
    for anchor in ("app_registry", "registry"):
        if anchor in parts:
            index = parts.index(anchor)
            if index + 1 < len(parts):
                candidate = parts[index + 1]
                try:
                    kind_by_key(candidate)
                    return candidate
                except UnknownRegistryKindError:
                    continue
    return None


def _resolve_validate_publish_kind(path: Path, kind: str | None) -> str:
    if kind is not None:
        return kind
    derived = _kind_from_path_position(path)
    if derived is None:
        raise CoreOpError(f"{path}: cannot determine registry kind from its path; pass kind explicitly")
    return derived


def _workflow_declared_digest(raw: dict) -> str | None:
    metadata = raw.get("metadata")
    if not isinstance(metadata, dict):
        return None
    declared = metadata.get("digest")
    if declared is None:
        return None
    if not isinstance(declared, str) or not declared.startswith("sha256:"):
        raise CoreOpError("metadata.digest must be a sha256:<hex> string")
    return declared


def _workflow_digest_payload(raw: dict) -> bytes:
    normalized = json.loads(json.dumps(raw))
    normalized.setdefault("metadata", {})["digest"] = ""
    return yaml.safe_dump(normalized, sort_keys=False).encode("utf-8")


def _verify_workflow_declared_digest(path: Path, raw: dict) -> None:
    declared = _workflow_declared_digest(raw)
    if declared is None:
        return
    actual = f"sha256:{hashlib.sha256(_workflow_digest_payload(raw)).hexdigest()}"
    if declared != actual:
        raise CoreOpError(f"{path}: metadata.digest mismatch - declared {declared}, actual {actual}")


def op_registry_list(repo_root: Path, *, kind: str, conn: sqlite3.Connection | None = None) -> list[dict]:
    registry_kind = kind_by_key(kind)
    roots = (("data", repo_root / DATA_ROOT), ("config", repo_root / CONFIG_ROOT))
    if registry_kind.data_only:
        # Section 9.3: this kind has no config/app_registry/ counterpart -
        # anything under config/app_registry/<kind>/ (e.g. reference examples,
        # ADR-0001) is never a real, resolvable registry object and MUST NOT
        # be listed as if it were one.
        roots = roots[:1]
    results = []
    for source_name, root in roots:
        kind_dir = root / kind
        if not kind_dir.is_dir():
            continue
        for name_dir in sorted(p for p in kind_dir.iterdir() if p.is_dir()):
            for version in version_names(name_dir, registry_kind):
                row = {"source": source_name, "kind": kind, "name": name_dir.name, "version": version}
                if conn is not None:
                    indexed = registry_index.index_row(conn, kind, name_dir.name, version)
                    row["trust_status"] = indexed["trust_status"] if indexed else None
                    row["digest"] = indexed["digest"] if indexed else None
                results.append(row)
    return results


def op_registry_get(repo_root: Path, conn: sqlite3.Connection, *, kind: str, name: str, version: str) -> dict:
    registry_kind = kind_by_key(kind)
    path, source = resolve_registry_object(repo_root, kind, name, version, conn=conn)

    indexed = registry_index.index_row(conn, kind, name, version)
    digest = indexed["digest"] if indexed else registry_index.compute_digest(path, registry_kind)
    trust_status = indexed["trust_status"] if indexed else None
    obj = dataclasses.asdict(_load_registry_object(repo_root, registry_kind, path))

    return {
        "kind": kind,
        "name": name,
        "version": version,
        "source": source,
        "content": path.read_text(),
        "digest": digest,
        "trust_status": trust_status,
        "object": obj,
    }


def op_skill_invoke(
    repo_root: Path,
    conn: sqlite3.Connection,
    *,
    ref: str,
    input_text: str,
    profile_ref: str = workflow_authoring.DEFAULT_AUTHOR_PROFILE,
) -> dict:
    name, sep, version = ref.partition("@")
    if not sep or not name or not version:
        raise CoreOpError(f"skill ref must be '<name>@<version>', got {ref!r}")
    profile_name, profile_sep, profile_version = profile_ref.partition("@")
    if not profile_sep or not profile_name or not profile_version:
        raise CoreOpError(f"profile ref must be '<name>@<version>', got {profile_ref!r}")
    skill_path, _skill_source = resolve_registry_object(repo_root, "skills", name, version, conn=conn)
    profile_path, _profile_source = resolve_registry_object(
        repo_root, "model-profiles", profile_name, profile_version, conn=conn
    )
    skill = load_skill(skill_path)
    profile = load_model_profile(profile_path)
    envelope = PromptEnvelope(
        segments=(
            PromptSegment(
                "application",
                "instruction",
                True,
                "Apply the referenced AWF Skill to the operator input and return the direct result.",
            ),
            PromptSegment("skill", "instruction", False, skill.body),
            PromptSegment("user", "input", False, input_text),
        )
    )
    response_text = complete(
        profile,
        render_chat(envelope).messages,
        conn=conn,
        actor="skill.invoke",
        repo_root=repo_root,
        agent_allowlist=[LLM_COMPLETE_CAPABILITY_REF],
    )
    return {
        "kind": "skills",
        "ref": skill.ref,
        "profile_ref": profile.ref,
        "digest": directory_digest(skill_path.parent),
        "response_text": response_text,
    }


def op_registry_validate(path: Path, *, kind: str | None = None) -> dict:
    registry_kind = kind_by_key(_resolve_validate_publish_kind(path, kind))

    if registry_kind is SKILLS:
        skill_md_path = _skill_md_path(path)
        if skill_md_path is None:
            raise CoreOpError(f"{path}: not a Skill (expected a SKILL.md file or its containing directory)")
        skill = load_skill(skill_md_path)
        return {"kind": "Skill", "ref": skill.ref, "valid": True}

    if registry_kind is AGENTS:
        manifest = load_agent_manifest(path)
        return {"kind": "AgentManifest", "ref": manifest.ref, "valid": True}

    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict):
        raise CoreOpError(f"{path}: must be a YAML mapping")

    if registry_kind is WORKFLOWS:
        workflow = parse_workflow(raw)
        _verify_workflow_declared_digest(path, raw)
        return {"kind": "Workflow", "ref": workflow.ref, "valid": True}
    if registry_kind is CAPABILITIES:
        record = parse_capability_record(raw)
        return {"kind": "CapabilityRecord", "ref": record.ref, "valid": True}
    if registry_kind is MCP:
        server = parse_mcp_server(raw)
        return {"kind": "McpServer", "ref": server.ref, "valid": True}
    if registry_kind is MODEL_PROFILES:
        profile = parse_model_profile(raw)
        return {"kind": "ModelProfile", "ref": profile.ref, "valid": True}
    if registry_kind is PERSONAS:
        persona = parse_persona(raw)
        return {"kind": "Persona", "ref": persona.ref, "valid": True}
    if registry_kind is MEMORY_PROFILES:
        profile = parse_memory_profile(raw)
        return {"kind": "MemoryProfile", "ref": profile.ref, "valid": True}
    if registry_kind is SEMANTIC_MEMORIES:
        memory = parse_semantic_memory(raw)
        return {"kind": "SemanticMemory", "ref": memory.ref, "valid": True}
    if registry_kind is VOICE_PROFILES:
        profile = parse_voice_profile(raw)
        return {"kind": "VoiceProfile", "ref": profile.ref, "valid": True}
    if registry_kind is HARDWARE_VOICE_MANIFESTS:
        manifest = parse_hardware_voice_manifest(raw)
        return {"kind": "HardwareVoiceManifest", "ref": f"{manifest.name}@{manifest.version}", "valid": True}
    if registry_kind is LLM_SERVERS:
        default_server, servers = parse_servers(raw)
        return {
            "kind": "LlmServers",
            "ref": f"{raw['metadata']['name']}@{raw['metadata']['version']}",
            "default_server": default_server,
            "server_count": len(servers),
            "valid": True,
        }
    raise CoreOpError(f"{path}: registry validate does not support kind '{registry_kind.key}'")


def op_registry_publish(repo_root: Path, conn: sqlite3.Connection, *, path: Path, kind: str) -> dict:
    registry_kind = kind_by_key(kind)

    if registry_kind is SKILLS:
        skill_md_path = _skill_md_path(path)
        if skill_md_path is None:
            raise CoreOpError(f"{path}: not a Skill (expected a SKILL.md file or its containing directory)")
        skill = load_skill(skill_md_path)
        skill_dir = skill_md_path.parent
        digest = directory_digest(skill_dir)
        target_dir = kind_object_path(repo_root / DATA_ROOT / "skills" / skill.name, SKILLS, skill.version).parent
        if target_dir.is_dir():
            shutil.rmtree(target_dir)
        target_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(skill_dir, target_dir)

        conn.execute(
            "INSERT INTO registry_index (kind, name, version, digest, source, path, trust_status, indexed_at) "
            "VALUES ('skills', ?, ?, ?, 'data', ?, 'local', ?) "
            "ON CONFLICT(kind, name, version) DO UPDATE SET "
            "digest=excluded.digest, path=excluded.path, indexed_at=excluded.indexed_at",
            (skill.name, skill.version, digest, target_dir.relative_to(repo_root).as_posix(), utc_now_rfc3339()),
        )
        conn.commit()
        return {
            "kind": "skills",
            "name": skill.name,
            "version": skill.version,
            "digest": digest,
            "path": str(target_dir),
        }

    if registry_kind is AGENTS:
        manifest = load_agent_manifest(path)
        name, version = manifest.name, manifest.version
    else:
        raw = yaml.safe_load(path.read_text())
        if not isinstance(raw, dict):
            raise CoreOpError(f"{path}: must be a YAML mapping")

        if registry_kind is WORKFLOWS:
            workflow = parse_workflow(raw)
            _verify_workflow_declared_digest(path, raw)
            name, version = workflow.metadata.name, workflow.metadata.version
        elif registry_kind is CAPABILITIES:
            record = parse_capability_record(raw)
            name, version = record.identity.name, record.identity.version
        elif registry_kind is MCP:
            server = parse_mcp_server(raw)
            name, version = server.name, server.version
        elif registry_kind is MODEL_PROFILES:
            profile = parse_model_profile(raw)
            name, version = profile.name, profile.version
        elif registry_kind is PERSONAS:
            persona = parse_persona(raw)
            name, version = persona.name, persona.version
        elif registry_kind is MEMORY_PROFILES:
            profile = parse_memory_profile(raw)
            name, version = profile.metadata.name, profile.metadata.version
        elif registry_kind is SEMANTIC_MEMORIES:
            memory = parse_semantic_memory(raw)
            name, version = memory.metadata.name, memory.metadata.version
        elif registry_kind is VOICE_PROFILES:
            profile = parse_voice_profile(raw)
            persona_name, sep, persona_version = profile.persona_ref.partition("@")
            if not sep or not persona_name or not persona_version:
                raise CoreOpError(
                    f"{path}: voice profile persona_ref must be '<name>@<version>', got {profile.persona_ref!r}"
                )
            resolve_registry_object(repo_root, "personas", persona_name, persona_version, conn=conn)
            name, version = profile.name, profile.version
        elif registry_kind is HARDWARE_VOICE_MANIFESTS:
            manifest = parse_hardware_voice_manifest(raw)
            name, version = manifest.name, manifest.version
        elif registry_kind is LLM_SERVERS:
            parse_servers(raw)
            name, version = raw["metadata"]["name"], raw["metadata"]["version"]
        else:
            raise CoreOpError(f"{path}: registry publish does not support kind '{kind}'")

    payload = path.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    target_dir = repo_root / DATA_ROOT / kind / name
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = kind_object_path(target_dir, registry_kind, version)
    target_path.write_bytes(payload)

    conn.execute(
        "INSERT INTO registry_index (kind, name, version, digest, source, path, trust_status, indexed_at) "
        "VALUES (?, ?, ?, ?, 'data', ?, 'local', ?) "
        "ON CONFLICT(kind, name, version) DO UPDATE SET "
        "digest=excluded.digest, path=excluded.path, indexed_at=excluded.indexed_at",
        (kind, name, version, digest, target_path.relative_to(repo_root).as_posix(), utc_now_rfc3339()),
    )
    conn.commit()
    return {"kind": kind, "name": name, "version": version, "digest": digest, "path": str(target_path)}


def op_registry_reindex(repo_root: Path, conn: sqlite3.Connection) -> dict:
    return registry_index.reindex(repo_root, conn)


def op_registry_trust(conn: sqlite3.Connection, *, kind: str, name: str, version: str, status: str) -> dict:
    kind_by_key(kind)  # validates the kind, raises UnknownRegistryKindError otherwise
    if status not in _TRUST_STATUSES:
        raise CoreOpError(f"status must be one of {_TRUST_STATUSES}, got {status!r}")
    row = registry_index.set_trust_status(conn, kind, name, version, status)
    if row is None:
        raise CoreOpError(f"{kind}/{name}@{version} is not indexed; run 'awf registry reindex' or publish it first")
    return row


def op_registry_retire(conn: sqlite3.Connection, *, kind: str, name: str, version: str) -> dict:
    return op_registry_trust(conn, kind=kind, name=name, version=version, status="blocked")


__all__ = (
    "op_registry_get",
    "op_registry_list",
    "op_registry_publish",
    "op_registry_reindex",
    "op_registry_retire",
    "op_registry_trust",
    "op_registry_validate",
    "op_skill_invoke",
)
