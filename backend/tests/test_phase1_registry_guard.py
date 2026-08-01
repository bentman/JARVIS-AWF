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
    assert first == second


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
