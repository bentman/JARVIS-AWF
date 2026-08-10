# ADR-0024: familiar control center

## Status

Implemented.

Acceptance run: `backend/.venv/bin/python -m pytest backend/tests -q` -> 570
passed, 1 skipped, 7 warnings; `backend/.venv/bin/python -m ruff check .`
passed; `npm --prefix frontend run build --workspaces` passed; `npm --prefix
frontend test --workspaces` -> shared 12 passed, CLI 41 passed, GUI 37 passed.

## Context

`docs/archives/ProjectVisionAWF.md` defines the seventh promise as a familiar
control center: a desktop surface for running work, approvals, verdicts, diffs,
memory, registry inspection, model identity, and hardware readiness; and a
terminal peer with streaming interaction and slash commands where registry
Skills appear as commands. Both surfaces must attach to the same headless core.

The current codebase already has useful pieces:

- `frontend/shared/src/types.ts` and `frontend/shared/src/client.ts` define the
  shared JSON-RPC client used by both frontends.
- `frontend/cli/src/commands.ts` exposes fixed slash commands for runs,
  approvals, artifacts, improvements, workflow authoring, proposals, memory,
  sessions, episodic timelines, registry lists, secrets, settings, theme, and
  keybindings.
- `frontend/gui/src/renderer/App.tsx` composes dashboard, proposal review,
  memory, transcript, voice activation, and approval confirmation panels.
- `frontend/gui/src/renderer/Dashboard.tsx` shows run, pending approval, and
  improvement-proposal summaries.
- `frontend/gui/src/main/ipc.ts` and `frontend/gui/src/preload/preload.ts`
  keep Electron renderer access behind narrow IPC methods.
- `backend/src/awf/cli/core_ops.py` already has operations for runs,
  approvals, artifacts, registry objects, memory, sessions, episodic timeline,
  voice sessions, and LLM server/model state.

Important gaps remain:

- The desktop surface is a set of panels, not yet a cohesive control center
  with one selected session/run and detail views for verdicts, artifacts,
  diffs, model choice, hardware chain, and registry objects.
- LLM server/model state exists in backend core operations, but is not exposed
  through the Section 16.3 JSON-RPC method list or GUI IPC surface.
- Hardware/profile readiness is not exposed as a GUI-readable protocol shape.
- `awf/events.subscribe` is listed in the shared protocol, but the current
  stdio server rejects it because request/response stdio is not a streaming
  transport.
- Registry Skills are listable through `/skills`; they are not yet executable
  slash commands with capability/approval handling.

Provider and community practice supports the target shape:

- OpenAI Codex CLI presents agent work in a terminal, runs locally against the
  operator's project, and uses explicit approval modes for command execution
  and edits:
  <https://help.openai.com/en/articles/11096431>
- Codex approval guidance treats approvals as scoped operator decisions for
  file edits and commands, and the app-server protocol sends approval prompts
  as JSON-RPC requests associated with a thread and turn:
  <https://www.mintlify.com/openai/codex/concepts/approvals> and
  <https://github.com/openai/codex/blob/main/codex-rs/app-server/README.md>
- Claude Code documents slash-command and subagent conventions, including
  project/user scopes and explicit tool access per subagent:
  <https://code.claude.com/docs/en/subagents>
- Claude Code hooks expose lifecycle extension points and a read-only command
  browser, matching the need for visible automation hooks rather than hidden
  frontend behavior:
  <https://code.claude.com/docs/en/hooks>
- Zed's Agent Client Protocol positions editor/desktop clients as agent UIs
  over protocol boundaries rather than durable-state owners:
  <https://zed.dev/acp>
- Electron recommends context isolation and a narrow `contextBridge` API; raw
  `ipcRenderer` should not be exposed to web content:
  <https://www.electronjs.org/docs/latest/tutorial/context-isolation> and
  <https://www.electronjs.org/docs/latest/api/context-bridge>

## Decision

**The control center is a composition over the existing core.** The desktop and
terminal clients gain richer status and detail views by adding protocol methods
where needed. They do not read `data/`, write registry files directly, or own
authorization logic.

**The shared protocol is the product boundary.** If the GUI needs model,
hardware, verdict, diff, registry, event, or run-detail information, the core
must expose it through `awf serve --stdio` and `frontend/shared`. A capability
that exists only as Electron code is not part of AWF.

**Desktop UX uses overview plus focused detail.** The first control-center
layout should keep the existing panels but reorganize them around:

- current session and selected run;
- active runs and last completed verdict;
- pending approvals with exact action digest and preview;
- improvement proposals and reviewable diff artifacts;
- model/server status and the model selected for the active session;
- hardware profile, reachable accelerators, and speech/LLM readiness;
- memory search/edit controls;
- registry object browser for agents, workflows, skills, MCP servers,
  capabilities, model profiles, and voice profiles;
- conversation transcript as one panel, not the whole application.

**Event streaming is not assumed until the transport supports it.** The first
implementation uses explicit refresh and read-only timeline/detail calls.
`awf/events.subscribe` remains unavailable over request/response stdio until a
streaming protocol is implemented. The GUI may poll focused summary methods;
it must not pretend that server-push exists.

**Terminal and desktop are peers.** The CLI keeps the fixed slash-command
surface and adds registry-backed Skill command discovery. A Skill can appear as
a command only when the core can resolve the Skill, validate its binding, route
the requested action through the Capability Guard, and record the decision.
Until that invocation path exists, `/skills` remains a browser, not execution.

**Subagents and hooks are registry concepts, not frontend plug-ins.** Agent
Manifests, Skills, MCP definitions, capabilities, and future hook records are
registry objects. The GUI/CLI can inspect and request actions against them.
Repository defaults ship under `config/app_registry/`; operator registry state
lives under `data/registry/`. When `data/registry/<kind>/<name>/` exists, it
overrides the matching shipped default for that kind and name. Copying a
default, adding a new object, publishing a draft, promoting trust, retiring an
object, or executing a Skill must preserve registry resolution, digest, trust,
guard, approval, and event rules.

**Approvals stay exact and action-bound.** Desktop approval cards and terminal
approval commands must use the same approval record, exact action digest, and
machine-action preview. R2+ confirmation rules from ADR-0023 remain unchanged.

**Electron remains a narrow shell.** The renderer keeps `contextIsolation` and
uses only preload-exposed methods. Main-process IPC handlers delegate to the
shared protocol client or to already-governed subprocess boundaries.

## Rationale

The vision asks for a familiar agent control center, not a new architecture.
Current agent tools have converged on terminal commands, scoped approvals,
visible tool access, hooks, subagents, and desktop/editor surfaces that observe
agent state through a protocol. AWF should fit that pattern while preserving
its stronger invariants: durable runs, capability records, gates, audit events,
and hardware honesty.

Putting missing control-center data behind JSON-RPC keeps scripts, CLI, and GUI
equally capable. It also makes the first implementation testable without a live
Electron window and avoids frontend-only state.

Polling summary/detail calls are sufficient for the first pass because the
current stdio server cannot push events. That keeps the implementation honest
and leaves a clean seam for later streaming.

## Entry and exit points

### Backend core and JSON-RPC

- Add read-only control-center aggregation in `backend/src/awf/cli/core_ops.py`:
  - `op_control_center_summary`
  - `op_control_center_run_detail`
  - `op_system_readiness`
- Expose those through `backend/src/awf/server/stdio.py`:
  - `awf/control.summary`
  - `awf/control.runDetail`
  - `awf/system.readiness`
- Expose existing LLM operations through JSON-RPC:
  - `awf/llm.servers`
  - `awf/llm.models`
  - `awf/llm.serveStatus`
- Preserve the registry resolution split:
  - `config/app_registry/` is shipped, repo-tracked defaults.
  - `data/registry/` is operator-owned registry state for copied defaults, new
    objects, proposals, trust changes, and retirements.
  - A present `data/registry/<kind>/<name>/` tree overrides
    `config/app_registry/<kind>/<name>/` for that kind and name.
- Reuse existing operations rather than duplicating queries:
  - runs: `op_run_list`, `op_run_status`
  - approvals: `op_approval_list`, `op_approval_detail`
  - artifacts: `op_artifact_list`, `op_artifact_read`
  - registry: `op_registry_list`, `op_registry_get`
  - memory: `op_memory_search`, `op_memory_get`
  - episodic: `op_episodic_timeline`
  - LLM: `op_llm_servers`, `op_llm_models`, `op_llm_serve`
- Keep control-center summary/detail operations read-only. Registry writes
  remain explicit registry actions; once written under `data/registry`, they
  participate in normal override resolution.

### Frontend shared protocol

- Add typed results and client methods in `frontend/shared/src/types.ts` and
  `frontend/shared/src/client.ts` for:
  - control summary;
  - run detail;
  - system readiness;
  - LLM servers/models/status.
- Keep `MethodName` exhaustive so GUI needs cannot bypass the protocol.

### AWF-GUI main/preload

- Add narrow IPC channels in `frontend/gui/src/main/ipc.ts` for the new shared
  protocol methods.
- Add matching preload methods in `frontend/gui/src/preload/preload.ts`.
- Keep renderer access limited to the `window.awf` API.

### AWF-GUI renderer

- Replace or evolve `Dashboard.tsx` into a control-center component with:
  - overview cards;
  - selected run detail;
  - approval queue with previews;
  - verdict/artifact/diff links;
  - model and hardware readiness panels;
  - registry browser entry points;
  - memory controls;
  - transcript panel.
- Keep existing components where they already match the target:
  - `ApprovalConfirmation.tsx`
  - `ProposalReview.tsx`
  - `MemoryPanel.tsx`
  - `Transcript.tsx`
  - `VoiceActivation.tsx`
- Add renderer tests that verify the displayed data comes from props/protocol
  functions, not direct filesystem reads.

### AWF-CLI

- Add commands for the new read-only status surfaces:
  - `/control`
  - `/readiness`
  - `/llm`
- Add Skill command discovery:
  - `/skills` continues to list registry Skills.
  - `/skill <name>@<version>` shows Skill detail through `registry.get`.
  - Direct `/skill-name ...` invocation is added only after a core Skill
    invocation operation exists and passes the Capability Guard.
- Preserve existing slash commands and tests.

## Implementation plan

1. Add backend read-only aggregation and protocol methods for control summary,
   run detail, system readiness, and LLM state.
2. Add shared TypeScript types/client methods and focused client tests.
3. Add GUI IPC/preload methods for the new protocol calls.
4. Refactor the dashboard into a control-center overview with focused detail
   panes, preserving existing proposal, memory, voice, transcript, and approval
   components.
5. Add CLI commands for `/control`, `/readiness`, `/llm`, and `/skill`.
6. Add targeted backend/frontend tests for the new protocol and UI surfaces.
7. Validate with focused backend tests, frontend build/tests, Ruff, and
   `git diff --check`.

## Acceptance criteria

- Desktop shows one coherent control-center view that includes active runs,
  pending approvals, recent verdict/improvement state, model/LLM state,
  hardware/readiness state, registry access, memory access, and transcript.
- Selecting a run exposes status, steps, timeline, artifacts, and verdict
  references through protocol data.
- The GUI can show model and hardware readiness without direct file reads.
- The GUI can initiate explicit registry actions that create or update
  `data/registry` objects, and those objects override shipped defaults through
  normal registry resolution.
- The CLI exposes the same read-only status surfaces and can inspect a specific
  Skill registry object.
- No frontend owns durable state or authorization logic.
- R2+ approval confirmation remains exact-action and screen-confirmed.
- `awf/events.subscribe` is not claimed as working over request/response stdio.
- Tests cover backend core ops, JSON-RPC dispatch, shared client methods, GUI
  rendering, GUI IPC wiring, and CLI command dispatch.

## Validation commands

- `backend/.venv/bin/python -m ruff check .`
- `backend/.venv/bin/python -m pytest backend/tests -q`
- `npm --prefix frontend run build --workspaces`
- `npm --prefix frontend test --workspaces`
- `git diff --check`
- GUI live smoke, when needed, must be run outside the Codex sandbox because
  Electron desktop launch can require host display/sandbox access.

## Consequences

- The desktop becomes the primary operator overview without becoming a durable
  state owner.
- The terminal remains a peer surface instead of a reduced fallback.
- Missing model/hardware readiness display becomes a protocol/backend task
  rather than a renderer shortcut.
- Skill execution is held until the core can govern it through registry and
  capability records.
- Streaming events remain a separate transport milestone.
