import pytest

from awf.gates.schema import Finding, FindingValidationError, Verdict
from awf.gates.verdict import build_verdict


def test_finding_rejects_invalid_role():
    with pytest.raises(FindingValidationError):
        Finding(role="builder", category="correctness", severity="low", summary="x")


def test_finding_rejects_invalid_category():
    with pytest.raises(FindingValidationError):
        Finding(role="verifier", category="not-a-category", severity="low", summary="x")


def test_finding_rejects_invalid_severity():
    with pytest.raises(FindingValidationError):
        Finding(role="verifier", category="correctness", severity="extreme", summary="x")


def test_verdict_rejects_invalid_tier():
    with pytest.raises(FindingValidationError):
        Verdict(passed=True, tier="medium-risk", findings=(), reason="x")


def test_build_verdict_passes_with_no_findings():
    verdict = build_verdict([], tier="default")
    assert verdict.passed is True
    assert verdict.findings == ()


def test_build_verdict_passes_with_only_low_severity_findings():
    finding = Finding(role="verifier", category="correctness", severity="low", summary="ok")
    verdict = build_verdict([finding], tier="default")
    assert verdict.passed is True


def test_build_verdict_fails_on_high_severity_finding():
    finding = Finding(role="verifier", category="correctness", severity="high", summary="broken")
    verdict = build_verdict([finding], tier="default")
    assert verdict.passed is False
    assert "broken" in verdict.reason


def test_build_verdict_fails_on_critical_severity_finding():
    finding = Finding(role="adversary", category="safety_gate_bypass", severity="critical", summary="bypassed")
    verdict = build_verdict([finding], tier="high-risk")
    assert verdict.passed is False


def test_verdict_to_dict_roundtrips_findings():
    finding = Finding(role="verifier", category="correctness", severity="low", summary="ok", details={"n": 1})
    verdict = build_verdict([finding], tier="default")
    d = verdict.to_dict()
    assert d["passed"] is True
    assert d["findings"] == [
        {"role": "verifier", "category": "correctness", "severity": "low", "summary": "ok", "details": {"n": 1}}
    ]
