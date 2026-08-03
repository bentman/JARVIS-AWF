import json
import sqlite3
from pathlib import Path

import pytest

from awf.db.bootstrap import init_db
from awf.guard.capability_guard import Decision, authorize, evaluate
from awf.registry.capability_record import (
    RegistryValidationError,
    load_capability_record,
    parse_capability_record,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "capabilities"


def load_fixture(name: str):
    return load_capability_record(FIXTURES / name)


def test_load_r0_capability_record():
    record = load_fixture("read_file_r0.yaml")
    assert record.identity.name == "read_file"
    assert record.risk_class == "R0"
    assert record.ref == "read_file@1.0.0"


def test_load_rejects_missing_field():
    with pytest.raises(RegistryValidationError):
        parse_capability_record({"identity": {"type": "activity"}})


def test_load_rejects_invalid_risk_class():
    with pytest.raises(RegistryValidationError):
        parse_capability_record(
            {
                "identity": {"type": "activity", "provider": "local", "name": "x", "version": "1.0.0"},
                "schema": {"input": "a", "output": "b"},
                "effects": {"operation": "read", "reversible": True, "idempotent": True, "external_side_effect": False},
                "risk_class": "R9",
                "approval": "never",
            }
        )


@pytest.mark.parametrize(
    "fixture, expected",
    [
        ("read_file_r0.yaml", Decision.ALLOW),
        ("write_scratch_file_r1.yaml", Decision.ALLOW),
        ("git_push_r2.yaml", Decision.APPROVAL_REQUIRED),
        ("modify_capability_registry_r3.yaml", Decision.DENY),
    ],
)
def test_evaluate_decision_per_risk_class_when_allowlisted(fixture, expected):
    record = load_fixture(fixture)
    decision, _reason = evaluate(record, agent_allowlist=[record.ref])
    assert decision == expected


def test_evaluate_denies_when_not_in_allowlist():
    record = load_fixture("read_file_r0.yaml")
    decision, reason = evaluate(record, agent_allowlist=[])
    assert decision == Decision.DENY
    assert reason == "not_in_agent_allowlist"


def test_evaluate_is_pure_and_deterministic():
    record = load_fixture("git_push_r2.yaml")
    first = evaluate(record, agent_allowlist=[record.ref])
    second = evaluate(record, agent_allowlist=[record.ref])
    assert first == second == (Decision.APPROVAL_REQUIRED, "approval_per_invocation")


def test_authorize_writes_decision_event_before_use(tmp_path):
    db_path = tmp_path / "awf.db"
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO runs (run_id, workflow_ref, status, input_json, budget_json, created_at, updated_at) "
            "VALUES ('run-1', 'wf@1.0.0#sha256:abc', 'RUNNING', '{}', '{}', 't', 't')"
        )
        conn.commit()

        record = load_fixture("git_push_r2.yaml")
        decision = authorize(
            conn,
            capability=record,
            agent_allowlist=[record.ref],
            run_id="run-1",
            actor="test-agent",
        )

        rows = conn.execute(
            "SELECT new_status, reason_code FROM events WHERE run_id = 'run-1'"
        ).fetchall()
    finally:
        conn.close()

    assert decision == Decision.APPROVAL_REQUIRED
    assert rows == [("approval_required", "approval_per_invocation")]


def test_verifier_role_denied_write_capability_above_r0():
    record = load_fixture("write_scratch_file_r1.yaml")  # operation: create, R1
    decision, reason = evaluate(record, agent_allowlist=[record.ref], role="verifier")
    assert decision == Decision.DENY
    assert reason == "policy_denied_verifier_write_above_r0"


def test_verifier_role_allowed_read_only_capability():
    record = load_fixture("read_file_r0.yaml")  # operation: read, R0
    decision, reason = evaluate(record, agent_allowlist=[record.ref], role="verifier")
    assert decision == Decision.ALLOW
    assert reason == "autoallow_r0"


def test_adversary_role_denied_altering_capability():
    record = load_fixture("write_scratch_file_r1.yaml")
    decision, reason = evaluate(record, agent_allowlist=[record.ref], role="adversary")
    assert decision == Decision.DENY
    assert reason == "policy_denied_adversary_altering_capability"


def test_adversary_role_allowed_read_only_capability():
    record = load_fixture("read_file_r0.yaml")
    decision, reason = evaluate(record, agent_allowlist=[record.ref], role="adversary")
    assert decision == Decision.ALLOW
    assert reason == "autoallow_r0"


def test_builder_role_unrestricted_for_write_capability():
    record = load_fixture("write_scratch_file_r1.yaml")
    decision, reason = evaluate(record, agent_allowlist=[record.ref], role="builder")
    assert decision == Decision.ALLOW
    assert reason == "approval_never"


def test_no_role_is_unrestricted_same_as_before_role_enforcement_existed():
    record = load_fixture("write_scratch_file_r1.yaml")
    decision, reason = evaluate(record, agent_allowlist=[record.ref])
    assert decision == Decision.ALLOW
    assert reason == "approval_never"


def test_evaluate_rejects_unknown_role():
    record = load_fixture("read_file_r0.yaml")
    with pytest.raises(ValueError):
        evaluate(record, agent_allowlist=[record.ref], role="not-a-real-role")


def test_authorize_records_role_in_event_payload(tmp_path):
    db_path = tmp_path / "awf.db"
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO runs (run_id, workflow_ref, status, input_json, budget_json, created_at, updated_at) "
            "VALUES ('run-1', 'wf@1.0.0#sha256:abc', 'RUNNING', '{}', '{}', 't', 't')"
        )
        conn.commit()

        record = load_fixture("write_scratch_file_r1.yaml")
        decision = authorize(
            conn,
            capability=record,
            agent_allowlist=[record.ref],
            run_id="run-1",
            actor="test-agent",
            role="verifier",
        )

        row = conn.execute(
            "SELECT reason_code, payload_json FROM events WHERE run_id = 'run-1'"
        ).fetchone()
    finally:
        conn.close()

    assert decision == Decision.DENY
    reason_code, payload_json = row
    assert reason_code == "policy_denied_verifier_write_above_r0"
    payload = json.loads(payload_json)
    assert payload["role"] == "verifier"
    assert payload["capability_ref"] == record.ref
    assert payload["risk_class"] == record.risk_class
