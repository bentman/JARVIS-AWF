from pathlib import Path

from awf.db.bootstrap import init_db
from awf.db.connection import get_connection
from awf.engine.run import create_run
from awf.gates.adversary import (
    check_memory_contamination,
    check_resource_safety,
    check_safety_gate_bypass,
)
from awf.gates.verifier import run_verifier_check
from awf.hardware.gpu_sampler import GpuSamplerUnavailable


def test_verifier_check_pass_yields_low_severity_finding():
    finding = run_verifier_check(lambda: True, summary="add(2,3)==5")
    assert finding.role == "verifier"
    assert finding.category == "correctness"
    assert finding.severity == "low"


def test_verifier_check_fail_yields_high_severity_finding():
    finding = run_verifier_check(lambda: False, summary="add(2,3)==5")
    assert finding.severity == "high"
    assert "FAILED" in finding.summary


def test_safety_gate_bypass_none_when_not_bypassed():
    assert check_safety_gate_bypass(False) is None


def test_safety_gate_bypass_critical_when_bypassed():
    finding = check_safety_gate_bypass(True, detail="prompt injection succeeded")
    assert finding.category == "safety_gate_bypass"
    assert finding.severity == "critical"


def test_resource_safety_returns_none_when_sampler_unavailable(monkeypatch):
    def raise_unavailable():
        raise GpuSamplerUnavailable("no gpu")

    monkeypatch.setattr("awf.gates.adversary.sample_gpu_utilization", raise_unavailable)
    assert check_resource_safety() is None


def test_resource_safety_flags_utilization_over_ceiling(monkeypatch):
    monkeypatch.setattr("awf.gates.adversary.sample_gpu_utilization", lambda: 0.9)
    finding = check_resource_safety()
    assert finding.category == "resource_safety"
    assert finding.severity == "high"


def test_resource_safety_none_when_under_ceiling(monkeypatch):
    monkeypatch.setattr("awf.gates.adversary.sample_gpu_utilization", lambda: 0.1)
    assert check_resource_safety() is None


def make_conn(tmp_path):
    db_path = tmp_path / "awf.db"
    init_db(db_path)
    conn = get_connection(db_path)
    create_run(conn, run_id="run-1", workflow_ref="demo@1.0.0")
    create_run(conn, run_id="run-other", workflow_ref="demo@1.0.0")
    return conn


def test_memory_contamination_none_when_dir_missing(tmp_path):
    conn = make_conn(tmp_path)
    assert check_memory_contamination(conn, "run-1", tmp_path / "does-not-exist") is None


def test_memory_contamination_none_when_clean(tmp_path):
    conn = make_conn(tmp_path)
    sandbox_dir = tmp_path / "sandbox" / "run-1"
    sandbox_dir.mkdir(parents=True)
    (sandbox_dir / "own_file.txt").write_text("x")
    assert check_memory_contamination(conn, "run-1", sandbox_dir) is None


def test_memory_contamination_flags_cross_run_artifact(tmp_path):
    conn = make_conn(tmp_path)
    sandbox_dir = tmp_path / "sandbox" / "run-1"
    sandbox_dir.mkdir(parents=True)
    (sandbox_dir / "run-other_leftover.txt").write_text("x")

    finding = check_memory_contamination(conn, "run-1", sandbox_dir)
    assert finding.category == "memory_contamination"
    assert finding.severity == "high"
