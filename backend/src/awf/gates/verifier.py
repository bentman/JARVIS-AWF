"""Verifier role (Section 12.3): runs regression tests against the Builder's
candidate artifacts and produces a structured Finding.

This implements the deterministic-test-execution half of the Verifier's
obligation ("runs regression tests ... produces structured Finding
records"). An LLM-driven independent code-review pass is not built here -
that would layer an `agent` invocation (role=verifier, read-only
constraints) on top of this same Finding-producing contract in a later pass.
"""

from typing import Callable

from awf.gates.schema import Finding


def run_verifier_check(check_fn: Callable[[], bool], *, summary: str) -> Finding:
    passed = bool(check_fn())
    return Finding(
        role="verifier",
        category="correctness",
        severity="low" if passed else "high",
        summary=summary if passed else f"FAILED: {summary}",
        details={"passed": passed},
    )
