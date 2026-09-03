# ADR-0031: minimal operator overhead and isolation alignment

## Status

Accepted. Implemented Sep 02, 2026. Aligns Section 10.4 and Section 14 of
`docs/AGENTIC_WORKFLOW_FABRIC_SPEC.md` with the single-operator repository contract.

## Context

`docs/AGENTIC_WORKFLOW_FABRIC_SPEC.md` Section 10.4 described an optional escalation
tier referencing rootless Podman/OCI containers for quarantined or advisory-adapter
execution. Section 14 described OpenTelemetry SDK instrumentation with GenAI semantic
conventions for external trace correlation.

In a single-operator local application, mandating container daemon runtimes, socket
bindings, rootless namespace mapping, or external OpenTelemetry collector processes
adds administrative complexity and maintenance drag that directly conflicts with the
core repository contract (KISS and YAGNI in `AGENTS.md`).

## Decision

1. **Isolation Standard:**
   - Dedicated Git worktrees (`cache/worktrees/<run_id>/`), ephemeral scratch paths
     (`cache/sandbox/<run_id>/`), and native CLI process sandboxes constitute the
     complete, required isolation model for all runs.
   - Any step requesting permissions or capabilities outside this boundary fails
     closed as `POLICY_DENIED` via the Capability Guard. External container daemons
     are explicitly excluded.

2. **Observability Standard:**
   - The embedded SQLite `events` ledger is the sole required and normative source
     of execution truth and timeline observability. External OpenTelemetry collector
     daemons, network exporters, and background telemetry services are excluded.

3. **Roadmap Boundary:**
   - Automation is constrained to eliminating operator friction (e.g. CI regression
     checks and proposal verification gates). Features introducing background daemon
     management or external service requirements are classified as excessive overhead
     and excluded.

## Consequences

- Zero background daemons, containers, or telemetry services are required to develop,
  test, or run AWF.
- System security remains strictly fail-closed via Capability Guard allowlists.
- All observability remains queryable via standard SQL against `data/awf_db/awf.db`.
