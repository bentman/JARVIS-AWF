# ADR-0029: one operator surface

## Status

Accepted. Implemented Aug 30, 2026. Supersedes Sections 16.1 and 16.2 of
`docs/AGENTIC_WORKFLOW_FABRIC_SPEC.md` on the shape of the operator surface.

## Context

ADR-0028 made operator state visible and actionable. What it did not change was
the size of the surface an operator has to learn before that state is reachable.

The `awf` CLI exposed 22 top-level commands across 47 command paths, with no
help text on any of them: `awf --help` printed a brace-list of names and
nothing else. The TUI listed 51 slash commands in one flat alphabetical block.
The GUI carried seven navigation views. Several concepts were spelled more than
once - `improvement` and `proposal` were two proposal systems with overlapping
verbs, `approvals`/`approval`/`approve`/`reject` were four top-level commands
for one decision, and the GUI kept Runs, Approvals, and Proposals as separate
destinations even though Operate's queue already surfaced all three.

Section 16.1 named thirteen commands and Section 16.2 named the TUI built-ins.
Those lists were the surface, not a floor beneath a larger one, so reducing the
surface means replacing them.

## Decision

AWF presents one operator surface, organized by what an operator is doing
rather than by which subsystem owns the record. The command names in Sections
16.1 and 16.2 are replaced, not aliased: a retired spelling is an error, and
its error names no substitute, because the help output is the substitute.

The CLI is eight top-level commands:

| Command | Covers |
|---|---|
| `awf run` | start a workflow |
| `awf status` | the run list, one run's detail, and `--artifacts` |
| `awf control` | what needs action, and the command for each |
| `awf doctor` | install health |
| `awf review` | approvals, proposed code changes, drafted registry objects |
| `awf registry` | published object lifecycle |
| `awf memory` | semantic memory, sessions, episodic events |
| `awf system` | readiness, resume, llm, secret, serve |

`awf review` is the single place a decision is made: it resolves an id to an
approval, a proposed code change, or a drafted registry object and acts on
whichever it finds, so the operator does not have to know which subsystem
issued the id. `awf review approve` on a non-approval names the command that
does apply. Every command and shared argument carries help text, and
`awf --help` opens with the operating loop.

The TUI mirrors those groups. `/review`, `/memory`, and `/system` take
subcommands with the same names as their CLI counterparts, `/status` with no
argument lists runs, and `/help` is grouped by task with a "Start here"
section. A command that `/help` does not list is not dispatchable; the flat
spellings the grouped commands resolve to internally are not typeable.

The GUI presents three destinations - Operate, Chat, Library. Operate carries
the work queue, start-work panel, selected run detail, approvals, proposals,
run history, and system overview in urgency order. Library carries the registry
browser and memory curation.

## Consequences

Retired spellings fail. `awf approvals`, `awf approve`, `awf reject`,
`awf artifacts`, `awf runs`, `awf resume`, `awf readiness`, `awf llm ...`,
`awf secret ...`, `awf serve --stdio`, `awf improvement ...`,
`awf proposal ...`, `awf author workflow`, `awf session ...`, and
`awf episodic ...` are argparse errors. Anything that invoked them - an
operator's shell history, a script, a scheduler entry - must move to the
replacement. `backend/tests/integration/test_cli_main.py` pins each retired
spelling to its replacement so the move stays recorded and testable.

`awf serve --stdio` is now `awf system serve --stdio`, and
`frontend/shared/src/transport.ts` spawns the core with the new path. A
frontend built before this change cannot start a backend after it.

Phase 10 and Phase 11 acceptance must be re-derived against the table above:
the operations those phases exercise are unchanged, but the commands that
invoke them are not. This ADR is the authority for what those phases run.

JSON-RPC method names are unchanged. `cli_path` metadata in
`awf.protocol.methods` points at the consolidated paths, and the argparse
parity check still verifies that every method's CLI metadata resolves to a real
parser path with matching arguments.

Commands the backend emits as next actions name the consolidated spellings, so
what `awf control` prints is what an operator can paste.

Where this ADR and Sections 16.1 or 16.2 disagree, this ADR governs. Those
sections describe the surface as it stood before this decision.
