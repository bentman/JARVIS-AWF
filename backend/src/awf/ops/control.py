"""control operation implementations."""

import json
import sqlite3
from pathlib import Path

from awf.ops.approval import op_approval_list
from awf.ops.artifact import op_artifact_list
from awf.ops.improvement import op_improvement_list
from awf.ops.llm import op_llm_serve, op_llm_servers
from awf.ops.memory import op_episodic_timeline
from awf.ops.registry import op_registry_get, op_registry_list
from awf.ops.run import op_run_list, op_run_outcome, op_run_status
from awf.ops.system import op_system_doctor, op_system_readiness
from awf.registry.kinds import KINDS


def _recent_verdict_artifacts(conn: sqlite3.Connection, *, limit: int = 5) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM artifacts WHERE artifact_type = 'verdict' ORDER BY created_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [dict(row) for row in rows]


def _registry_counts(repo_root: Path, conn: sqlite3.Connection) -> dict[str, int]:
    counts: dict[str, int] = {}
    for registry_kind in KINDS:
        counts[registry_kind.key] = len(op_registry_list(repo_root, kind=registry_kind.key, conn=None))
    return counts


def _control_error(exc: Exception) -> dict:
    return {"error": str(exc)}


def _action(
    *,
    kind: str,
    label: str,
    command: str,
    description: str | None = None,
    run_id: str | None = None,
    approval_id: str | None = None,
    improvement_id: str | None = None,
    artifact_id: str | None = None,
    workflow_ref: str | None = None,
    registry_kind: str | None = None,
    registry_name: str | None = None,
    registry_version: str | None = None,
) -> dict:
    return {
        "kind": kind,
        "label": label,
        "command": command,
        "description": description,
        "run_id": run_id,
        "approval_id": approval_id,
        "improvement_id": improvement_id,
        "artifact_id": artifact_id,
        "workflow_ref": workflow_ref,
        "registry_kind": registry_kind,
        "registry_name": registry_name,
        "registry_version": registry_version,
    }


def _item(
    *,
    kind: str,
    title: str,
    status: str,
    priority: int,
    description: str,
    command: str,
    source: str,
    run_id: str | None = None,
    step_id: str | None = None,
    approval_id: str | None = None,
    improvement_id: str | None = None,
    artifact_id: str | None = None,
    created_at: str | None = None,
    primary_action: dict | None = None,
    secondary_actions: list[dict] | None = None,
) -> dict:
    stable_parts = [kind, run_id, step_id, approval_id, improvement_id, artifact_id, source]
    return {
        "item_id": ":".join(part for part in stable_parts if part),
        "kind": kind,
        "title": title,
        "status": status,
        "priority": priority,
        "description": description,
        "command": command,
        "source": source,
        "run_id": run_id,
        "step_id": step_id,
        "approval_id": approval_id,
        "improvement_id": improvement_id,
        "artifact_id": artifact_id,
        "created_at": created_at,
        "primary_action": primary_action
        or _action(
            kind="command",
            label="Run command",
            command=command,
            description=description,
            run_id=run_id,
            approval_id=approval_id,
            improvement_id=improvement_id,
            artifact_id=artifact_id,
        ),
        "secondary_actions": secondary_actions or [],
    }


def _run_label(run: dict) -> str:
    return f"{run.get('workflow_ref', 'workflow')} ({run.get('run_id', 'unknown')})"


def _approval_title(approval: dict) -> str:
    preview = approval.get("preview") if isinstance(approval.get("preview"), dict) else {}
    proposal = preview.get("proposal") if isinstance(preview.get("proposal"), dict) else {}
    summary = preview.get("human_summary") or proposal.get("human_summary")
    if summary:
        return f"Approval required: {summary}"
    return f"Approval required for run {approval.get('run_id')}"


def _readiness_blockers(readiness: dict) -> list[str]:
    if readiness.get("error"):
        return [str(readiness["error"])]
    results = readiness.get("readiness") if isinstance(readiness.get("readiness"), dict) else {}
    blockers = []
    for name, result in results.items():
        if not isinstance(result, dict) or result.get("ready"):
            continue
        reason = result.get("reason") or "not ready"
        blockers.append(f"{name}: {reason}")
    return blockers


def _llm_blocker(llm_status: dict) -> str | None:
    if llm_status.get("error"):
        return str(llm_status["error"])
    state = llm_status.get("state")
    if state in {None, "running", "adopted"}:
        return None
    reason = llm_status.get("reason")
    return f"LLM server is {state}" + (f": {reason}" if reason else "")


def _derive_operator_work_items(
    *,
    runs: list[dict],
    approvals: list[dict],
    improvements: list[dict],
    recent_verdicts: list[dict],
    readiness: dict,
    doctor: dict,
    llm_status: dict,
) -> list[dict]:
    items: list[dict] = []
    for approval in approvals:
        approval_id = approval.get("approval_id")
        items.append(
            _item(
                kind="approval",
                title=_approval_title(approval),
                status="blocked",
                priority=10,
                description="A workflow step is waiting for an operator decision.",
                command=f"awf approval {approval_id}",
                source="approvals",
                run_id=approval.get("run_id"),
                step_id=approval.get("step_id"),
                approval_id=approval_id,
                created_at=approval.get("requested_at"),
                primary_action=_action(
                    kind="approval.review",
                    label="Review approval",
                    command=f"awf approval {approval_id}",
                    description="Open the approval and decide from the run context.",
                    run_id=approval.get("run_id"),
                    approval_id=approval_id,
                ),
                secondary_actions=[
                    _action(
                        kind="run.detail",
                        label="Open run",
                        command=f"awf status {approval.get('run_id')}",
                        run_id=approval.get("run_id"),
                    )
                ]
                if approval.get("run_id")
                else [],
            )
        )

    active_statuses = {"CREATED", "VALIDATING", "QUEUED", "RUNNING", "WAITING_INPUT", "WAITING_APPROVAL", "CANCELING"}
    for run in runs:
        status = run.get("status")
        outcome = run.get("outcome") if isinstance(run.get("outcome"), dict) else {}
        run_id = run.get("run_id")
        if status == "FAILED":
            items.append(
                _item(
                    kind="failed_run",
                    title=f"Failed run: {_run_label(run)}",
                    status="blocked",
                    priority=20,
                    description=outcome.get("next_action") or "Inspect failed steps and evidence.",
                    command=f"awf status {run_id}",
                    source="runs",
                    run_id=run_id,
                    created_at=run.get("updated_at") or run.get("created_at"),
                    primary_action=_action(
                        kind="run.detail",
                        label="Inspect failure",
                        command=f"awf status {run_id}",
                        description="Open failed steps, artifacts, and recovery context.",
                        run_id=run_id,
                    ),
                )
            )
        elif status in active_statuses:
            priority = 15 if status in {"WAITING_INPUT", "WAITING_APPROVAL"} else 40
            items.append(
                _item(
                    kind="active_run",
                    title=f"Run {status}: {_run_label(run)}",
                    status=str(status).lower(),
                    priority=priority,
                    description=outcome.get("next_action") or "Watch progress and resolve the next blocking item.",
                    command=f"awf status {run_id}",
                    source="runs",
                    run_id=run_id,
                    created_at=run.get("updated_at") or run.get("created_at"),
                    primary_action=_action(
                        kind="run.detail",
                        label="Open run",
                        command=f"awf status {run_id}",
                        description="Open current step, blockers, approvals, and evidence.",
                        run_id=run_id,
                    ),
                )
            )

    for proposal in improvements:
        status = proposal.get("status")
        if status not in {"draft", "ready_for_review", "approved"}:
            continue
        next_action = proposal.get("next_action") if isinstance(proposal.get("next_action"), dict) else {}
        command = next_action.get("command") or f"awf review show {proposal.get('improvement_id')}"
        label = next_action.get("label") or "Review improvement proposal"
        priority = {"approved": 12, "ready_for_review": 25, "draft": 35}.get(status, 35)
        items.append(
            _item(
                kind="improvement",
                title=f"{label}: {proposal.get('improvement_id')}",
                status=str(status),
                priority=priority,
                description=proposal.get("human_summary")
                or proposal.get("summary")
                or "Improvement proposal needs review.",
                command=command,
                source="improvements",
                run_id=proposal.get("run_id"),
                improvement_id=proposal.get("improvement_id"),
                artifact_id=proposal.get("verdict_artifact_id"),
                created_at=proposal.get("updated_at") or proposal.get("created_at"),
                primary_action=_action(
                    kind="improvement.review",
                    label=str(label),
                    command=command,
                    description="Review proposal evidence and complete the next proposal action.",
                    run_id=proposal.get("run_id"),
                    improvement_id=proposal.get("improvement_id"),
                    artifact_id=proposal.get("verdict_artifact_id"),
                ),
                secondary_actions=[
                    _action(
                        kind="run.detail",
                        label="Open run",
                        command=f"awf status {proposal.get('run_id')}",
                        run_id=proposal.get("run_id"),
                    )
                ]
                if proposal.get("run_id")
                else [],
            )
        )

    for blocker in _readiness_blockers(readiness):
        items.append(
            _item(
                kind="readiness",
                title="Readiness is not complete",
                status="blocked",
                priority=30,
                description=blocker,
                command="awf doctor",
                source="readiness",
                primary_action=_action(
                    kind="doctor.open",
                    label="Open doctor",
                    command="awf doctor",
                    description=blocker,
                ),
            )
        )

    blocker = _llm_blocker(llm_status if isinstance(llm_status, dict) else {})
    if blocker:
        items.append(
            _item(
                kind="llm",
                title="LLM runtime needs attention",
                status="blocked",
                priority=32,
                description=blocker,
                command="awf system llm serve status",
                source="llm",
                primary_action=_action(
                    kind="llm.status",
                    label="Check LLM",
                    command="awf system llm serve status",
                    description=blocker,
                ),
                secondary_actions=[
                    _action(kind="llm.models", label="Load models", command="awf system llm models"),
                ],
            )
        )

    next_actions = doctor.get("next_actions") if isinstance(doctor.get("next_actions"), list) else []
    for index, action in enumerate(next_actions):
        items.append(
            _item(
                kind="doctor",
                title="Doctor check needs action",
                status=str(doctor.get("status", "warn")),
                priority=34 + index,
                description=str(action),
                command="awf doctor",
                source="doctor",
                primary_action=_action(
                    kind="doctor.open",
                    label="Open doctor",
                    command="awf doctor",
                    description=str(action),
                ),
            )
        )

    open_run_ids = {item.get("run_id") for item in items if item.get("run_id")}
    completed_runs = [
        run
        for run in runs
        if run.get("status") == "SUCCEEDED"
        and run.get("run_id") not in open_run_ids
        and isinstance(run.get("outcome"), dict)
        and run["outcome"].get("evidence")
    ]
    for run in completed_runs[:3]:
        evidence = run["outcome"].get("evidence") if isinstance(run["outcome"].get("evidence"), list) else []
        items.append(
            _item(
                kind="completed_evidence",
                title=f"Review completed evidence: {_run_label(run)}",
                status="review",
                priority=80,
                description=f"{len(evidence)} evidence artifact(s) available for closeout.",
                command=f"awf status {run.get('run_id')}",
                source="artifacts",
                run_id=run.get("run_id"),
                created_at=run.get("updated_at") or run.get("created_at"),
                primary_action=_action(
                    kind="run.detail",
                    label="Review evidence",
                    command=f"awf status {run.get('run_id')}",
                    description="Open the completed run and inspect its artifacts.",
                    run_id=run.get("run_id"),
                ),
            )
        )

    if not items and not recent_verdicts:
        first_run = doctor.get("first_run_command") or 'awf run assistant-default@1.0.0 --objective "check the system"'
        items.append(
            _item(
                kind="idle",
                title="System is idle",
                status="ready",
                priority=100,
                description="No runs, approvals, proposals, or evidence need attention.",
                command=str(first_run),
                source="control",
                primary_action=_action(
                    kind="workflow.start",
                    label="Start work",
                    command=str(first_run),
                    description="Start the default assistant workflow.",
                    workflow_ref="assistant-default@1.0.0",
                ),
            )
        )

    return sorted(items, key=lambda item: (item["priority"], item.get("created_at") or "", item["item_id"]))


def _operator_next_actions(work_items: list[dict]) -> list[dict]:
    return [
        {
            "label": item["title"],
            "command": item["command"],
            "description": item["description"],
            "kind": item["kind"],
            "run_id": item.get("run_id"),
            "approval_id": item.get("approval_id"),
            "improvement_id": item.get("improvement_id"),
            "primary_action": item.get("primary_action"),
        }
        for item in work_items[:5]
    ]


def _input_schema_summary(schema: dict) -> dict:
    properties = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
    required = schema.get("required") if isinstance(schema.get("required"), list) else []
    fields = []
    ordered_names = [name for name in required if name in properties] + [
        name for name in properties if name not in required
    ]
    for name in ordered_names:
        value = properties[name]
        field = value if isinstance(value, dict) else {}
        fields.append(
            {
                "name": name,
                "type": field.get("type") or "string",
                "required": name in required,
                "enum": field.get("enum") if isinstance(field.get("enum"), list) else None,
                "description": field.get("description"),
                "default": field.get("default"),
            }
        )
    return {"type": schema.get("type") or "object", "required": required, "fields": fields}


def _operator_start_options(repo_root: Path, conn: sqlite3.Connection, *, limit: int = 12) -> list[dict]:
    options: list[dict] = []
    for entry in op_registry_list(repo_root, kind="workflows", conn=conn)[:limit]:
        name = entry.get("name")
        version = entry.get("version")
        if not name or not version:
            continue
        ref = f"{name}@{version}"
        try:
            detail = op_registry_get(repo_root, conn, kind="workflows", name=str(name), version=str(version))
        except Exception as exc:
            options.append(
                {
                    "workflow_ref": ref,
                    "name": name,
                    "version": version,
                    "source": entry.get("source"),
                    "trust_status": entry.get("trust_status"),
                    "digest": entry.get("digest"),
                    "status": "unavailable",
                    "description": str(exc),
                    "input_schema": {},
                    "input_schema_summary": _input_schema_summary({}),
                    "primary_action": _action(
                        kind="registry.workflow.detail",
                        label="Inspect workflow",
                        command=f"awf registry get workflows {name} {version}",
                        registry_kind="workflows",
                        registry_name=str(name),
                        registry_version=str(version),
                    ),
                }
            )
            continue
        obj = detail.get("object") if isinstance(detail.get("object"), dict) else {}
        metadata = obj.get("metadata") if isinstance(obj.get("metadata"), dict) else {}
        spec = obj.get("spec") if isinstance(obj.get("spec"), dict) else {}
        input_schema = spec.get("inputSchema") or obj.get("input_schema") or {}
        if not isinstance(input_schema, dict):
            input_schema = {}
        ref = f"{metadata.get('name', name)}@{metadata.get('version', version)}"
        required = input_schema.get("required") if isinstance(input_schema.get("required"), list) else []
        start_command = f"awf run {ref}"
        if "objective" in required:
            start_command = f'{start_command} --objective "<objective>"'
        options.append(
            {
                "workflow_ref": ref,
                "name": metadata.get("name", name),
                "version": metadata.get("version", version),
                "source": entry.get("source"),
                "trust_status": entry.get("trust_status"),
                "digest": entry.get("digest") or detail.get("digest") or metadata.get("digest"),
                "status": "ready",
                "description": metadata.get("summary") or f"Run {ref}",
                "input_schema": input_schema,
                "input_schema_summary": _input_schema_summary(input_schema),
                "primary_action": _action(
                    kind="workflow.start",
                    label="Start workflow",
                    command=start_command,
                    workflow_ref=ref,
                    registry_kind="workflows",
                    registry_name=str(metadata.get("name", name)),
                    registry_version=str(metadata.get("version", version)),
                ),
            }
        )
    return options


def _safe_json(value: str | None) -> dict:
    if not value:
        return {}
    try:
        loaded = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _operator_timeline(conn: sqlite3.Connection, *, run_id: str) -> list[dict]:
    entries: list[dict] = []
    for step in conn.execute("SELECT * FROM steps WHERE run_id = ? ORDER BY started_at, step_id", (run_id,)):
        entries.append(
            {
                "kind": "step",
                "status": step["status"],
                "title": f"{step['node_id']} {step['status']}",
                "description": step["failure_class"] or f"attempt {step['attempt']}",
                "occurred_at": step["ended_at"] or step["started_at"],
                "step_id": step["step_id"],
                "node_id": step["node_id"],
                "failure_class": step["failure_class"],
                "payload": _safe_json(step["output_json"]),
            }
        )
    for approval in conn.execute("SELECT * FROM approvals WHERE run_id = ? ORDER BY requested_at", (run_id,)):
        status = approval["status"]
        entries.append(
            {
                "kind": "approval",
                "status": status,
                "title": f"Approval {status}: {approval['approval_id']}",
                "description": approval["reason"] or f"risk {approval['risk_class'] or 'R2'}",
                "occurred_at": approval["decided_at"] or approval["requested_at"],
                "step_id": approval["step_id"],
                "approval_id": approval["approval_id"],
                "action_digest": approval["action_digest"],
            }
        )
    for artifact in conn.execute("SELECT * FROM artifacts WHERE run_id = ? ORDER BY created_at", (run_id,)):
        entries.append(
            {
                "kind": "artifact",
                "status": "complete" if artifact["complete"] else "incomplete",
                "title": f"{artifact['artifact_type']}: {artifact['relative_path']}",
                "description": artifact["media_type"],
                "occurred_at": artifact["created_at"],
                "step_id": artifact["step_id"],
                "artifact_id": artifact["artifact_id"],
            }
        )
    for event in conn.execute("SELECT * FROM events WHERE run_id = ? ORDER BY occurred_at, event_id", (run_id,)):
        entries.append(
            {
                "kind": "event",
                "status": event["new_status"],
                "title": event["reason_code"],
                "description": event["actor"],
                "occurred_at": event["occurred_at"],
                "step_id": event["step_id"],
                "event_id": event["event_id"],
                "payload": _safe_json(event["payload_json"]),
            }
        )
    return sorted(entries, key=lambda item: (item.get("occurred_at") or "", item["kind"], item["title"]))


def op_events_snapshot(conn: sqlite3.Connection, *, run_id: str | None = None, limit: int = 100) -> dict:
    limit = max(1, min(int(limit), 500))
    if run_id:
        rows = conn.execute(
            "SELECT * FROM events WHERE run_id = ? ORDER BY occurred_at DESC, event_id DESC LIMIT ?",
            (run_id, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM events ORDER BY occurred_at DESC, event_id DESC LIMIT ?", (limit,)
        ).fetchall()
    return {"events": [dict(row) for row in reversed(rows)], "streaming": False}


def op_control_center_summary(repo_root: Path, conn: sqlite3.Connection) -> dict:
    readiness = op_system_readiness(repo_root)
    host_profile_id = readiness.get("profile_id") if isinstance(readiness, dict) else None
    try:
        llm_servers = op_llm_servers(repo_root, host_profile_id=host_profile_id, probe_timeout_seconds=0.15)
    except Exception as exc:
        llm_servers = _control_error(exc)
    try:
        llm_status = op_llm_serve(repo_root, conn, action="status", probe_timeout_seconds=0.15)
    except Exception as exc:
        llm_status = _control_error(exc)
    doctor = op_system_doctor(repo_root, readiness=readiness, quick=True)
    runs = op_run_list(conn)
    approvals = op_approval_list(conn)
    improvements = op_improvement_list(conn)
    recent_verdicts = _recent_verdict_artifacts(conn)
    llm_status = llm_status if isinstance(llm_status, dict) else {}
    work_items = _derive_operator_work_items(
        runs=runs,
        approvals=approvals,
        improvements=improvements,
        recent_verdicts=recent_verdicts,
        readiness=readiness if isinstance(readiness, dict) else {},
        doctor=doctor if isinstance(doctor, dict) else {},
        llm_status=llm_status,
    )
    return {
        "runs": runs,
        "approvals": approvals,
        "improvements": improvements,
        "recent_verdicts": recent_verdicts,
        "registry_counts": _registry_counts(repo_root, conn),
        "llm": {
            "servers": llm_servers,
            "status": llm_status,
        },
        "readiness": readiness,
        "doctor": doctor,
        "operator_work_items": work_items,
        "operator_next_actions": _operator_next_actions(work_items),
        "operator_start_options": _operator_start_options(repo_root, conn),
    }


def op_control_center_run_detail(repo_root: Path, conn: sqlite3.Connection, *, run_id: str) -> dict:
    status = op_run_status(conn, run_id=run_id)
    outcome = status.get("outcome") or op_run_outcome(conn, run_id=run_id)
    artifacts = op_artifact_list(conn, run_id=run_id)
    timeline = op_episodic_timeline(conn, run_id=run_id)
    improvements = op_improvement_list(conn, run_id=run_id)
    verdicts = [artifact for artifact in artifacts if artifact.get("artifact_type") == "verdict"]
    run_work_items = _derive_operator_work_items(
        runs=[{**status, "outcome": outcome}],
        approvals=op_approval_list(conn, run_id=run_id),
        improvements=improvements,
        recent_verdicts=verdicts,
        readiness={},
        doctor={},
        llm_status={},
    )
    return {
        "run": status,
        "outcome": outcome,
        "artifacts": artifacts,
        "timeline": timeline,
        "operator_timeline": _operator_timeline(conn, run_id=run_id),
        "operator_work_items": run_work_items,
        "operator_next_actions": _operator_next_actions(run_work_items),
        "improvements": improvements,
        "verdicts": verdicts,
    }


__all__ = ("op_control_center_run_detail", "op_control_center_summary", "op_events_snapshot")
