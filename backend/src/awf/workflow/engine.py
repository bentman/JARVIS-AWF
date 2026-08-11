"""Workflow engine (Section 12): executes a WorkflowDefinition as durable Steps.

All eight Section 12.2 node types are interpreted: `activity`, `agent`,
`gate`, `handoff`, `approval`, `subworkflow`, `map`, and `loop`.

Branching is driven by two engine-specific node fields that are NOT part of
the Section 12.1 spec shape: `next` (the node id to run afterward; absent
means the workflow completes) and, on `gate` nodes, `onFail` (the node id to
jump to when the gate fails).

Any node executor MAY return `{"waiting_input": True, ...}` (the `handoff`
executor does this when it exhausts `maxHops` without its termination
condition being set, Section 13.4; `approval` does this while a decision is
still pending; `loop` does this when it exhausts `maxIterations` while its
condition still holds) - the engine stops there and returns `status:
"WAITING_INPUT"` without advancing to `next`, matching the "MUST NOT
silently continue or silently succeed" rule.

`handoff` and `loop` nodes manage their own internal Step/Run state
(Section 13.4: "each hop is a normal, durable Step"; each `loop` iteration
is itself a fully durable child Run) - the engine does not create an outer
Step row for either node type itself, only for `agent`/`gate`/`approval`/
`subworkflow`/`map`.

Every `agent` node passes through the Capability Guard (Section 9.2) before
its adapter runs: a node MAY declare `capability: {name, version}` to
resolve a real, published Capability Record; one that doesn't gets a
conservative synthesized R1/approval-never record instead, so every
invocation is still authorized and logged, never skipped.

`activity` nodes pass through the same Guard chokepoint (ADR-0009) when the
executor is constructed with a `repo_root`: the node's `function` name
resolves a published `capabilities/<function>/1.0.0` record if one exists,
else a conservative synthesized activity/R1/approval-never record, mirroring
the `agent`-node fallback.

A node MAY also declare `agentRef: name@version` (ADR-0002) resolving a
real Agent Manifest, whose `adapter`/`capabilities`/`role`/`voice` become
this invocation's defaults - the node's own `adapter`/`role` fields still
win if present, and the node's `objective` is the per-invocation task,
layered under (never replacing) the manifest's default instructions. A
manifest's `capabilities` list becomes the Guard's real allowlist for this
invocation, replacing the self-permitting singleton used when no manifest
is resolved. A manifest's `model_profile` (ADR-0005), when set, is resolved
and threaded through so the adapter runs with that profile's winning
candidate's model, via its own `--model`/`-m` flag.

A Step that raises is caught here at the Run level: the Run is marked
`FAILED` and a clean result dict is returned, rather than letting the
exception propagate to the caller as an unhandled crash.
"""

import re
import sqlite3
from collections.abc import Callable
from pathlib import Path

from awf.adapters.base import AgentInvocation, AgentResult
from awf.clock import utc_now_rfc3339
from awf.engine.agent_step import run_agent_step
from awf.engine.executor import StepFailure, run_step
from awf.engine.run import create_step
from awf.events.writer import write_event
from awf.guard.capability_guard import Decision, authorize
from awf.registry.agent_manifest import AgentManifest, load_agent_manifest
from awf.registry.capability_record import CapabilityRecord, Effects, Identity, load_capability_record
from awf.registry.resolve import RegistryObjectNotFoundError, resolve_registry_object
from awf.workflow.activities import ACTIVITY_REGISTRY, UnknownActivityError
from awf.workflow.definition import WorkflowDefinition
from awf.workflow.io_schema import OutputValidationError, render_outputs, validate_output

NodeExecutor = Callable[[sqlite3.Connection, str, str, dict], dict]
AdapterFn = Callable[[AgentInvocation], AgentResult]

EXECUTABLE_NODE_TYPES = ("activity", "agent", "gate", "handoff", "approval", "subworkflow", "map", "loop")

# Node types that manage their own internal Step rows and should not get a
# generic outer Step created for them by the engine.
SELF_STEPPING_NODE_TYPES = ("handoff", "loop")
_INPUT_TEMPLATE_RE = re.compile(r"\{\{\s*input\.(\w+)\s*\}\}")
_NON_WORD_RE = re.compile(r"\W+")


class WorkflowEngineError(RuntimeError):
    pass


def _render_input_templates(value: str, workflow_input: dict) -> str:
    return _INPUT_TEMPLATE_RE.sub(lambda match: str(workflow_input.get(match.group(1), "")), value)


def _render_input_templates_in_value(value, workflow_input: dict):
    if isinstance(value, str):
        return _render_input_templates(value, workflow_input)
    if isinstance(value, list):
        return [_render_input_templates_in_value(item, workflow_input) for item in value]
    if isinstance(value, dict):
        return {key: _render_input_templates_in_value(item, workflow_input) for key, item in value.items()}
    return value


def _engine_context_key(node_id: str, output_key: str) -> str:
    node_part = _NON_WORD_RE.sub("_", node_id).strip("_")
    output_part = _NON_WORD_RE.sub("_", output_key).strip("_")
    return f"{node_part}_{output_part}"


def _synthesized_capability_for_node(node: dict, adapter_name: str) -> CapabilityRecord:
    """A conservative stand-in Capability Record for an `agent` node that
    doesn't declare a real one - still real enough to be evaluated and
    logged by the Guard, never a rubber stamp."""
    return CapabilityRecord(
        identity=Identity(
            type="cli-adapter-action", provider=adapter_name, name=f"agent_node_{node['id']}", version="0.0.0"
        ),
        schema_input="",
        schema_output="",
        effects=Effects(operation="update", reversible=True, idempotent=False, external_side_effect=True),
        risk_class="R1",
        approval="never",
        constraints={},
    )


def _resolve_node_capability(node: dict, repo_root: Path, adapter_name: str) -> CapabilityRecord:
    declared = node.get("capability")
    if not declared:
        return _synthesized_capability_for_node(node, adapter_name)
    path, _source = resolve_registry_object(repo_root, "capabilities", declared["name"], declared["version"])
    return load_capability_record(path)


def _resolve_agent_manifest(node: dict, repo_root: Path) -> AgentManifest | None:
    agent_ref = node.get("agentRef")
    if not agent_ref:
        return None
    name, _, version = agent_ref.partition("@")
    path, _source = resolve_registry_object(repo_root, "agents", name, version)
    return load_agent_manifest(path)


def make_agent_node_executor(
    adapter_registry: dict[str, AdapterFn],
    worktree_path: Path,
    repo_root: Path,
    workflow_input: dict | None = None,
) -> NodeExecutor:
    def executor(conn: sqlite3.Connection, run_id: str, step_id: str, node: dict) -> dict:
        manifest = _resolve_agent_manifest(node, repo_root)
        adapter_name = node.get("adapter") or (manifest.adapter if manifest else None)
        if not adapter_name:
            raise WorkflowEngineError(f"agent node '{node['id']}': no adapter - declare 'adapter' or 'agentRef'")

        input_data = dict(workflow_input or {})
        invocation = AgentInvocation(
            objective=_render_input_templates(node["objective"], input_data),
            inputs=input_data,
            workspace_root=worktree_path,
            constraints=node.get("constraints", {}),
        )
        output = run_agent_step(
            conn,
            step_id=step_id,
            run_id=run_id,
            worktree_path=worktree_path,
            invocation=invocation,
            adapter_fn=adapter_registry[adapter_name],
            commit_message=f"workflow: {node['id']}",
            capability=_resolve_node_capability(node, repo_root, adapter_name),
            # An empty/undeclared `capabilities` list means this manifest
            # hasn't scoped an allowlist yet, not "allow nothing" - it falls
            # back to the same self-permitting default as no manifest at
            # all, matching Section 9.2's "a maximum, never a grant" framing
            # (a maximum only constrains once it's actually declared).
            agent_allowlist=list(manifest.capabilities) if manifest and manifest.capabilities else None,
            role=node.get("role") or (manifest.role if manifest else None),
            actor=adapter_name,
            voice=manifest.voice if manifest else None,
            instructions=manifest.instructions if manifest else "",
            mcp_refs=list(manifest.mcp) if manifest and manifest.mcp else [],
            skill_refs=list(manifest.skills) if manifest and manifest.skills else [],
            persona_ref=manifest.persona if manifest else None,
            model_profile_ref=manifest.model_profile if manifest else None,
            repo_root=repo_root,
        )
        return output

    return executor


def _synthesized_capability_for_activity(node: dict) -> CapabilityRecord:
    """A conservative stand-in Capability Record for an `activity` node whose
    function has no published record - the activity counterpart of
    `_synthesized_capability_for_node`, still real enough to be evaluated
    and logged by the Guard, never a rubber stamp."""
    return CapabilityRecord(
        identity=Identity(type="activity", provider="awf", name=node["function"], version="0.0.0"),
        schema_input="",
        schema_output="",
        effects=Effects(operation="execute", reversible=True, idempotent=True, external_side_effect=False),
        risk_class="R1",
        approval="never",
        constraints={},
    )


def _resolve_activity_capability(node: dict, repo_root: Path) -> CapabilityRecord:
    try:
        path, _source = resolve_registry_object(repo_root, "capabilities", node["function"], "1.0.0")
    except RegistryObjectNotFoundError:
        return _synthesized_capability_for_activity(node)
    return load_capability_record(path)


def make_activity_node_executor(
    activity_registry: dict = ACTIVITY_REGISTRY,
    repo_root: Path | None = None,
    worktree_path: Path | None = None,
    workflow_input: dict | None = None,
) -> NodeExecutor:
    def executor(conn: sqlite3.Connection, run_id: str, step_id: str, node: dict) -> dict:
        rendered_node = {
            **node,
            "args": _render_input_templates_in_value(node.get("args", {}), dict(workflow_input or {})),
        }
        if repo_root is not None and node["function"] in {"fs_read", "fs_write", "fs_delete", "command_run", "network_fetch"}:
            from awf.machine.activities import run_machine_activity

            capability = _resolve_activity_capability(node, repo_root)
            return run_machine_activity(
                conn,
                repo_root=repo_root,
                worktree_path=worktree_path or repo_root,
                run_id=run_id,
                step_id=step_id,
                node=rendered_node,
                capability=capability,
            )

        def fn(_payload: dict) -> dict:
            activity_fn = activity_registry.get(node["function"])
            if activity_fn is None:
                raise UnknownActivityError(f"node '{node['id']}': no registered activity named '{node['function']}'")
            if repo_root is not None:
                capability = _resolve_activity_capability(node, repo_root)
                decision = authorize(
                    conn,
                    capability=capability,
                    agent_allowlist=[capability.ref],
                    run_id=run_id,
                    actor="awf",
                    step_id=step_id,
                )
                if decision != Decision.ALLOW:
                    raise StepFailure(
                        f"blocked by Capability Guard: {decision.value}",
                        failure_class="POLICY_DENIED",
                    )
            return activity_fn(conn, rendered_node.get("args", {}))

        return run_step(conn, step_id=step_id, run_id=run_id, fn=fn, input_payload={})

    return executor


def _mark_run_failed(conn: sqlite3.Connection, *, run_id: str, reason_code: str) -> None:
    conn.execute(
        "UPDATE runs SET status = 'FAILED', updated_at = ? WHERE run_id = ?",
        (utc_now_rfc3339(), run_id),
    )
    conn.commit()
    write_event(conn, run_id=run_id, new_status="FAILED", actor="engine", reason_code=reason_code)


def run_workflow_definition(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    workflow: WorkflowDefinition,
    node_executors: dict[str, NodeExecutor],
) -> dict:
    max_repairs = workflow.budgets.get("maxRepairIterations", 3)
    repairs_used = 0
    hops_used = 0
    last_verdict_artifact_id = None
    node_output_context = {}
    attempt_counts: dict[str, int] = {}

    conn.execute(
        "UPDATE runs SET status = 'RUNNING', updated_at = ? WHERE run_id = ?",
        (utc_now_rfc3339(), run_id),
    )
    conn.commit()

    current_id = workflow.nodes[0]["id"]
    while current_id is not None:
        node = workflow.node(current_id)
        node_type = node["type"]
        if node_type not in EXECUTABLE_NODE_TYPES:
            raise WorkflowEngineError(
                f"node '{current_id}' (type={node_type}) has no execution semantics yet "
                f"(only {EXECUTABLE_NODE_TYPES} are executable in this phase)"
            )
        executor = node_executors.get(node_type)
        if executor is None:
            raise WorkflowEngineError(f"no executor registered for node type '{node_type}'")

        attempt_counts[current_id] = attempt_counts.get(current_id, 0) + 1
        # step_id is globally unique (Section 8: PRIMARY KEY) - scoped by
        # run_id, not just node id, since the same node id recurs across
        # different Runs of the same workflow.
        step_id = f"{run_id}:{current_id}#{attempt_counts[current_id]}"
        if node_type not in SELF_STEPPING_NODE_TYPES:
            create_step(conn, step_id=step_id, run_id=run_id, node_id=current_id, attempt=attempt_counts[current_id])

        try:
            output = executor(conn, run_id, step_id, node)
        except Exception as exc:
            # run_step (or the handoff executor's own per-hop run_step calls)
            # already recorded the Step's FAILED status and failure_class
            # before this propagated - this is the Run-level consequence.
            _mark_run_failed(conn, run_id=run_id, reason_code=f"step_failed:{exc}")
            return {"status": "FAILED", "repairs_used": repairs_used, "error": str(exc)}

        if "hops_used" in output:
            hops_used = output["hops_used"]
        if isinstance(output, dict):
            for output_key, value in output.items():
                node_output_context[_engine_context_key(current_id, output_key)] = value

        if output.get("waiting_input"):
            return {"status": "WAITING_INPUT", "repairs_used": repairs_used, **output}

        if node_type == "gate":
            if output.get("passed"):
                last_verdict_artifact_id = output.get("verdict_artifact_id")
                current_id = node.get("next")
            else:
                terminal_failure = output.get("terminal_failure", False)
                if terminal_failure or repairs_used >= max_repairs:
                    reason_code = "gate_terminal_failure" if terminal_failure else "gate_repair_budget_exhausted"
                    _mark_run_failed(conn, run_id=run_id, reason_code=reason_code)
                    return {
                        "status": "FAILED",
                        "repairs_used": repairs_used,
                        "verdict_artifact_id": output.get("verdict_artifact_id"),
                    }
                repairs_used += 1
                current_id = node.get("onFail")
                if current_id is None:
                    raise WorkflowEngineError(f"gate node '{node['id']}' failed with no 'onFail' target")
        else:
            current_id = node.get("next")

    engine_context = {
        "repairs_used": repairs_used,
        "hops_used": hops_used,
        "verdict_artifact_id": last_verdict_artifact_id,
        **node_output_context,
    }
    rendered_outputs = render_outputs(workflow.outputs, engine_context)
    try:
        validate_output(rendered_outputs, workflow.output_schema)
    except OutputValidationError as exc:
        _mark_run_failed(conn, run_id=run_id, reason_code=f"output_schema_invalid:{exc}")
        return {"status": "FAILED", "repairs_used": repairs_used, "error": str(exc)}

    conn.execute(
        "UPDATE runs SET status = 'SUCCEEDED', updated_at = ? WHERE run_id = ?",
        (utc_now_rfc3339(), run_id),
    )
    conn.commit()
    write_event(conn, run_id=run_id, new_status="SUCCEEDED", actor="engine", reason_code="run_completed")
    return {
        "status": "SUCCEEDED",
        "repairs_used": repairs_used,
        "verdict_artifact_id": last_verdict_artifact_id,
        "outputs": rendered_outputs,
    }
