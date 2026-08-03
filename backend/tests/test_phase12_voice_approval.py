import pytest

from awf.cli.core_ops import CoreOpError, op_approval_approve
from awf.db.bootstrap import init_db
from awf.db.connection import get_connection
from awf.engine.run import create_run, create_step
from awf.gates.voice_approval import attempt_voice_approval, decide_voice_acknowledgement


@pytest.mark.parametrize("risk_class", ["R2", "R3"])
def test_high_risk_never_decided_by_voice_even_when_confirmed(risk_class):
    decision = decide_voice_acknowledgement(risk_class, voice_confirmed=True)
    assert decision["decided"] is False
    assert decision["requires_on_screen_confirmation"] is True


@pytest.mark.parametrize("risk_class", ["R0", "R1"])
def test_low_risk_voice_acknowledgement_allowed_when_confirmed(risk_class):
    decision = decide_voice_acknowledgement(risk_class, voice_confirmed=True)
    assert decision["decided"] is True
    assert decision["requires_on_screen_confirmation"] is False


def test_low_risk_not_decided_without_voice_confirmation():
    decision = decide_voice_acknowledgement("R0", voice_confirmed=False)
    assert decision["decided"] is False
    assert decision["requires_on_screen_confirmation"] is False


def make_conn(tmp_path):
    db_path = tmp_path / "awf.db"
    init_db(db_path)
    conn = get_connection(db_path)
    create_run(conn, run_id="run-1", workflow_ref="demo@1.0.0")
    create_step(conn, step_id="s1", run_id="run-1", node_id="n1")
    conn.execute(
        "INSERT INTO approvals (approval_id, run_id, step_id, action_digest, status, requested_at) "
        "VALUES ('ap-1', 'run-1', 's1', 'sha256:deadbeef', 'pending', '2026-01-01T00:00:00Z')"
    )
    conn.commit()
    return conn


def test_r2_approval_attempted_by_voice_stays_pending(tmp_path):
    conn = make_conn(tmp_path)

    result = attempt_voice_approval(conn, approval_id="ap-1", risk_class="R2", voice_confirmed=True)

    assert result["requires_on_screen_confirmation"] is True
    row = conn.execute("SELECT status FROM approvals WHERE approval_id = 'ap-1'").fetchone()
    assert row["status"] == "pending"


def test_r0_approval_attempted_by_voice_is_actually_approved(tmp_path):
    conn = make_conn(tmp_path)

    result = attempt_voice_approval(conn, approval_id="ap-1", risk_class="R0", voice_confirmed=True)

    assert result["status"] == "approved"
    row = conn.execute("SELECT status FROM approvals WHERE approval_id = 'ap-1'").fetchone()
    assert row["status"] == "approved"


def test_r2_approval_can_still_be_approved_via_the_real_non_voice_path(tmp_path):
    from awf.cli.core_ops import op_approval_approve

    conn = make_conn(tmp_path)

    voice_result = attempt_voice_approval(conn, approval_id="ap-1", risk_class="R2", voice_confirmed=True)
    assert voice_result["requires_on_screen_confirmation"] is True

    # A real on-screen (click/keypress) confirmation still works normally.
    screen_result = op_approval_approve(conn, approval_id="ap-1")
    assert screen_result["status"] == "approved"


def test_core_op_approve_with_voice_channel_and_r2_risk_stays_pending(tmp_path):
    # The real caller this closes: op_approval_approve itself now enforces
    # the R2+ voice-only refusal rule (Section 16.4), not just the GUI's own
    # separate TypeScript copy of it.
    conn = make_conn(tmp_path)

    result = op_approval_approve(conn, approval_id="ap-1", channel="voice", risk_class="R2")

    assert result["status"] == "pending"
    assert result["requires_on_screen_confirmation"] is True
    row = conn.execute("SELECT status FROM approvals WHERE approval_id = 'ap-1'").fetchone()
    assert row["status"] == "pending"


def test_core_op_approve_with_voice_channel_and_r0_risk_actually_approves(tmp_path):
    conn = make_conn(tmp_path)

    result = op_approval_approve(conn, approval_id="ap-1", channel="voice", risk_class="R0")

    assert result["status"] == "approved"
    row = conn.execute("SELECT status FROM approvals WHERE approval_id = 'ap-1'").fetchone()
    assert row["status"] == "approved"


def test_core_op_approve_with_voice_channel_requires_risk_class(tmp_path):
    conn = make_conn(tmp_path)

    with pytest.raises(CoreOpError):
        op_approval_approve(conn, approval_id="ap-1", channel="voice")


def test_core_op_approve_default_channel_is_unaffected(tmp_path):
    conn = make_conn(tmp_path)

    result = op_approval_approve(conn, approval_id="ap-1")

    assert result["status"] == "approved"
