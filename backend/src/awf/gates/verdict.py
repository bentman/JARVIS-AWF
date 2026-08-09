"""Deterministic Verdict aggregation (Section 12.3).

The Builder MUST NOT issue the Verdict - this is the only place a Verdict is
produced, aggregated purely from structured Finding records, never by
summarizing any agent's prose.
"""

from awf.gates.schema import FAILING_SEVERITIES, Finding, Verdict


def build_verdict(findings: list[Finding], *, tier: str) -> Verdict:
    failing = [f for f in findings if f.severity in FAILING_SEVERITIES]
    passed = not failing
    reason = "no high/critical findings" if passed else "; ".join(f"{f.category}:{f.summary}" for f in failing)
    return Verdict(passed=passed, tier=tier, findings=tuple(findings), reason=reason)
