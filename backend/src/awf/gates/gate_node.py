"""Trifecta gate node executor (Section 12.3) for the Phase 7 workflow engine.

Default tier: Builder + Verifier only (Adversary/Optimizer omitted). The
Verifier MAY use the same model family as the Builder. High-risk tier: full
Trifecta - Builder, Verifier, and Adversary/Optimizer all produce structured
Findings before a Verdict is issued. In both tiers, the Verdict is written
by this deterministic module, never by the Builder or by summarizing prose.

A `safety_gate_bypass` Finding is a terminal failure: it fails the Run
immediately without consuming one of the bounded repair loop's iterations
(Section 12.3: "does not consume one of the 3 repair iterations").
"""

import sqlite3
from pathlib import Path
from typing import Callable

from awf.engine.executor import run_step
from awf.gates.adversary import (
    check_memory_contamination,
    check_resource_safety,
    check_safety_gate_bypass,
)
from awf.gates.artifacts import write_finding_artifact, write_verdict_artifact
from awf.gates.schema import Finding
from awf.gates.verdict import build_verdict
from awf.gates.verifier import run_verifier_check


def make_trifecta_gate_executor(
    *,
    check_fn: Callable[[], bool],
    check_summary: str,
    artifacts_root: Path,
    tier: str = "default",
    cache_sandbox_dir: Path | None = None,
    guard_bypassed: bool = False,
):
    def executor(conn: sqlite3.Connection, run_id: str, step_id: str, node: dict) -> dict:
        def fn(_payload: dict) -> dict:
            findings: list[Finding] = [run_verifier_check(check_fn, summary=check_summary)]
            terminal_failure = False

            if tier == "high-risk":
                adversary_findings = [
                    check_resource_safety(),
                    check_safety_gate_bypass(guard_bypassed),
                    check_memory_contamination(conn, run_id, cache_sandbox_dir)
                    if cache_sandbox_dir is not None
                    else None,
                ]
                for finding in adversary_findings:
                    if finding is not None:
                        findings.append(finding)
                        if finding.category == "safety_gate_bypass":
                            terminal_failure = True

            verdict = build_verdict(findings, tier=tier)

            for finding in findings:
                write_finding_artifact(
                    conn, artifacts_root=artifacts_root, run_id=run_id, step_id=step_id, finding=finding
                )
            verdict_artifact_id = write_verdict_artifact(
                conn, artifacts_root=artifacts_root, run_id=run_id, step_id=step_id, verdict=verdict
            )

            return {
                "passed": verdict.passed,
                "terminal_failure": terminal_failure,
                "verdict_artifact_id": verdict_artifact_id,
                "reason": verdict.reason,
            }

        return run_step(conn, step_id=step_id, run_id=run_id, fn=fn, input_payload={})

    return executor
