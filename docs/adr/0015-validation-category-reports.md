# ADR-0015: validation-category reports and live per-test status

## Status

Implemented.

Bootstrap wrappers also write durable diagnostic transcripts:
`scripts/bootstrap.sh` and `scripts/bootstrap.ps1` create
`reports/diagnostics/<datetime>-bootstrap.txt` before setup work starts and
capture the full console output, including `awf.setup --provision`,
`--install`, `--verify`, model sync/verify, doctor output, failures, and the
next operator command.

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

Every report header records UTC start time, validation command,
provisioning-derived `host_class_id`, pytest command, pytest return code, and
harness return code. The host class uses the same `collect_inventory()` plus
`explain_ort_extra()` decision as `awf-setup --provision`, mapped to the
canonical profile suffix (`cpu`, `cuda`, `gpu`, or `qnn`). This keeps report
classification aligned with the dependency extra the operator would install;
it does not treat per-function runtime readiness as a provisioning decision.
If the provisioning inventory cannot resolve the host, the header records a
short `unresolved:<ExceptionClass>` value without changing the command's
existing failure semantics.

The `profile` diagnostic records the selected extra and its reason, followed
by the separate runtime-readiness profile/evidence when it can be resolved.
That distinction makes a restricted execution environment visible without
misclassifying the host selected by the provisioning probe.

The bootstrap diagnostic is intentionally wrapper-scoped rather than a new
`awf-setup` flag: it records the complete operator path around setup, including
venv creation, pip output, frontend install output when present, and the final
doctor report.

At the end of every harness invocation, the report root is pruned per folder:
only the newest 35 `.txt` files in each directory under `reports/` are kept.
This bounds local evidence storage without mixing diagnostics, validation, or
future report categories.

## Consequences

Test selection, marker expressions, cache location, and the shared exit-code
contract remain unchanged. `backend/tests/conftest.py` remains focused on test
fixtures and SQLite speed; reporting stays in the named harness so direct
pytest use is unaffected. This ADR supersedes ADR-0006 only where its
regression-only report format conflicts with the common category-report
format.
