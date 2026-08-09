"""Runs an Agent node as a durable Step (Section 12.2 node type, Section 10).

The worktree is committed only after the Step's `SUCCEEDED` status is
persisted to `steps` - never before, and never if the adapter didn't
complete. When `capability` is supplied, the Capability Guard (Section 9.2)
authorizes the action before the adapter runs; a DENY/APPROVAL_REQUIRED
decision fails the Step with `POLICY_DENIED` rather than proceeding.

`voice` (an Agent Manifest's `voice` ref, ADR-0002), when given, is folded
into the Step's own persisted output - not just the in-memory return value -
so a later `awf status`/`op_run_status` query can actually see which voice
a Step's output should be spoken in.

`mcp_refs` (an Agent Manifest's `mcp` list, ADR-0002/ADR-0003), when given,
resolves each `name@version` against the registry, skips anything
`quarantined`/`blocked` in `registry_index`, renders the surviving set into
the invoking adapter's own config format (`awf.mcp.render`), writes it into
the Run's worktree, records one `mcp_rendered` event, and merges the
render's resolved-secret environment overlay into the adapter subprocess's
environment via `invocation.constraints` - AWF never runs an MCP client of
its own; the adapter connects. An empty or absent `mcp_refs` renders
nothing and the adapter runs exactly as it would have.

`skill_refs`/`instructions` (an Agent Manifest's `skills` list and Markdown
body, ADR-0004): each resolved, trust-passing Skill's `SKILL.md` body is
folded into the objective text, after `instructions` and before the node's
own per-invocation objective - AWF is the one applying the procedure, by
default the adapter never sees a discoverable skill directory. A ref
explicitly marked `share: true` additionally copies the skill's directory
into the worktree's `.claude/skills/`/`.agents/skills/` (read natively by
Claude Code, Copilot CLI, and Antigravity) and, for Codex specifically,
into a scratch `$CODEX_HOME` (mirroring the MCP scratch-home mechanism
above) since Codex only discovers skills under its own home directory.

`model_profile_ref` (an Agent Manifest's `model_profile` field, ADR-0005),
when given, resolves the named Model Profile, picks its winning candidate
(the same `enabled_candidates_by_priority()` + fallback posture the Model
Gateway itself uses), and merges the candidate's `model`/`provider` into
`invocation.constraints` as `model_override`/`model_override_provider` -
each adapter appends its own real `--model`/`-m` flag from these, the same
shape `mcp_extra_args` already uses. This is a separate path from the
Model Gateway: it picks what model an adapter's own agentic loop runs as,
not what AWF itself calls directly. A profile with no enabled candidates
fails the Step before the adapter runs, the same posture as an empty
Capability Guard allowlist.
"""

import dataclasses
import hashlib
import json
import shutil
import sqlite3
from collections.abc import Callable
from pathlib import Path

from awf.adapters.base import AgentInvocation, AgentResult, AgentStatus
from awf.cognition.envelope import PromptEnvelope, PromptSegment
from awf.cognition.render import render_flat
from awf.engine.executor import StepFailure, run_step
from awf.envfile import get_env_value
from awf.events.writer import write_event
from awf.guard.capability_guard import Decision, authorize
from awf.isolation.scratch import scratch_path
from awf.isolation.worktree import commit_all_changes
from awf.mcp.render import RENDERERS
from awf.paths import env_path
from awf.registry.agent_manifest import SkillRef
from awf.registry.capability_record import CapabilityRecord, load_capability_record
from awf.registry.index import latest_version
from awf.registry.mcp_server import load_mcp_server
from awf.registry.model_profile import load_model_profile
from awf.registry.persona import CompiledPersona, compile_persona, load_persona
from awf.registry.resolve import resolve_registry_object
from awf.registry.skill import Skill, directory_digest, load_skill
from awf.secrets.store import get_secret

AdapterFn = Callable[[AgentInvocation], AgentResult]

AGENT_STATUS_FAILURE_CLASSES = {
    AgentStatus.FAILED: "TOOL_ERROR",
    AgentStatus.LIMIT_EXCEEDED: "TIMEOUT",
}


class AgentStepError(StepFailure):
    pass


def _is_trusted(conn: sqlite3.Connection, kind: str, name: str, version: str, source: str) -> bool:
    if source != "data":
        # config/app_registry/ objects carry no trust field - inclusion in
        # the repository is the review (Section 9.3).
        return True
    row = conn.execute(
        "SELECT trust_status FROM registry_index WHERE kind = ? AND name = ? AND version = ?",
        (kind, name, version),
    ).fetchone()
    if row is None:
        return True
    return row["trust_status"] not in ("quarantined", "blocked")


def _resolve_mcp_servers(
    conn: sqlite3.Connection, repo_root: Path, mcp_refs: list[str], capability_refs: list[str] | None
):
    """Returns (servers, refs_with_digest) for the refs that pass the trust gate."""
    servers = []
    refs_with_digest = []
    allowed_capability_refs = set(capability_refs or [])
    for ref in mcp_refs:
        name, _, version = ref.partition("@")
        path, source = resolve_registry_object(repo_root, "mcp", name, version)
        if not _is_trusted(conn, "mcp", name, version, source):
            continue
        server = load_mcp_server(path)
        tools, capability_records = _allowed_mcp_tools(repo_root, server.name, server.tools, allowed_capability_refs)
        if server.tools and tuple(tools) != server.tools:
            continue
        servers.append(dataclasses.replace(server, tools=tuple(tools)))
        refs_with_digest.append(
            {
                "ref": ref,
                "digest": hashlib.sha256(path.read_bytes()).hexdigest(),
                "tools": tools,
                "capabilities": [record.ref for record in capability_records],
            }
        )
    return servers, refs_with_digest


def _allowed_mcp_tools(repo_root: Path, provider: str, tools: tuple[str, ...], allowed_refs: set[str]):
    allowed_tools = []
    capability_records = []
    for tool in tools:
        try:
            version = latest_version(repo_root, "capabilities", tool)
            cap_path, _source = resolve_registry_object(repo_root, "capabilities", tool, version)
            capability = load_capability_record(cap_path)
        except Exception:
            continue
        if capability.ref not in allowed_refs:
            continue
        if capability.identity.type != "mcp-tool" or capability.identity.provider != provider:
            continue
        allowed_tools.append(tool)
        capability_records.append(capability)
    return allowed_tools, capability_records


def _resolve_secrets(conn: sqlite3.Connection, repo_root: Path, servers) -> dict[str, str]:
    secret_names = set()
    for server in servers:
        secret_names.update(server.env_secrets.values())
        secret_names.update(server.header_secrets.values())
    if not secret_names:
        return {}
    secret_key = get_env_value(env_path(repo_root), "AWF_SECRET_KEY").encode("ascii")
    return {name: get_secret(conn, name, secret_key) for name in secret_names}


def _apply_mcp(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    step_id: str,
    worktree_path: Path,
    repo_root: Path | None,
    mcp_refs: list[str],
    capability_refs: list[str] | None,
    actor: str,
    invocation: AgentInvocation,
) -> AgentInvocation:
    if not mcp_refs or repo_root is None:
        return invocation

    servers, refs_with_digest = _resolve_mcp_servers(conn, repo_root, mcp_refs, capability_refs)
    if not servers:
        return invocation

    resolved_secrets = _resolve_secrets(conn, repo_root, servers)
    renderer = RENDERERS.get(actor)
    if renderer is None:
        return invocation
    rendered = renderer(servers, resolved_secrets)

    if rendered.relative_path is not None:
        target = worktree_path / rendered.relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(rendered.contents)

    scratch_home = None
    if rendered.home_relative_files or rendered.home_copy_paths:
        # A throwaway $HOME for this Run only - never the operator's real
        # home directory, never anything that outlives the Run (Section
        # 18 #3's spirit, applied to an adapter with no per-invocation MCP
        # flag of its own). The "scratch_home" directory is generic and shared
        # by every home-scoped adapter (Antigravity, Cline, ...); the trailing
        # `<actor>` segment keeps each adapter's isolated home separate.
        scratch_home = scratch_path(repo_root, run_id) / "scratch_home" / actor
        for relative, contents in rendered.home_relative_files.items():
            target = scratch_home / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(contents)
        for relative in rendered.home_copy_paths:
            source = Path.home() / relative
            if source.is_file():
                target = scratch_home / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(source.read_bytes())

    write_event(
        conn,
        run_id=run_id,
        step_id=step_id,
        new_status="mcp_rendered",
        actor=actor,
        reason_code="mcp_rendered",
        payload_json=json.dumps({"servers": refs_with_digest}),
    )

    if not rendered.extra_args and not rendered.env_overlay and scratch_home is None:
        return invocation

    constraints = dict(invocation.constraints)
    if rendered.extra_args:
        constraints["mcp_extra_args"] = list(rendered.extra_args)
    env_overlay = dict(rendered.env_overlay)
    if scratch_home is not None:
        env_overlay["HOME"] = str(scratch_home)
    if env_overlay:
        constraints["mcp_env_overlay"] = env_overlay
    return AgentInvocation(
        objective=invocation.objective,
        inputs=invocation.inputs,
        workspace_root=invocation.workspace_root,
        capabilities=invocation.capabilities,
        skills=invocation.skills,
        constraints=constraints,
        completion_contract=invocation.completion_contract,
        trace_context=invocation.trace_context,
    )


# Read natively by Claude Code and GitHub Copilot CLI (`.claude/skills/`)
# and by Antigravity (`.agents/skills/`), given flags each adapter already
# passes on every invocation (ADR-0004) - no adapter-specific flag needed
# for either path.
SKILL_SHARE_RELATIVE_DIRS = (".claude/skills", ".agents/skills")


def _resolve_skills(conn: sqlite3.Connection, repo_root: Path, skill_refs: list[SkillRef]):
    """Returns (skill_ref, skill, digest, skill_dir) for refs that pass the trust gate."""
    resolved = []
    for skill_ref in skill_refs:
        name, _, version = skill_ref.ref.partition("@")
        path, source = resolve_registry_object(repo_root, "skills", name, version)
        if not _is_trusted(conn, "skills", name, version, source):
            continue
        skill = load_skill(path)
        skill_dir = path.parent
        resolved.append((skill_ref, skill, directory_digest(skill_dir), skill_dir))
    return resolved


def _share_skill(worktree_path: Path, skill: Skill, skill_dir: Path) -> None:
    for relative_dir in SKILL_SHARE_RELATIVE_DIRS:
        target = worktree_path / relative_dir / skill.name
        if target.is_dir():
            shutil.rmtree(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(skill_dir, target)


def _codex_scratch_home_for_skills(
    repo_root: Path, run_id: str, actor: str, worktree_path: Path, skills: list[Skill]
) -> Path:
    # Codex only discovers skills under its own `$CODEX_HOME/skills/` - the
    # same scratch-home shape ADR-0003 established for Antigravity's MCP
    # config, never the operator's real `~/.codex/`. Symlinks to the copy
    # already written into the worktree by `_share_skill` rather than a
    # second copy on disk.
    home_dir = scratch_path(repo_root, run_id) / "codex_home" / actor
    (home_dir / "skills").mkdir(parents=True, exist_ok=True)
    for skill in skills:
        link_path = home_dir / "skills" / skill.name
        if not link_path.exists():
            link_path.symlink_to(worktree_path / ".claude" / "skills" / skill.name)
    real_auth = Path.home() / ".codex" / "auth.json"
    if real_auth.is_file():
        (home_dir / "auth.json").write_bytes(real_auth.read_bytes())
    return home_dir


def _apply_skills(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    step_id: str,
    worktree_path: Path,
    repo_root: Path | None,
    skill_refs: list[SkillRef],
    persona: CompiledPersona | None,
    actor: str,
    instructions: str,
    invocation: AgentInvocation,
) -> AgentInvocation:
    resolved = _resolve_skills(conn, repo_root, skill_refs) if (repo_root is not None and skill_refs) else []

    segments = []
    if instructions.strip():
        segments.append(PromptSegment("application", "instruction", True, instructions))
    if persona is not None and persona.system_text.strip():
        segments.append(PromptSegment("persona", "style", True, persona.system_text))
    segments.extend(
        PromptSegment("skill", "instruction", False, skill.body)
        for _ref, skill, _digest, _dir in resolved
        if skill.body.strip()
    )
    if invocation.objective.strip():
        segments.append(PromptSegment("user", "input", False, invocation.objective))
    envelope = PromptEnvelope(
        segments=tuple(segments),
        example_messages=persona.example_messages if persona is not None else (),
        generation=persona.generation if persona is not None else {},
    )
    objective = render_flat(envelope)

    constraints = dict(invocation.constraints)
    resolved_skill_refs: tuple[str, ...] = invocation.skills

    if resolved:
        shared = [(ref, skill, skill_dir) for ref, skill, _digest, skill_dir in resolved if ref.share]
        for _ref, skill, skill_dir in shared:
            _share_skill(worktree_path, skill, skill_dir)

        if shared and actor == "codex":
            home_dir = _codex_scratch_home_for_skills(
                repo_root, run_id, actor, worktree_path, [skill for _r, skill, _d in shared]
            )
            env_overlay = dict(constraints.get("skill_env_overlay", {}))
            env_overlay["CODEX_HOME"] = str(home_dir)
            constraints["skill_env_overlay"] = env_overlay

        write_event(
            conn,
            run_id=run_id,
            step_id=step_id,
            new_status="skills_resolved",
            actor=actor,
            reason_code="skills_resolved",
            payload_json=json.dumps(
                {
                    "skills": [
                        {"ref": ref.ref, "digest": digest, "shared": ref.share} for ref, _s, digest, _d in resolved
                    ]
                }
            ),
        )
        resolved_skill_refs = tuple(ref.ref for ref, _skill, _digest, _dir in resolved)

    if objective == invocation.objective and not resolved:
        return invocation

    return AgentInvocation(
        objective=objective,
        inputs=invocation.inputs,
        workspace_root=invocation.workspace_root,
        capabilities=invocation.capabilities,
        skills=resolved_skill_refs,
        constraints=constraints,
        completion_contract=invocation.completion_contract,
        trace_context=invocation.trace_context,
    )


def _apply_model_profile(
    *,
    repo_root: Path | None,
    model_profile_ref: str | None,
    invocation: AgentInvocation,
) -> AgentInvocation:
    if not model_profile_ref or repo_root is None:
        return invocation

    name, _, version = model_profile_ref.partition("@")
    path, _source = resolve_registry_object(repo_root, "model-profiles", name, version)
    profile = load_model_profile(path)
    candidates = profile.enabled_candidates_by_priority()
    if not candidates:
        raise AgentStepError(
            f"model profile '{model_profile_ref}' has no enabled candidates",
            failure_class="INVALID_INPUT",
        )
    winner = candidates[0]

    constraints = dict(invocation.constraints)
    constraints["model_override"] = winner.model
    constraints["model_override_provider"] = winner.provider
    return AgentInvocation(
        objective=invocation.objective,
        inputs=invocation.inputs,
        workspace_root=invocation.workspace_root,
        capabilities=invocation.capabilities,
        skills=invocation.skills,
        constraints=constraints,
        completion_contract=invocation.completion_contract,
        trace_context=invocation.trace_context,
    )


def _resolve_persona(repo_root: Path | None, persona_ref: str | None) -> CompiledPersona | None:
    if not persona_ref or repo_root is None:
        return None
    name, sep, version = persona_ref.partition("@")
    if not sep or not name or not version:
        raise AgentStepError(
            f"persona ref must be '<name>@<version>', got {persona_ref!r}",
            failure_class="INVALID_INPUT",
        )
    path, _source = resolve_registry_object(repo_root, "personas", name, version)
    return compile_persona(load_persona(path))


def run_agent_step(
    conn: sqlite3.Connection,
    *,
    step_id: str,
    run_id: str,
    worktree_path: Path,
    invocation: AgentInvocation,
    adapter_fn: AdapterFn,
    commit_message: str,
    capability: CapabilityRecord | None = None,
    agent_allowlist: list[str] | None = None,
    role: str | None = None,
    actor: str = "agent",
    voice: str | None = None,
    instructions: str = "",
    mcp_refs: list[str] | None = None,
    skill_refs: list[SkillRef] | None = None,
    persona_ref: str | None = None,
    model_profile_ref: str | None = None,
    repo_root: Path | None = None,
) -> dict:
    def fn(_payload: dict) -> dict:
        if capability is not None:
            # A real Agent Manifest's declared `capabilities` (ADR-0002) is
            # the caller-supplied allowlist; a caller with no manifest to
            # resolve (no `agentRef` on the node) falls back to a
            # self-permitting singleton, matching pre-ADR-0002 behavior.
            decision = authorize(
                conn,
                capability=capability,
                agent_allowlist=agent_allowlist if agent_allowlist is not None else [capability.ref],
                run_id=run_id,
                actor=actor,
                step_id=step_id,
                role=role,
            )
            if decision != Decision.ALLOW:
                raise AgentStepError(
                    f"blocked by Capability Guard: {decision.value}",
                    failure_class="POLICY_DENIED",
                )

        compiled_persona = _resolve_persona(repo_root, persona_ref)

        skilled_invocation = _apply_skills(
            conn,
            run_id=run_id,
            step_id=step_id,
            worktree_path=worktree_path,
            repo_root=repo_root,
            skill_refs=list(skill_refs) if skill_refs else [],
            persona=compiled_persona,
            actor=actor,
            instructions=instructions,
            invocation=invocation,
        )

        effective_invocation = _apply_mcp(
            conn,
            run_id=run_id,
            step_id=step_id,
            worktree_path=worktree_path,
            repo_root=repo_root,
            mcp_refs=list(mcp_refs) if mcp_refs else [],
            capability_refs=agent_allowlist if agent_allowlist is not None else [capability.ref] if capability else [],
            actor=actor,
            invocation=skilled_invocation,
        )

        modeled_invocation = _apply_model_profile(
            repo_root=repo_root,
            model_profile_ref=model_profile_ref,
            invocation=effective_invocation,
        )

        result = adapter_fn(modeled_invocation)
        if result.status != AgentStatus.COMPLETED:
            raise AgentStepError(
                f"adapter did not complete: status={result.status.value} reason={result.termination_reason!r}",
                failure_class=AGENT_STATUS_FAILURE_CLASSES.get(result.status, "INTERNAL"),
            )
        output = {"status": result.status.value, "termination_reason": result.termination_reason}
        if voice is not None:
            output["voice"] = voice
        return output

    output = run_step(conn, step_id=step_id, run_id=run_id, fn=fn, input_payload={})
    # Reached only when `fn` returned without raising, meaning the Step's
    # SUCCEEDED status is already committed to `steps` (Section 13.2).
    # Only now is it safe to commit the worktree's changes.
    commit_sha = commit_all_changes(worktree_path, commit_message)
    return {**output, "commit_sha": commit_sha}
