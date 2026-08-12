# ADR-0021: governed reach into the machine

## Status

Implemented.

Corrective update, 2026-08-12: the default capability registry now includes
`network_fetch@1.0.0` with an explicit example host allowlist
(`example.com`), `GET`/`HEAD`, R2 risk, and per-invocation approval. Workflows
can resolve the standard activity capability on a fresh checkout; operators
still need custom `data/registry/capabilities/network_fetch/` records for real
destinations beyond the shipped example.

Acceptance run: `backend/.venv/bin/python -m pytest backend/tests -q` outside
the Codex sandbox -> 550 passed, 7 warnings; `backend/.venv/bin/python -m ruff
check .` passed; `npm --prefix frontend run build --workspaces` passed; `npm
--prefix frontend test --workspaces` passed.

## Context

`docs/archives/ProjectVisionAWF.md` defines the fourth promise as governed
filesystem, command, network, and MCP reach. The boundary is explicit:
capability comes from a record, never from a prompt.

The current implementation already has the main control points:

- `CapabilityRecord` defines identity, effects, risk class, and approval mode.
- `Capability Guard` evaluates a capability against an allowlist and writes an
  event before execution.
- `agent` and `activity` workflow nodes pass through the guard before running.
- `approval` nodes persist an exact action digest and wait for operator
  approval.
- Each mutating Run uses a dedicated Git worktree and `cache/sandbox/<run_id>/`
  scratch directory.
- MCP server records resolve through the registry, skip quarantined or blocked
  data objects, render adapter-specific config, and are never connected to
  directly by AWF core.
- CLI and GUI already observe pending approvals through JSON-RPC instead of
  reading durable state directly.

The current gaps are specific:

- no first-class filesystem activities for bounded read, write, and delete;
- no first-class command execution activity with executable/argument policy;
- no first-class network fetch activity with destination allowlisting;
- no normalized machine-action digest shared by guard, approval, event, and UI;
- `APPROVAL_REQUIRED` currently blocks agent/activity execution instead of
  creating a pending approval for the exact machine action;
- capability records do not yet carry path, command, or network constraints;
- frontend approval summaries show an action digest but not a normalized
  machine-action preview.

Provider and community practice points to the same implementation shape:

- The MCP 2026-07-28 specification treats tools as arbitrary code execution and
  says hosts need explicit user consent, clear review UI, access controls, and
  privacy controls before data access or tool invocation:
  <https://modelcontextprotocol.io/specification/2026-07-28>
- Claude Code's sandbox documentation separates permissions from sandboxing and
  recommends filesystem and network boundaries enforced by the OS, with writes
  defaulting to the working directory/temp area and new network domains requiring
  approval:
  <https://code.claude.com/docs/en/sandboxing>
- OpenAI's Codex CLI documentation exposes `/permissions` as the operator
  surface for setting run boundaries and inspecting the active sandbox and
  writable roots:
  <https://learn.chatgpt.com/docs/codex/cli>

## Decision

**Machine reach is workflow execution, not frontend authority.** The CLI and
GUI may request, inspect, approve, or reject machine actions through JSON-RPC,
but they do not directly read/write paths, run commands, or call network
destinations.

**Machine actions are activities.** Add standard activities for `fs_read`,
`fs_write`, `fs_delete`, `command_run`, and `network_fetch`. These activities
run only inside a Run, after a Capability Record has been resolved and a guard
decision has been recorded.

**Capability Records carry executable policy.** Extend Capability Records with
an optional `constraints` object. Existing records remain valid. Machine
activities require the relevant constraint subsection.

**Approval is bound to the exact normalized action.** For any
`APPROVAL_REQUIRED` machine action, AWF creates or reuses an `approvals` row
whose digest is computed from the normalized action payload, not merely the
workflow node id. A changed path, command, argument, body digest, method, URL,
or destination host produces a different digest and requires review again.

**Default reach is worktree and scratch only.** Reads and writes are confined to
the Run worktree and Run scratch directory unless a Capability Record explicitly
declares an additional allowed root. `.env`, `data/awf_db/`, secrets, and the
authorization registry surface are denied by default. Any allowed exception is
R2 and per-invocation.

**Delete is not routine.** Delete operations are R2 by default. Initial
implementation should use a reversible move-to-trash inside the Run worktree
when possible. Permanent deletion or deletion outside the Run worktree is denied
unless an R2 capability explicitly allows it and the operator approves the exact
target.

**Network reach is destination-scoped.** `network_fetch` requires a host
allowlist in the Capability Record. Redirects are followed only if every
destination host is allowed. Request body digests, method, URL, and response
metadata are recorded; response bodies are artifacts when retained.

**MCP remains a connection boundary.** An MCP server record can expose tool
names, resources, and prompts, but invoking or rendering access to it still
requires trust status checks and Capability Records for the exposed tools.
Descriptions supplied by MCP servers are untrusted metadata; they do not grant
authority.

## Rationale

The Project Vision requires useful machine reach without prompt-granted
authority. Implementing machine reach as activities reuses the existing durable
Run/Step model, event log, worktree isolation, approval queue, and frontend
approval display.

Extending Capability Records with constraints is smaller than adding a separate
policy registry. Capabilities already answer "what may be called"; constraints
answer "where and how this capability may act."

The normalized action digest is the critical control. It prevents approval of a
generic class of action from becoming approval of a different path, command, or
network destination.

Keeping MCP indirect matches the existing adapter flow and the MCP security
model: the host application remains responsible for consent, access control,
and review; server-provided tool descriptions are not trusted policy.

## Deviation recorded

| Requirement | Deviation | Compensating control |
|---|---|---|
| Section 9.1 Capability Record shape does not include path, command, or network policy | Adds optional `constraints` object | Existing records remain valid; machine activities require specific constraints before execution |
| Section 12.2 activity nodes can run arbitrary registered Python functions | Adds standard machine activities with stricter policy checks | These activities require normalized action validation, guard authorization, and approval when required |
| Current guard returns `APPROVAL_REQUIRED` but activity/agent execution treats it as policy denial | Adds machine-action approval bridge for machine activities | The exact action digest is persisted and reviewed before execution resumes |
| Section 16.3 JSON-RPC method list has no machine-action preview/read surface | Adds approval detail/preview methods only | Frontends still do not execute machine actions directly |
| MCP server records render adapter config but do not require per-tool Capability Records at render time | Requires declared MCP tool capability refs before exposure | Untrusted or unrecorded MCP tools are not rendered into adapter config |

No change is made to the Run state machine, registry resolution order, adapter
contract, or frontend authority model.

## Implementation

Implemented on 2026-08-09.

- Added standard governed machine activities: `fs_read`, `fs_write`,
  `fs_delete`, `command_run`, and `network_fetch`.
- Extended Capability Records with optional `constraints`; existing records
  remain valid, while standard machine activities require their matching
  filesystem, command, or network constraint family.
- Added normalized machine-action digests and an approval bridge that creates
  or reuses the existing approval row for exact machine actions.
- Added approval detail and machine-action preview JSON-RPC methods, CLI
  command support, and GUI preview rendering.
- Added MCP declared-tool exposure checks: a server that declares tools is
  rendered only when every declared tool has a matching allowed MCP-tool
  Capability Record.
- Added default filesystem, command, and network capability records under
  `config/app_registry/capabilities/`, including bounded write size defaults
  for `fs_write` and a conservative example-host allowlist for
  `network_fetch`.
- Machine policy accepts platform-native absolute allowed roots, not only
  POSIX-style `/...` roots. Command activities validate the authored
  executable exactly, then resolve Python aliases such as `python3.12` and
  repo-relative venv paths to the active repo venv/current interpreter at
  execution time so the same workflow works on Windows and Linux.

Validation evidence:

- `backend/.venv/bin/python -m pytest backend/tests -q` outside the Codex
  sandbox -> 550 passed, 7 warnings.
- `backend/.venv/bin/python -m ruff check .` -> passed.
- `npm --prefix frontend run build --workspaces` -> passed.
- `npm --prefix frontend test --workspaces` -> shared 9 passed, CLI 37
  passed, GUI 32 passed.

## Mechanism

### Task A — Capability constraints

Extend `CapabilityRecord` parsing with an optional `constraints` mapping.

Example filesystem read capability:

```yaml
identity: {type: activity, provider: awf, name: fs_read, version: 1.0.0}
schema: {input: "", output: ""}
effects: {operation: read, reversible: true, idempotent: true, external_side_effect: false}
risk_class: R0
approval: never
constraints:
  filesystem:
    allowedRoots: [worktree, scratch]
    allowedGlobs: ["**/*.md", "**/*.py", "**/*.ts", "**/*.tsx", "**/*.json", "**/*.yaml"]
    deniedGlobs: [".env", "data/awf_db/**", "data/registry/capabilities/**"]
    followSymlinks: false
```

Example bounded command capability:

```yaml
identity: {type: activity, provider: awf, name: command_run, version: 1.0.0}
schema: {input: "", output: ""}
effects: {operation: execute, reversible: true, idempotent: true, external_side_effect: false}
risk_class: R1
approval: per-invocation
constraints:
  command:
    executable: python3.12
    allowedArgs:
      - ["-m", "pytest", "backend/tests/**"]
    cwdRoot: worktree
    timeoutSeconds: 300
    network: denied
```

Example network capability:

```yaml
identity: {type: activity, provider: awf, name: network_fetch, version: 1.0.0}
schema: {input: "", output: ""}
effects: {operation: communicate, reversible: false, idempotent: true, external_side_effect: true}
risk_class: R2
approval: per-invocation
constraints:
  network:
    allowedHosts: ["example.com"]
    allowedMethods: ["GET", "HEAD"]
    maxResponseBytes: 1048576
    retainBodyAsArtifact: true
```

Validation rules:

- exactly one machine constraint family is required for standard machine
  activities;
- filesystem roots must resolve to `worktree`, `scratch`, or an explicit
  absolute path declared in the capability;
- command executable and cwd must resolve under an allowed root unless the
  capability is R2/per-invocation;
- network hosts must be exact hostnames or explicit wildcard suffixes;
- network host allowlists must be non-empty;
- secrets may be referenced only by secret name, never inline value;
- R0 machine capabilities cannot write, execute, delete, or communicate.

### Task B — Machine-action policy module

Add `backend/src/awf/machine/`:

```text
machine/
  action.py        # normalized action payloads and digests
  policy.py        # path, command, and network constraint checks
  approvals.py    # approval bridge for APPROVAL_REQUIRED decisions
  activities.py   # fs_read/fs_write/fs_delete/command_run/network_fetch
```

`MachineAction` should include:

- `kind`: `fs_read|fs_write|fs_delete|command_run|network_fetch`;
- `run_id`, `step_id`, and workflow node id;
- normalized path(s), command argv, or URL;
- operation;
- body/content digest where applicable;
- capability ref and capability digest where available;
- risk class and approval mode.

The digest is:

```text
sha256(canonical_json(machine_action_without_timestamp))
```

The event payload records the normalized action, not raw secrets or full file
contents.

### Task C — Approval bridge for machine activities

Add a helper used only by machine activities:

```python
authorize_machine_action(conn, capability, allowlist, action, actor, role)
```

Behavior:

1. evaluate and record the guard decision;
2. if decision is `DENY`, fail the Step with `POLICY_DENIED`;
3. if decision is `ALLOW`, execute;
4. if decision is `APPROVAL_REQUIRED`, create or reuse an `approvals` row using
   the machine-action digest, mark Step/Run `WAITING_APPROVAL`, and return
   `{"waiting_input": true, "approval_id": ...}`;
5. when the Step resumes after approval, recompute the action digest and execute
   only if it matches the approved row.

This preserves the existing approval table and frontend approval flow while
making approval useful for standard machine activities.

### Task D — Filesystem activities

Register:

- `fs_read`
- `fs_write`
- `fs_delete`

Required behavior:

- normalize all paths with `Path.resolve(strict=False)`;
- deny symlink traversal unless the capability permits it;
- deny reads/writes outside allowed roots;
- write via temporary file plus atomic replace where practical;
- emit artifacts for retained file snapshots when configured;
- implement reversible delete as move-to-trash inside the worktree when
  possible;
- record `machine_action_allowed`, `machine_action_waiting_approval`,
  `machine_action_denied`, and `machine_action_executed` events.

### Task E — Command activity

Register `command_run`.

Required behavior:

- use `subprocess.run` with list argv only;
- no shell by default;
- cwd must be an allowed root;
- timeout is mandatory;
- stdout/stderr size caps are mandatory;
- environment starts from a minimal allowlist plus explicitly named secret
  references;
- unresolved globs, shell metacharacters, command separators, and redirection
  are data unless a capability explicitly allows shell execution;
- shell execution is R2/per-invocation minimum.

### Task F — Network activity

Register `network_fetch`.

Required behavior:

- support `GET` and `HEAD` first;
- validate every redirect destination host;
- enforce response byte cap before retention;
- record method, URL, status code, content type, response size, and body digest;
- write retained bodies as artifacts, not event payloads;
- default-deny private network ranges unless explicitly allowed by an R2
  capability.

### Task G — MCP exposure checks

Before rendering MCP server config for an adapter:

- resolve the server and trust status as today;
- for every exposed tool requested by an Agent Manifest, require a Capability
  Record with `identity.type: mcp-tool` and `identity.provider` matching the MCP
  server name;
- skip tools without a matching allowed capability;
- record rendered server, rendered tool names, capability refs, and digests;
- never treat MCP tool descriptions as policy.

This changes exposure, not protocol implementation. AWF still does not become a
general MCP client in this ADR.

### Task H — Protocol and frontend preview

Extend core operations and JSON-RPC with read-only preview methods:

```text
awf/approval.detail
awf/machine.actionPreview
```

The GUI and CLI approval views should show:

- approval id;
- risk class;
- capability ref;
- operation;
- normalized path, command argv, or URL;
- body/content digest;
- whether the action is reversible;
- whether there is an external side effect.

Approval and rejection continue to use existing approval methods. Voice-only
approval remains refused for R2+.

## Entry and exit points

Entry points:

- authored or hand-written Workflows using standard machine activities;
- resident-mind-authored Workflow proposals from ADR-0019, after operator
  publication;
- CLI/GUI approval views over JSON-RPC;
- Agent Manifest MCP refs, after capability and trust filtering.

Execution path:

```text
Workflow node
  -> activity executor
  -> machine action normalization
  -> capability resolution
  -> policy constraint check
  -> Capability Guard event
  -> optional approval wait/resume
  -> worktree/scratch/network/command operation
  -> event + optional artifact
  -> Step output
```

Exit points:

- Step output for small structured results;
- artifact rows for retained file snapshots, command logs, and response bodies;
- events for guard decisions, approval waits, denials, and execution summaries;
- approval rows for pending or decided R2 actions;
- Run status for waiting, succeeded, or failed state.

## Test plan

Focused backend tests:

```text
backend/tests/unit/test_machine_action.py
backend/tests/unit/test_machine_policy.py
backend/tests/integration/test_machine_activities.py
backend/tests/integration/test_baseline_agent_step_mcp.py
backend/tests/integration/test_phase10_server_stdio.py
backend/tests/integration/test_phase10_cli_main.py
```

Focused frontend tests:

```text
frontend/shared/tests/client.test.ts
frontend/cli/tests/commands.test.ts
frontend/gui/tests/ipc.test.ts
frontend/gui/tests/ApprovalConfirmation.test.tsx
frontend/gui/tests/Dashboard.test.tsx
```

Validation commands:

```text
backend/.venv/bin/python -m pytest backend/tests/unit/test_machine_action.py backend/tests/unit/test_machine_policy.py backend/tests/integration/test_machine_activities.py backend/tests/integration/test_baseline_agent_step_mcp.py
backend/.venv/bin/python -m pytest backend/tests -q
npm --prefix frontend run build --workspaces
npm --prefix frontend test --workspaces
backend/.venv/bin/python -m ruff check .
git diff --check
```

Live validation is not required for this ADR unless a host-specific command,
network route, or adapter sandbox claim is made. Any live command that needs
host reach outside the Codex sandbox must be executed on the real host with
explicit operator approval and reported separately from unit/integration
evidence.
