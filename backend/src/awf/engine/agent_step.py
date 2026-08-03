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
"""

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Callable

from awf.adapters.base import AgentInvocation, AgentResult, AgentStatus
from awf.engine.executor import StepFailure, run_step
from awf.envfile import get_env_value
from awf.events.writer import write_event
from awf.guard.capability_guard import Decision, authorize
from awf.isolation.worktree import commit_all_changes
from awf.mcp.render import RENDERERS
from awf.registry.capability_record import CapabilityRecord
from awf.registry.mcp_server import load_mcp_server
from awf.registry.resolve import resolve_registry_object
from awf.secrets.store import get_secret

AdapterFn = Callable[[AgentInvocation], AgentResult]

AGENT_STATUS_FAILURE_CLASSES = {
    AgentStatus.FAILED: "TOOL_ERROR",
    AgentStatus.LIMIT_EXCEEDED: "TIMEOUT",
}


class AgentStepError(StepFailure):
    pass


def _is_trusted(conn: sqlite3.Connection, name: str, version: str, source: str) -> bool:
    if source != "data":
        # config/app_registry/ objects carry no trust field - inclusion in
        # the repository is the review (Section 9.3).
        return True
    row = conn.execute(
        "SELECT trust_status FROM registry_index WHERE kind = 'mcp' AND name = ? AND version = ?",
        (name, version),
    ).fetchone()
    if row is None:
        return True
    return row["trust_status"] not in ("quarantined", "blocked")


def _resolve_mcp_servers(conn: sqlite3.Connection, repo_root: Path, mcp_refs: list[str]):
    """Returns (servers, refs_with_digest) for the refs that pass the trust gate."""
    servers = []
    refs_with_digest = []
    for ref in mcp_refs:
        name, _, version = ref.partition("@")
        path, source = resolve_registry_object(repo_root, "mcp", name, version)
        if not _is_trusted(conn, name, version, source):
            continue
        servers.append(load_mcp_server(path))
        refs_with_digest.append({"ref": ref, "digest": hashlib.sha256(path.read_bytes()).hexdigest()})
    return servers, refs_with_digest


def _resolve_secrets(conn: sqlite3.Connection, repo_root: Path, servers) -> dict[str, str]:
    secret_names = set()
    for server in servers:
        secret_names.update(server.env_secrets.values())
        secret_names.update(server.header_secrets.values())
    if not secret_names:
        return {}
    secret_key = get_env_value(repo_root / ".env", "AWF_SECRET_KEY").encode("ascii")
    return {name: get_secret(conn, name, secret_key) for name in secret_names}


def _apply_mcp(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    step_id: str,
    worktree_path: Path,
    repo_root: Path | None,
    mcp_refs: list[str],
    actor: str,
    invocation: AgentInvocation,
) -> AgentInvocation:
    if not mcp_refs or repo_root is None:
        return invocation

    servers, refs_with_digest = _resolve_mcp_servers(conn, repo_root, mcp_refs)
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

    write_event(
        conn, run_id=run_id, step_id=step_id, new_status="mcp_rendered",
        actor=actor, reason_code="mcp_rendered",
        payload_json=json.dumps({"servers": refs_with_digest}),
    )

    if not rendered.extra_args and not rendered.env_overlay:
        return invocation

    constraints = dict(invocation.constraints)
    if rendered.extra_args:
        constraints["mcp_extra_args"] = list(rendered.extra_args)
    if rendered.env_overlay:
        constraints["mcp_env_overlay"] = rendered.env_overlay
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
    mcp_refs: list[str] | None = None,
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

        effective_invocation = _apply_mcp(
            conn,
            run_id=run_id,
            step_id=step_id,
            worktree_path=worktree_path,
            repo_root=repo_root,
            mcp_refs=list(mcp_refs) if mcp_refs else [],
            actor=actor,
            invocation=invocation,
        )

        result = adapter_fn(effective_invocation)
        if result.status != AgentStatus.COMPLETED:
            raise AgentStepError(
                f"adapter did not complete: status={result.status.value} "
                f"reason={result.termination_reason!r}",
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
