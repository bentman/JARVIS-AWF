# ADR-0026: the run speaks and the mind remembers

## Status

Accepted.

Implemented on 2026-08-14 in branch
`adr/0026-the-run-speaks-and-the-mind-remembers`. The implementation keeps
`awf/events.subscribe` as snapshot polling, persists bounded agent output in
step output, reuses the existing approval record/action-preview bridge for
agent approvals, makes the assistant read recent session and memory context,
and applies the adjacent Windows/SQLite/pathing correctness fixes described
below.

Change entry, 2026-08-14: final implementation alignment records that the
shared adapter runner preserves each adapter's existing command-line prompt
delivery rather than moving prompts to stdin/temp files; CLI and GUI status
surfaces gained readable summaries and post-request run detail, but continuous
frontend polling during an in-flight `run.start` remains deferred. Related ADR
corrections from this pass: ADR-0021 now notes that ADR-0026 extends the
approval bridge to agent nodes, while ADR-0023's SpeechRecognition caveat,
ADR-0024's snapshot-only `events.subscribe`, ADR-0017's resident-mind/default
assistant state, and ADR-0018/0020 memory-envelope notes already match current
repo truth.

This record was produced from an external code audit of the repository at
commit `e126629` (four independent review passes: engine/adapters/gates,
cognition/memory/registry, frontend surfaces, repository practices). Every
claim below cites the file and line it was observed at. Where this record and
the source disagree, re-verify against the source before implementing.

## Context

The fabric's durable core is sound. `engine/executor.py` genuinely enforces
the never-leave-a-Step-RUNNING rule, the Capability Guard is a pure testable
chokepoint, danger-flag refusals are enforced in code in all five adapters,
and ADR-0018's envelope ordering ships exactly as specified. The clunkiness an
operator feels is not the architecture — it is that the system does the work
and then does not say what it did.

Four observations define the decision boundary.

**The run is mute.** `engine/agent_step.py:552` persists only
`{"status", "termination_reason"}` as the step output; the adapter's
`result.output` — the agent's actual answer — plus `usage`, `findings`, and
`artifact_candidates` (declared in `adapters/base.py:39-41`) are dropped on
the floor. Downstream nodes cannot consume what the agent produced, and
`awf status` after a successful run shows nothing the agent said.
Meanwhile the frontends have no progress surface at all: `op_run_start`
(`cli/core_ops.py:584-618`) executes the whole workflow inside one request,
and although `awf/events.subscribe` is implemented end-to-end
(`server/stdio.py:281-282`, `shared/src/client.ts:335-337`), it has zero
callers in either frontend. During an agent step the operator sees a disabled
button or `working...` — no steps, no status, no output. Most slash commands
(`/approvals`, `/control`, `/llm`, `/memory-search`, …) render
`JSON.stringify(..., 2)` into the transcript (`cli/src/App.tsx:80-81`), and
the GUI renders readiness, run timelines, and registry results as raw JSON in
`<pre>` blocks (`Overview.tsx:69-113`, `RunsView.tsx:129`).

**Failure is illegible.** A missing agent CLI — the most likely first-run
failure — propagates `FileNotFoundError` from a bare `subprocess.run`
(`adapters/claude_code.py:47` and its four siblings) and is recorded as
failure class `INTERNAL` with message `[Errno 2] No such file or directory`.
No `shutil.which` preflight exists at invocation time, even though
`op_system_doctor` already probes all five CLIs (`core_ops.py:1836-1856`).
On the frontend, `transport.ts:26-41` registers no `child.on("error")`
handler and never reads the child's stderr, so a missing backend kills the
CLI/GUI with a raw ENOENT stack trace; `ProtocolClient.call`
(`client.ts:76-84`) has no timeout, so a wedged backend shows `working...`
forever. Dropped MCP refs are silent: `_resolve_mcp_servers` skips untrusted
refs and `_allowed_mcp_tools` swallows all exceptions
(`agent_step.py:116-143`), so a misconfigured capability record strips an
agent's tools with no event saying so.

**The mind is stateless.** `workflow/activities.py:47-57` builds the
assistant reply from exactly two segments: application instruction plus raw
user text. It never calls `retrieve_memory_context`, never compiles a
persona, and never reads `active_session_entries` — even though
`op_voice_submit_text` (`core_ops.py:1529-1536`) dutifully records every
utterance and response into the session store. The assistant cannot remember
the previous turn of its own conversation. ADR-0020's session tier is written
and never read; `summarize_session` (`memory/sessions.py:58-71`) computes a
summary and discards it. Persona `example_messages` and `generation` params
are validated as mandatory (`registry/persona.py:160-165`) and then 100%
discarded — the only renderer honoring them, `render_chat`, has no production
caller. What memory context *is* injected into agent steps is low-quality:
`memory/context.py:33-45` compares characters against a token budget, `break`s
on the first oversized memory (starving all later ones), and injects raw
`json.dumps` of dataclass dicts — digests, trust status, provenance — as
prompt material.

**Approval semantics fork.** A capability that resolves to
`APPROVAL_REQUIRED` on a machine activity parks the run in
`WAITING_APPROVAL` and waits for the operator
(`machine/approvals.py:70-94`). The identical capability on an `agent` node
raises `POLICY_DENIED` and fails the run (`agent_step.py:486-490`). At the
decision point, the GUI's always-on-top confirmation renders only the opaque
digest and risk class (`ApprovalConfirmation.tsx:34-50`) while the
human-readable action preview lives in a different view; the CLI's
`/approve <id>` executes with no digest or preview shown at all.

A fifth observation is the enabler: roughly 60% of each adapter is
copy-paste. `_parse_events` is byte-identical in three adapters, the
`subprocess.run` + timeout block appears five times, and
`DEFAULT_TIMEOUT_SECONDS = 300` is defined five times, while
`adapters/base.py` holds only two dataclasses. Every fix above that touches
invocation would otherwise be written five times.

## Decision

**One shared adapter runner.** `adapters/base.py` gains
`run_cli(argv, invocation, *, extra_env) -> AgentResult | CompletedProcess`
and a shared `parse_jsonl_events`. The runner owns: env merge,
`stdin=subprocess.DEVNULL` (today the Claude adapter alone omits it,
`claude_code.py:47-54`), process-group cleanup on timeout (today
`subprocess.run(timeout=...)` can orphan agent-spawned grandchildren that keep
writing into the worktree after the step is recorded), and
`FileNotFoundError` caught and returned as
`AgentResult(FAILED, ...)` with a termination reason naming the missing CLI
and the `awf doctor` remedy. Each adapter keeps its current
command flags and prompt-delivery shape; avoiding Windows command-line length
limits by moving large envelopes to stdin or temp files remains a future
adapter-contract refinement.

**The run speaks.** The agent step persists a bounded result text and
`usage` into the step output and `node_output_context`, spilling large
payloads to an artifact exactly as `machine/activities.py:263-273` already
does for command output. `response_text` surfaces the agent's answer in chat
and `awf status`. Every silently dropped MCP ref writes a `mcp_ref_skipped`
event carrying the reason. A run that returns `WAITING_INPUT` persists that
status to the `runs` table (today `workflow/engine.py:336-337` returns it
without writing it, so an exhausted handoff shows `RUNNING` forever).

**The run shows progress through status surfaces.** The already-shipped
`awf/events.subscribe` stays a request/response snapshot endpoint, and
`awf/run.status` plus run outcome responses carry step/output detail suitable
for CLI and GUI summaries. The transport gains a `child.on("error")` handler
with a readable `failed to start awf core` message, stderr capture, and
per-call timeouts with method-aware defaults. Slash-command and GUI output
move from broad `JSON.stringify`/`<pre>` rendering toward focused formatters
for approvals, control, LLM status, memory search, run status, and event/run
snapshots; raw payloads remain available on JSON-oriented paths. `COMMAND_NAMES`
is derived from `HELP_TEXT` so autocomplete stays aligned with the help text.
True live frontend polling while a synchronous `run.start` request is still
executing remains deferred until the frontend run-start path is split into
start-and-poll or another async interaction shape. Server-push streaming
remains parked where ADR-0024 left it.

**The mind remembers.** `_assistant_reply` resolves the voice profile's
persona via `compile_persona`, appends recent session entries as
`session/context` segments, and calls `retrieve_memory_context` on the
objective — every component already exists and is tested; only the wiring is
absent, and ADRs 0018/0020 already promise it. Memory context rendering
becomes compact lines (`subject predicate value (confidence)` for semantic,
`reason_code @ workflow/node` for episodic) instead of serialized dataclasses;
the budget uses a chars/4 token estimate and `continue` rather than `break`;
episodic retrieval moves its filter into SQL (`LIKE` + `LIMIT`) instead of
scanning every event ever written on every agent step
(`memory/episodic.py:18-28`).

**Approvals converge.** An `agent` node whose capability resolves to
`APPROVAL_REQUIRED` routes through the same pending-approval bridge machine
activities use, parking the run in `WAITING_APPROVAL` instead of failing it.
The GUI confirmation dialog fetches `approvalDetail` and shows the
machine-action preview beside the digest; the CLI `/approve` echoes digest
plus preview and requires a second confirmation. The Guard's decision logic,
risk classes, and the R2+ non-voice confirmation rule (Section 18.12) are
untouched — this record changes what the operator *sees*, never what is
*allowed*.

## Repairs folded in

These are correctness findings from the same audit that touch the same lines
the decision touches; folding them in avoids re-visiting the files.

- **Resume re-commit.** `agent_step.py:557-561` returns the cached output for
  an already-SUCCEEDED step, then runs `commit_all_changes` unconditionally —
  a resume after a later-step crash commits arbitrary dirty worktree state
  under the earlier step's message, or dies in `git add -A` if the worktree
  was cleaned. Skip the commit when the step short-circuited.
- **Credentials in scratch.** `agent_step.py:296-298` copies the operator's
  real `~/.codex/auth.json` into `cache/sandbox/<run_id>/`, which is cleaned
  only on SUCCEEDED runs — failed runs leave credential copies on disk
  indefinitely. Symlink or `chmod 0600` plus always-clean on any terminal
  state.
- **Timeout classification.** `machine/activities.py:259` lets
  `TimeoutExpired` escape as `INTERNAL`; adapters map the same condition to
  `LIMIT_EXCEEDED`. Catch and classify as `TIMEOUT`.
- **Gate check hangs.** The gate `checkCommand` subprocess in
  `cli/core_ops.py` (`_make_check_fn`) runs with no timeout — a hanging test
  command wedges the run with the step stuck RUNNING.
- **Inert symlink knob.** `machine/policy.py:65-67` checks `is_symlink()` on
  an already-resolved path, which is never true; `followSymlinks: false` is
  inert. Check before resolution or delete the constraint.
- **WAL.** `db/connection.py` sets `busy_timeout` for acknowledged concurrent
  writers but stays on the rollback journal; `PRAGMA journal_mode=WAL` is one
  line and removes writer-blocks-readers stalls during long agent steps.

## Explicitly deferred

Each of these is real, was observed in the audit, and is *not* decided here —
they carry their own tradeoffs and deserve their own records:

- **Intent routing.** Today every utterance runs `assistant-default@1.0.0`;
  nothing conversational reaches `workflow.authorDraft` or maps "run the
  deploy workflow" to `op_run_start`. A structured-output router (answer /
  run workflow / draft workflow / propose memory) in front of the assistant
  is the largest single intuitiveness jump available, and an architectural
  change warranting its own ADR.
- **Persona schema.** Implement-or-delete for `example_messages` and
  `generation` (an ADR-0018 amendment either threads them through to real
  model calls or stops validating discarded data).
- **Session/memory schema.** Persist `summarize_session` output, enforce or
  delete `active_session_ttl_hours` and the unused embedding config (an
  ADR-0020 amendment).
- **Streaming/live progress transport.** ADR-0024 parked server-push, and this
  implementation keeps `events.subscribe` as snapshot polling. Continuous
  frontend progress updates during an in-flight synchronous `run.start` remain
  deferred.
- **CI graduation.** Every CHANGE_LOG entry already cites test counts — the
  validation culture is CI-shaped and runs by hand. A minimal
  `.github/workflows/ci.yml` (ruff, `pytest -m "not live and not slow"`,
  `npm test --workspaces`), a `v0.1.0` tag, dependabot, and SECURITY.md are
  recommended as a separate, code-free change.

## The tradeoffs accepted

- Snapshot polling instead of push. Run and event detail are visible through
  explicit status/snapshot calls without introducing a streaming protocol.
- Bounded result persistence. Step outputs store a capped text plus an
  artifact spill, not the full agent transcript, in exchange for a readable
  `steps` table.
- Approval-required agent nodes now park runs that previously failed fast; an
  unattended operator sees `WAITING_APPROVAL` rather than a terminal state.
  This matches the machine-activity path and Section 15's approval seam.
- The shared runner adds one indirection layer to adapters, in exchange for
  fixing five copies of every invocation bug once.

## Acceptance

- A successful agent step's output row contains the agent's bounded result
  text and usage; `awf status <run>` and the chat transcript show it.
- Invoking a workflow whose adapter CLI is not installed produces a FAILED
  step whose reason names the missing CLI and the remedy — not `INTERNAL`
  `[Errno 2]`.
- Killing the backend mid-session produces a readable message in both
  frontends within the call timeout, including captured stderr where
  available.
- After `run.start` returns, `awf/run.status`, the CLI `/status` formatter,
  and GUI run detail expose step state and bounded output without raw DB
  inspection. Automatic live progress polling during the same in-flight
  request is not part of the implemented surface.
- A voice exchange of "my name is X" followed by "what is my name?" answers
  correctly from session context, with the active persona's tone.
- An R2 capability on an `agent` node parks the run in `WAITING_APPROVAL`,
  the confirmation dialog shows the machine-action preview, and approving
  resumes the run — with an integration test covering resume-after-approval
  and resume-after-crash (no re-commit of cached steps).
- No slash command listed in `HELP_TEXT` is absent from autocomplete, and
  none of `/approvals`, `/control`, `/llm`, `/memory-search` print raw JSON
  without `--json`.
- Every dropped MCP ref during envelope assembly has a matching
  `mcp_ref_skipped` event.
- Backend and frontend suites pass, with adapter invocation behavior
  centralized in `adapters/base.py`.

## Consequences

- Runs become more self-explanatory: what the agent said, why it stopped, and
  the recorded step state are visible where the operator already looks.
- The five adapters converge on one invocation path, so the next adapter —
  and the next invocation bug — is written once.
- The assistant graduates from a stateless form-submitter to a conversation
  with memory, using only components the repo already ships and tests.
- The guard, gates, verdict authorship, and every Section 18 prohibition are
  unchanged; this record spends its entire budget on legibility and wiring,
  not authority.
