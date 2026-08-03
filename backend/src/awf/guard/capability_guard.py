"""Capability Guard: the single authorization chokepoint (Section 9.2).

`evaluate` is pure — Capability Record + Agent Manifest allowlist + declared risk
class in, decision out — so it is unit-testable without a database. `authorize`
wraps it to write the decision to the `events` table before the action executes.

Trifecta role enforcement (Section 12.3): each role is passed a `role` field
inside the `AgentInvocation` `constraints` block. The Guard - never the agent's
own self-assessment - enforces the restriction before the action executes: a
`verifier`-scoped invocation MUST be denied any write capability above R0; an
`adversary`-scoped invocation MUST be denied any capability that would alter
the candidate artifact or worktree state. Detecting an agent that claims a
different role in its own output is a separate concern belonging to
`AgentResult` post-processing, not this pre-execution check.
"""

import sqlite3
from enum import Enum

from awf.events.writer import write_event
from awf.registry.capability_record import CapabilityRecord

ROLES = ("builder", "verifier", "adversary")

# Effects.operation values that mutate the worktree or a candidate artifact -
# the operations a verifier or adversary role MUST NOT be granted.
WRITE_OPERATIONS = ("create", "update", "delete")


class Decision(Enum):
    ALLOW = "allow"
    DENY = "deny"
    APPROVAL_REQUIRED = "approval_required"


def evaluate(
    capability: CapabilityRecord, agent_allowlist: list[str], role: str | None = None
) -> tuple[Decision, str]:
    if capability.ref not in agent_allowlist:
        return Decision.DENY, "not_in_agent_allowlist"

    if role is not None and role not in ROLES:
        raise ValueError(f"role '{role}' not in {ROLES}")

    is_write = capability.effects.operation in WRITE_OPERATIONS

    if role == "verifier" and is_write and capability.risk_class != "R0":
        return Decision.DENY, "policy_denied_verifier_write_above_r0"

    if role == "adversary" and is_write:
        return Decision.DENY, "policy_denied_adversary_altering_capability"

    if capability.risk_class == "R3":
        return Decision.DENY, "prohibited_risk_class"

    if capability.risk_class == "R0":
        return Decision.ALLOW, "autoallow_r0"

    if capability.approval == "never":
        return Decision.ALLOW, "approval_never"

    return Decision.APPROVAL_REQUIRED, f"approval_{capability.approval.replace('-', '_')}"


def authorize(
    conn: sqlite3.Connection,
    *,
    capability: CapabilityRecord,
    agent_allowlist: list[str],
    run_id: str,
    actor: str,
    step_id: str | None = None,
    role: str | None = None,
) -> Decision:
    decision, reason_code = evaluate(capability, agent_allowlist, role)
    write_event(
        conn,
        run_id=run_id,
        step_id=step_id,
        new_status=decision.value,
        actor=actor,
        reason_code=reason_code,
        payload_json=(
            '{"capability_ref": "%s", "risk_class": "%s", "role": %s}'
            % (
                capability.ref,
                capability.risk_class,
                f'"{role}"' if role is not None else "null",
            )
        ),
    )
    return decision
