import json
import sqlite3

import pytest

from awf.db.bootstrap import init_db
from awf.guard.capability_guard import Decision, authorize, evaluate
from awf.registry.capability_record import (
    CapabilityRecordValidationError,
    load_capability_record,
    parse_capability_record,
)


@pytest.fixture
def load_fixture(fixtures_dir):
    def _load(name: str):
        return load_capability_record(fixtures_dir / "guard_registry" / "capabilities" / name / "1.0.0.yaml")

    return _load


def test_load_r0_capability_record(load_fixture):
    record = load_fixture("read_file")
    assert record.identity.name == "read_file"
    assert record.risk_class == "R0"
    assert record.ref == "read_file@1.0.0"


@pytest.mark.parametrize(
    "name,expected_provider,expected_risk_class",
    [
        ("hardware_probe", "awf", "R0"),
        ("gpu_utilization_sample", "awf", "R0"),
        ("claude_code_invoke", "claude-code", "R1"),
        ("codex_invoke", "codex", "R1"),
        ("antigravity_invoke", "antigravity", "R1"),
        ("copilot_invoke", "copilot", "R1"),
        ("cline_invoke", "cline", "R1"),
        ("llm_complete", "awf", "R1"),
    ],
)
def test_load_shipped_adr0009_capability_records(repo_root, name, expected_provider, expected_risk_class):
    record = load_capability_record(repo_root / "config" / "app_registry" / "capabilities" / name / "1.0.0.yaml")
    assert record.identity.name == name
    assert record.identity.provider == expected_provider
    assert record.risk_class == expected_risk_class
    assert record.approval == "never"
    assert record.ref == f"{name}@1.0.0"


def test_load_rejects_missing_field():
    with pytest.raises(CapabilityRecordValidationError):
        parse_capability_record({"identity": {"type": "activity"}})


def test_load_rejects_invalid_risk_class():
    with pytest.raises(CapabilityRecordValidationError):
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
        ("read_file", Decision.ALLOW),
        ("write_scratch_file", Decision.ALLOW),
        ("git_push", Decision.APPROVAL_REQUIRED),
        ("modify_capability_registry", Decision.DENY),
    ],
)
def test_evaluate_decision_per_risk_class_when_allowlisted(fixture, expected, load_fixture):
    record = load_fixture(fixture)
    decision, _reason = evaluate(record, agent_allowlist=[record.ref])
    assert decision == expected


def test_evaluate_denies_when_not_in_allowlist(load_fixture):
    record = load_fixture("read_file")
    decision, reason = evaluate(record, agent_allowlist=[])
    assert decision == Decision.DENY
    assert reason == "not_in_agent_allowlist"


def test_evaluate_is_pure_and_deterministic(load_fixture):
    record = load_fixture("git_push")
    first = evaluate(record, agent_allowlist=[record.ref])
    second = evaluate(record, agent_allowlist=[record.ref])
    assert first == second == (Decision.APPROVAL_REQUIRED, "approval_per_invocation")


def test_authorize_writes_decision_event_before_use(tmp_path, load_fixture):
    db_path = tmp_path / "awf.db"
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO runs (run_id, workflow_ref, status, input_json, budget_json, created_at, updated_at) "
            "VALUES ('run-1', 'wf@1.0.0#sha256:abc', 'RUNNING', '{}', '{}', 't', 't')"
        )
        conn.commit()

        record = load_fixture("git_push")
        decision = authorize(
            conn,
            capability=record,
            agent_allowlist=[record.ref],
            run_id="run-1",
            actor="test-agent",
        )

        rows = conn.execute("SELECT new_status, reason_code FROM events WHERE run_id = 'run-1'").fetchall()
    finally:
        conn.close()

    assert decision == Decision.APPROVAL_REQUIRED
    assert rows == [("approval_required", "approval_per_invocation")]


def test_verifier_role_denied_write_capability_above_r0(load_fixture):
    record = load_fixture("write_scratch_file")  # operation: create, R1
    decision, reason = evaluate(record, agent_allowlist=[record.ref], role="verifier")
    assert decision == Decision.DENY
    assert reason == "policy_denied_verifier_write_above_r0"


def test_verifier_role_allowed_read_only_capability(load_fixture):
    record = load_fixture("read_file")  # operation: read, R0
    decision, reason = evaluate(record, agent_allowlist=[record.ref], role="verifier")
    assert decision == Decision.ALLOW
    assert reason == "autoallow_r0"


def test_adversary_role_denied_altering_capability(load_fixture):
    record = load_fixture("write_scratch_file")
    decision, reason = evaluate(record, agent_allowlist=[record.ref], role="adversary")
    assert decision == Decision.DENY
    assert reason == "policy_denied_adversary_altering_capability"


def test_adversary_role_allowed_read_only_capability(load_fixture):
    record = load_fixture("read_file")
    decision, reason = evaluate(record, agent_allowlist=[record.ref], role="adversary")
    assert decision == Decision.ALLOW
    assert reason == "autoallow_r0"


def test_builder_role_unrestricted_for_write_capability(load_fixture):
    record = load_fixture("write_scratch_file")
    decision, reason = evaluate(record, agent_allowlist=[record.ref], role="builder")
    assert decision == Decision.ALLOW
    assert reason == "approval_never"


def test_no_role_is_unrestricted_same_as_before_role_enforcement_existed(load_fixture):
    record = load_fixture("write_scratch_file")
    decision, reason = evaluate(record, agent_allowlist=[record.ref])
    assert decision == Decision.ALLOW
    assert reason == "approval_never"


def test_evaluate_rejects_unknown_role(load_fixture):
    record = load_fixture("read_file")
    with pytest.raises(ValueError):
        evaluate(record, agent_allowlist=[record.ref], role="not-a-real-role")


def test_authorize_records_role_in_event_payload(tmp_path, load_fixture):
    db_path = tmp_path / "awf.db"
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO runs (run_id, workflow_ref, status, input_json, budget_json, created_at, updated_at) "
            "VALUES ('run-1', 'wf@1.0.0#sha256:abc', 'RUNNING', '{}', '{}', 't', 't')"
        )
        conn.commit()

        record = load_fixture("write_scratch_file")
        decision = authorize(
            conn,
            capability=record,
            agent_allowlist=[record.ref],
            run_id="run-1",
            actor="test-agent",
            role="verifier",
        )

        row = conn.execute("SELECT reason_code, payload_json FROM events WHERE run_id = 'run-1'").fetchone()
    finally:
        conn.close()

    assert decision == Decision.DENY
    reason_code, payload_json = row
    assert reason_code == "policy_denied_verifier_write_above_r0"
    payload = json.loads(payload_json)
    assert payload["role"] == "verifier"
    assert payload["capability_ref"] == record.ref
    assert payload["risk_class"] == record.risk_class
