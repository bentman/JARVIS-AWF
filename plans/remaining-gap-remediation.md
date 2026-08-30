# Plan: Engine Resilience, CI, and Proposal Checks

## Scope

Three increments for the AWF backend and repository automation. Each
increment declares its dependency, targets, and exit conditions. An
increment is complete only when its exit conditions are verified.

## 1. Transient step retry

Requirement: a Step that fails with failure class `TRANSIENT` is retried
automatically instead of failing the Run.

- Owner: `backend/src/awf/workflow/engine.py` (retry control),
  `backend/src/awf/workflow/definition.py` (configuration).
- Mechanism: on `StepFailure` with `failure_class == "TRANSIENT"`, the
  engine re-executes the same node with `attempt + 1`, up to the
  workflow's `maxRetries` (optional integer, default `0`, meaning no
  retry — the current behavior). Exhausting `maxRetries` follows the
  existing FAILED path. Each retry writes a `step_retry_scheduled`
  event.
- Dependency: none (uses the existing `TRANSIENT` failure class and
  `RETRY_WAIT` status in `db/schema.py`).
- Exit conditions:
  - New `backend/tests/integration/test_engine_transient_retry.py`
    passes, covering: transient failure then success (step has two
    attempts, Run SUCCEEDED); retries exhausted (Run FAILED with one
    `step_retry_scheduled` event per attempt); non-TRANSIENT failure
    (no retry, existing behavior).
  - `scripts/validate_backend.py regression` reports PASS.

## 2. CI workflow

Requirement: the backend and frontend test suites run automatically on
every push and pull request.

- Owner: `.github/workflows/ci.yml` (new file); existing commands only,
  no new logic.
- Mechanism:
  - `backend` job (ubuntu-latest, Python 3.12): install
    `backend[dev]` per `backend/pyproject.toml`, run
    `scripts/validate_backend.py ci`, upload the generated
    `reports/validation/*-ci.txt` as a workflow artifact.
  - `frontend` job (ubuntu-latest, Node 22): `npm ci` in `frontend/`,
    run `npm test --workspaces --if-present`.
- Dependency: none.
- Exit conditions:
  - A run on a non-`main` branch passes both jobs.
  - A deliberately broken test produces a red run; reverting restores
    green.

## 3. Proposal check gate

Requirement: an improvement proposal whose manifest names a check set
merges only when all named checks pass against the candidate worktree.

- Owner: `backend/src/awf/eval/runner.py` (check execution, new module),
  `backend/src/awf/improvement/proposals.py` (merge gating).
- Mechanism: the runner executes the proposal's declared list of
  deterministic shell/pytest commands in the candidate worktree, records
  each result, and writes one `test-result` artifact (artifact type
  already defined in `db/schema.py`). The merge step in
  `improvement/proposals.py` requires a passing artifact before the
  existing merge path runs. No new registry kind; no model-graded
  checks.
- Dependency: none, but scheduled after Increments 1 and 2.
- Exit conditions:
  - Unit test: runner passes/fails correctly on passing and failing
    check sets; artifact row of type `test-result` is written.
  - Integration test: merge is refused without a passing artifact and
    proceeds with one.


