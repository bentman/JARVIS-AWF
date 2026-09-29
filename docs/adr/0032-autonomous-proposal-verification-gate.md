# ADR-0032: autonomous proposal verification gate

## Status

Implemented. Acceptance run: `pytest backend/tests/unit/test_eval_runner.py backend/tests/integration/test_improvement_proposals.py -q` -> 12 passed; `ruff check` passed. Refines Section 15 and Section 19 of `docs/AGENTIC_WORKFLOW_FABRIC_SPEC.md` and implements Increment 2 of `plans/remaining-gap-remediation.md`.

## Context

In the self-improvement workflow established by ADR-0021 and ADR-0022, mutating runs
execute within dedicated Git worktrees (`cache/worktrees/<run_id>/`). When an agent
submits a proposal, `awf.improvement.proposals` packages the diff, computes safety
assessments, and manages operator approval before merging into the target branch.

However, the verification gate prior to merge currently depends on manual operator
testing or upstream gate node verdicts. `awf.improvement.proposals.mark_ready` validates
that a workflow verdict artifact exists and passed (`_verdict_passed`), but there is no
autonomous mechanism that automatically executes declared regression and validation suites
directly within the candidate worktree to verify that the proposed changes do not break
the codebase.

Requiring the operator to manually switch to the candidate worktree and run test suites
by hand introduces operational friction, violating the minimal operator overhead principle
codified in ADR-0031.

## Decision

AWF implements an autonomous proposal verification runner and gates proposal merging on
immutable test-result artifacts:

1. **Evaluation Runner (`awf.eval.runner`):**
   - Provide a deterministic evaluation runner module at `backend/src/awf/eval/runner.py`.
   - The runner exposes:
     ```python
     def run_evaluation(
         repo_root: Path,
         conn: sqlite3.Connection,
         *,
         run_id: str,
         step_id: str,
         worktree: Path,
         commands: list[list[str]] | None = None,
         timeout_seconds: float = 300.0,
     ) -> dict:
     ```
   - Execution occurs strictly within the candidate `worktree` with `cwd=worktree` and
     per-command timeout enforcement.
   - If `commands` is omitted, the default validation set runs:
     - Python backend check: `[sys.executable, "scripts/validate_backend.py", "ci"]` (or targeted validation suite).

2. **Immutable `test-result` Artifact Creation:**
   - The runner records the execution transcript and verdict as a durable artifact in the
     `artifacts` table:
     - `artifact_type = 'test-result'` (already supported in the SQLite schema).
     - `media_type = 'application/json'`.
     - File written to `data/artifacts/<run_id>/test-result-<artifact_id>.json`.
   - The artifact payload structure:
     ```json
     {
       "passed": true,
       "run_id": "<run_id>",
       "candidate_commit": "<commit_hash>",
       "evaluated_at": "<iso_timestamp>",
       "commands": [
         {
           "command": ["pytest", "..."],
           "exit_code": 0,
           "duration_seconds": 12.4,
           "stdout_snippet": "...",
           "stderr_snippet": ""
         }
       ]
     }
     ```
   - Payloads are bounded to prevent SQLite and disk bloat.

3. **Enforced Merge Seam (`awf.improvement.proposals.merge`):**
   - `awf.improvement.proposals.merge` and `request_merge` enforce that a passing
     `test-result` artifact exists for `run_id` matching `candidate_commit`.
   - If no passing `test-result` artifact is found, `request_merge` and `merge` fail
     closed with `ImprovementProposalError("cannot merge proposal without passing test-result artifact")`.

4. **Operator Integration:**
   - Expose evaluation execution through `awf.ops.improvement` and CLI command
     `awf review verify <improvement_id>` / slash commands in the TUI/GUI.

## Consequences

- Self-improvement proposals cannot be merged without concrete, verifiable test execution
  in the candidate worktree.
- Eliminates manual pre-merge test execution by the operator, directly fulfilling Increment 2
  of `plans/remaining-gap-remediation.md`.
- Test execution evidence is durably recorded in SQLite and auditable via standard SQL queries.
- Zero external daemon or service dependencies are added, preserving the single-operator
  footprint defined in ADR-0031.
