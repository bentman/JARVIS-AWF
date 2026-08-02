"""Finding/Verdict schema (Section 12.3).

Persisted as Artifacts (`artifact_type`: `finding` | `verdict`, Section 8) -
never as summarized agent prose, and never written by the Builder.
"""

from dataclasses import dataclass, field

FINDING_ROLES = ("verifier", "adversary")
FINDING_CATEGORIES = (
    "correctness",
    "resource_safety",
    "safety_gate_bypass",
    "memory_contamination",
    "other",
)
FINDING_SEVERITIES = ("low", "medium", "high", "critical")

# A Finding at or above this severity fails the Verdict (Section 12.3).
FAILING_SEVERITIES = ("high", "critical")

GATE_TIERS = ("default", "high-risk")


class FindingValidationError(ValueError):
    pass


@dataclass(frozen=True)
class Finding:
    role: str
    category: str
    severity: str
    summary: str
    details: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.role not in FINDING_ROLES:
            raise FindingValidationError(f"role '{self.role}' not in {FINDING_ROLES}")
        if self.category not in FINDING_CATEGORIES:
            raise FindingValidationError(f"category '{self.category}' not in {FINDING_CATEGORIES}")
        if self.severity not in FINDING_SEVERITIES:
            raise FindingValidationError(f"severity '{self.severity}' not in {FINDING_SEVERITIES}")

    def to_dict(self) -> dict:
        return {
            "role": self.role,
            "category": self.category,
            "severity": self.severity,
            "summary": self.summary,
            "details": self.details,
        }


@dataclass(frozen=True)
class Verdict:
    passed: bool
    tier: str
    findings: tuple[Finding, ...]
    reason: str

    def __post_init__(self) -> None:
        if self.tier not in GATE_TIERS:
            raise FindingValidationError(f"tier '{self.tier}' not in {GATE_TIERS}")

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "tier": self.tier,
            "reason": self.reason,
            "findings": [f.to_dict() for f in self.findings],
        }
