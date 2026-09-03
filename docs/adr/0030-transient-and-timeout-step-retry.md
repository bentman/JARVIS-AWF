# ADR-0030: transient and timeout step retry

## Status

Accepted. Implemented Sep 02, 2026. Refines Section 13.3 of
`docs/AGENTIC_WORKFLOW_FABRIC_SPEC.md` and implements Increment 1 of
`plans/remaining-gap-remediation.md`.

## Context

Section 13.3 of `docs/AGENTIC_WORKFLOW_FABRIC_SPEC.md` defines failure classes:
`TRANSIENT, TIMEOUT, INVALID_INPUT, POLICY_DENIED, APPROVAL_REJECTED,
TOOL_ERROR, SANDBOX_VIOLATION, NONDETERMINISTIC_OUTPUT, INTEGRITY_FAILURE,
UNKNOWN_SIDE_EFFECT, INTERNAL`. It establishes that `TRANSIENT` and `TIMEOUT`
are retry-eligible by default, while all others are not. Furthermore, the SQLite
schema in `backend/src/awf/db/schema.py` has supported `'RETRY_WAIT'` as a valid
step status since Phase 0.

However, the workflow engine (`backend/src/awf/workflow/engine.py`) previously
aborted on any step exception immediately, marking the run `FAILED` without
attempting retry. Any transient model gateway rate limit, temporary socket
hiccup, or timeout would abort an entire long-running workflow.

## Decision

AWF implements step retry resilience for retry-eligible failures:

1. **Configuration:**
   - Workflows can declare a baseline retry budget in `spec.budgets.maxRetries`
     (non-negative integer, default `0`).
   - Individual nodes may declare an optional `retry` block:
     ```yaml
     retry:
       max_retries: 3
       retry_on: ["TRANSIENT", "TIMEOUT"]
       backoff_seconds: 1.0
       backoff_factor: 2.0
       jitter: true
     ```
   - If omitted on a node, `max_retries` falls back to `budgets.maxRetries`, and
     `retry_on` defaults to `["TRANSIENT", "TIMEOUT"]`.

2. **Step Attempt Tracking & Lifecycle:**
   - Each attempt is recorded as a distinct step row (`<run_id>:<node_id>#<attempt>`).
   - When an attempt fails with a failure class matching `retry_on` and attempts
     do not exceed `max_retries`:
     - The current attempt is recorded with `status = 'FAILED'` and its failure class.
     - A structured event `step_retry_scheduled` is written to `events` detailing
       `failed_attempt`, `next_attempt`, `failure_class`, and `backoff_seconds`.
     - An exponential backoff with randomized jitter is computed and waited.
     - The next attempt is created in `steps` with `status = 'RETRY_WAIT'`,
       transitioning to `status = 'RUNNING'` as execution starts.
   - If retries are exhausted or the failure class is not in `retry_on`, the Run
     transitions to `FAILED`.

3. **Crash Recovery (`awf system resume`):**
   - If an engine process crashes while waiting for retry or mid-attempt,
     `op_run_resume` clears unfinished attempts (`RUNNING` or `RETRY_WAIT`)
     for that uncompleted node from `steps` and resets the node to attempt 1
     cleanly upon resume.

## Consequences

- Workflows running against remote or local model gateways withstand transient
  network/rate-limit anomalies without failing the run.
- Tests can specify `backoff_seconds: 0.0` or override `max_retries` to remain fast
  and deterministic per AGENTS.md.
- Existing workflows with `maxRetries: 0` retain identical previous behavior.
