"""Capability Guard: the single authorization chokepoint (Section 9.2).

`evaluate` is pure — Capability Record + Agent Manifest allowlist + declared risk
class in, decision out — so it is unit-testable without a database. `authorize`
wraps it to write the decision to the `events` table before the action executes.
"""

import sqlite3
from enum import Enum

from awf.events.writer import write_event
from awf.registry.capability_record import CapabilityRecord


class Decision(Enum):
    ALLOW = "allow"
    DENY = "deny"
    APPROVAL_REQUIRED = "approval_required"


def evaluate(capability: CapabilityRecord, agent_allowlist: list[str]) -> tuple[Decision, str]:
    if capability.ref not in agent_allowlist:
        return Decision.DENY, "not_in_agent_allowlist"

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
) -> Decision:
    decision, reason_code = evaluate(capability, agent_allowlist)
    write_event(
        conn,
        run_id=run_id,
        step_id=step_id,
        new_status=decision.value,
        actor=actor,
        reason_code=reason_code,
        payload_json=(
            '{"capability_ref": "%s", "risk_class": "%s"}'
            % (capability.ref, capability.risk_class)
        ),
    )
    return decision
