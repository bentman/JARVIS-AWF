# ADR-0028: end-to-end operability

## Status

Accepted. Implemented Aug 30, 2026.

## Context

AWF already records the durable facts an operator needs: runs, steps, events,
approvals, artifacts, improvement proposals, registry inventory, readiness,
doctor checks, and local LLM status. Before this decision, those facts were
spread across separate debug-style pages and commands. Operators could inspect
state, but they still had to infer which item was blocked, which run was active,
which proposal needed review, and what exact command or click should happen
next.

That is an operability problem, not a new authority requirement. The control
surface should make AWF feel like one control center while preserving the
existing Python operations and JSON-RPC methods as the only execution path.
The first implementation pass made the state visible, but several GUI cards
still displayed commands instead of making the next operator step executable in
place. Starting work also still depended on knowing whether to use Chat,
Registry, or a CLI command.

## Decision

AWF will expose one backend-derived operator state through
`awf/control.summary` and `awf/control.runDetail`.

The summary includes:

- `operator_work_items`: typed, prioritized work items derived from existing
  durable state;
- `operator_next_actions`: the first actionable commands or decisions for the
  operator;
- `operator_start_options`: trusted runnable workflows, their source/trust
  metadata, and their input schema summaries;
- the existing runs, approvals, improvements, verdicts, registry counts,
  readiness, doctor, and LLM state.

Work items and start options include typed `primary_action` metadata. The CLI
renders those actions as exact commands. The GUI renders them as buttons and
forms wired to existing JSON-RPC methods.

Run detail includes:

- `operator_timeline`: steps, approvals, artifacts, and events in one readable
  timeline;
- run-scoped work items and next actions;
- the existing raw episodic timeline behind an advanced path.

No database schema, scheduler, approval semantic, durable authority, or daemon
is added by this decision. The presentation layer is deterministic and derived
from existing records.

## Consequences

The GUI starts from Operate, a task-flow home view. Chat remains available as
an entry point, and started runs link back to durable run state. Operate
contains a Start work panel backed by workflow registry entries, lane-based work
queues, and selected run detail. Run detail shows status, current action, steps,
approvals, artifacts, failures, verdicts, proposals, and follow-up actions
together.

The CLI and TUI render concise operator summaries by default. Raw payloads stay
available only through existing JSON paths and advanced disclosures.

Registry browsing is treated as configuration work: source and trust are visible,
selected objects have a readable summary, workflow input schemas are surfaced,
and runnable workflow refs hand off to the same Operate start flow without
making the registry browser a separate executor.

The voice runtime follows the same operator-managed artifact rule. STT does not
download models during transcription; `awf-speech models sync` is the
acquisition path, and missing local STT artifacts surface as explicit operator
errors.
