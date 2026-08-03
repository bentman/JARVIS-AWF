"""Verifier role (Section 12.3): runs regression tests against the Builder's
candidate artifacts and produces a structured Finding.

`run_verifier_check` is the deterministic-test-execution half of the
Verifier's obligation. `run_llm_review` is the other half - an independent
LLM-driven review, routed through the Model Gateway (Section 11) via a
`purpose: judge` Model Profile, never the same model call that produced the
candidate. Both produce the same structured Finding contract; a gate MAY use
either or both.
"""

import sqlite3
from typing import Callable

from awf.gateway.client import complete
from awf.gates.schema import Finding
from awf.registry.model_profile import ModelProfile

REVIEW_SYSTEM_PROMPT = (
    "You are an independent code reviewer with no knowledge of how this candidate "
    "was produced. Reply with exactly one line: 'PASS: <one-line reason>' if the "
    "change looks correct, or 'FAIL: <one-line reason>' if it does not."
)


def run_verifier_check(check_fn: Callable[[], bool], *, summary: str) -> Finding:
    passed = bool(check_fn())
    return Finding(
        role="verifier",
        category="correctness",
        severity="low" if passed else "high",
        summary=summary if passed else f"FAILED: {summary}",
        details={"passed": passed},
    )


def run_llm_review(
    profile: ModelProfile,
    *,
    candidate_summary: str,
    conn: sqlite3.Connection | None = None,
    secret_key: bytes | None = None,
) -> Finding:
    messages = [
        {"role": "system", "content": REVIEW_SYSTEM_PROMPT},
        {"role": "user", "content": candidate_summary},
    ]
    response = complete(profile, messages, conn=conn, secret_key=secret_key).strip()
    passed = response.upper().startswith("PASS")
    model = profile.candidates[0].litellm_model if profile.candidates else None
    return Finding(
        role="verifier",
        category="correctness",
        severity="low" if passed else "high",
        summary=response,
        details={"passed": passed, "model": model},
    )
