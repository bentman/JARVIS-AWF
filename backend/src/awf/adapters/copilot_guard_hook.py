"""Copilot CLI `preToolUse` hook backed by the AWF Capability Guard."""

import json
import os
import sys
from pathlib import Path

from awf.db.connection import get_connection
from awf.guard.capability_guard import Decision, authorize
from awf.paths import db_path as resolve_db_path
from awf.registry.capability_record import load_capability_record

DEFAULT_TOOL_CAPABILITIES = {
    "bash": "command_run@1.0.0",
    "powershell": "command_run@1.0.0",
    "shell": "command_run@1.0.0",
    "read": "fs_read@1.0.0",
    "view": "fs_read@1.0.0",
    "grep": "fs_read@1.0.0",
    "rg": "fs_read@1.0.0",
    "glob": "fs_read@1.0.0",
    "write": "fs_write@1.0.0",
    "create": "fs_write@1.0.0",
    "edit": "fs_write@1.0.0",
    "str_replace_editor": "fs_write@1.0.0",
    "apply_patch": "fs_write@1.0.0",
}


def _load_json_env(name: str, default):
    raw = os.environ.get(name)
    if not raw:
        return default
    return json.loads(raw)


def _tool_name(payload: dict) -> str:
    return str(payload.get("toolName") or payload.get("tool_name") or "").strip()


def _tool_args_type(payload: dict) -> str:
    args = payload.get("toolArgs", payload.get("tool_input"))
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except json.JSONDecodeError:
            return "string"
    if args is None:
        return "null"
    if isinstance(args, dict):
        return "object"
    if isinstance(args, list):
        return "array"
    return type(args).__name__


def _capability_ref_for_tool(tool_name: str, mapping: dict[str, str]) -> str | None:
    return mapping.get(tool_name.lower())


def _load_capability(repo_root: Path, capability_ref: str):
    name, _, version = capability_ref.partition("@")
    if not name or not version:
        raise ValueError(f"invalid capability ref {capability_ref!r}")
    return load_capability_record(repo_root / "config" / "app_registry" / "capabilities" / name / f"{version}.yaml")


def _decision_response(decision: Decision, reason: str) -> dict:
    if decision == Decision.ALLOW:
        return {"permissionDecision": "allow"}
    return {"permissionDecision": "deny", "permissionDecisionReason": reason}


def evaluate_pre_tool_use(payload: dict) -> dict:
    repo_root = Path(os.environ["AWF_REPO_ROOT"])
    run_id = os.environ["AWF_RUN_ID"]
    step_id = os.environ.get("AWF_STEP_ID") or None
    actor = os.environ.get("AWF_ACTOR", "copilot")
    role = os.environ.get("AWF_ROLE") or None
    agent_allowlist = _load_json_env("AWF_AGENT_ALLOWLIST", [])
    mapping = {**DEFAULT_TOOL_CAPABILITIES, **_load_json_env("AWF_COPILOT_TOOL_CAPABILITIES", {})}
    tool_name = _tool_name(payload)
    capability_ref = _capability_ref_for_tool(tool_name, mapping)
    if capability_ref is None:
        return {
            "permissionDecision": "deny",
            "permissionDecisionReason": f"no AWF capability mapping for Copilot tool {tool_name!r}",
        }

    conn = get_connection(resolve_db_path(repo_root))
    try:
        capability = _load_capability(repo_root, capability_ref)
        decision = authorize(
            conn,
            capability=capability,
            agent_allowlist=agent_allowlist,
            run_id=run_id,
            actor=actor,
            step_id=step_id,
            role=role,
            payload_extra={
                "copilot_tool_name": tool_name,
                "copilot_tool_args_type": _tool_args_type(payload),
            },
        )
    finally:
        conn.close()
    return _decision_response(decision, f"AWF Capability Guard returned {decision.value} for {capability_ref}")


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        response = evaluate_pre_tool_use(payload if isinstance(payload, dict) else {})
    except Exception as exc:
        response = {"permissionDecision": "deny", "permissionDecisionReason": f"AWF hook error: {exc}"}
    print(json.dumps(response, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
