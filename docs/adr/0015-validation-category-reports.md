# ADR-0015: validation-category reports and live per-test status

## Status

Implemented.

## Context

ADR-0006 created the backend validation harness and durable reports, but only
the `profile` and `regression` commands wrote reports. The other test
categories captured pytest until completion and emitted quiet progress dots,
which did not provide durable evidence or a readable per-test status stream.

## Decision

Every test-running harness command (`unit`, `integration`, `runtime`,
`regression`, and `ci`) writes one UTC-timestamped report under
`reports/validation/`. `profile` continues to write its diagnostic report
under `reports/diagnostics/`.

The harness runs pytest in verbose mode and streams its combined terminal
output while retaining the same transcript in the category report. Pytest's
standard verbose lines provide the node ID, cumulative progress, and result
for each test. The harness appends a normalized final summary with the
validator outcome and counts for passed, failed, skipped, deselected, errors,
and warnings; pytest's detailed failure, warning, and skip sections remain
verbatim in the transcript.

Every report header records UTC start time, validation command, canonical
`host_class_id`, pytest command, pytest return code, and harness return code.
If the hardware profiler cannot resolve the host, the header records a short
`unresolved:<ExceptionClass>` value without changing the command's existing
failure semantics.

## Consequences

Test selection, marker expressions, cache location, and the shared exit-code
contract remain unchanged. `backend/tests/conftest.py` remains focused on test
fixtures and SQLite speed; reporting stays in the named harness so direct
pytest use is unaffected. This ADR supersedes ADR-0006 only where its
regression-only report format conflicts with the common category-report
format.
