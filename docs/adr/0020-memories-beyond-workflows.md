# ADR-0020: memories beyond workflows

## Status

Implemented.

Corrective update, 2026-08-15: `_semantic_line` in `memory/context.py` now
reads the actual `search_semantic_memories` result schema — `ref` as label,
`object.subject / object.predicate / object.value` as body, top-level
`confidence` appended when present. The previous implementation read `title`,
`key`, `text`, `content`, and `summary`, none of which that function emits,
and fell through to `json.dumps(result)`, injecting digest, trust_status, and
all governance fields into the prompt. The rule in Task F below is corrected
accordingly.

Corrective update, 2026-08-12: agent execution now retrieves memory context
by default through `retrieve_memory_context(repo_root, conn, query=objective,
profile_ref="default@1.0.0")` during prompt-envelope assembly. Retrieved
semantic memories render as untrusted `memory/context` segments and episodic
hits render as untrusted `retrieval/context` segments before the current
`user/input`. Retrieval failures are logged as `memory_retrieval_skipped` and
do not fail the agent step.

Corrective update, 2026-08-12: `data/registry/memory-profiles/.gitkeep` and
`data/registry/semantic-memories/.gitkeep` now ship with matching `.gitignore`
re-include rules, so every declared memory registry kind has consistent
operator-data scaffolding.

Alignment update: memory, session, and episodic operations live in
`awf.ops.memory`; registry publication/listing lives in `awf.ops.registry`.
All operations are centralized in `awf.ops`.

## Context

`docs/archives/ProjectVisionAWF.md` defines the third promise as memory beyond
workflows. AWF already records what happens during a Run, but those records are
not yet deliberate memory. The target layers are:

- present-turn working context;
- bounded active-session memory;
- episodic memory over Runs, Steps, verdicts, approvals, and proposal actions;
- semantic memory for durable facts and preferences;
- procedural memory through Skills;
- operator profile state for preferences, personas, voices, defaults, and
  permissions.

The boundary is exact: memory is operator-visible, curatable, registry-shaped,
and resolved under the same repository-default/operator-override/version rules
as other AWF registry objects. Retrieval does not imply retention.

The current codebase has useful entry points:

- `events` already stores durable Run/Step/approval/gate transitions.
- `artifacts` already stores immutable evidence pointers.
- `registry/kinds.py`, `registry/resolve.py`, `registry/index.py`, and
  `awf.ops.registry.op_registry_publish` already provide versioned registry publishing,
  lookup, indexing, trust status, and digest checks.
- `awf.cognition.envelope.PromptEnvelope` already has `session`, `memory`, and
  `retrieval` authorities.
- Persona loading rejects `memory_policy` and `memory_permissions`, so memory
  authority stays outside persona text.
- `frontend/shared/src/client.ts` is the shared protocol boundary for CLI and
  GUI; frontends do not read `data/` directly.
- ADR-0019 already established a proposal pattern for model-authored registry
  work, including review and digest-bound publication.

The gaps are:

- no Memory Profile registry kind;
- no Semantic Memory registry kind;
- no explicit active-session store;
- no deliberate episodic retrieval API over events/artifacts;
- no memory retrieval renderer that adds bounded, provenanced memory segments
  to a prompt envelope;
- no operator UI/API to view, correct, forget, pin, or publish memory.

Provider and community practices align with these gaps:

- OpenAI separates session history from longer-lived agent memory, uses
  progressive disclosure, and treats stale memory as guidance that must yield
  to current environment truth:
  <https://openai.github.io/openai-agents-python/sandbox/memory/>
- LangChain/LangGraph separates short-term thread-scoped memory from
  long-term cross-session stores, and distinguishes semantic, episodic, and
  procedural memory:
  <https://docs.langchain.com/oss/python/concepts/memory>
- Anthropic Contextual Retrieval emphasizes bounded retrieval with chunk
  context, hybrid lexical/semantic search, and evaluation of retrieval quality:
  <https://www.anthropic.com/engineering/contextual-retrieval>
- Claude's memory tool pattern keeps memory operations client-side: the model
  may request memory operations, but the application owns storage and policy:
  <https://platform.claude.com/docs/en/agents-and-tools/tool-use/memory-tool>

## Decision

**Memory is a registry-backed capability, not a cache.** Durable semantic
memory is stored as versioned registry objects. Cache files and derived indexes
may speed retrieval, but the registry object is the authority.

**Implement in layers.** The first implementation adds active sessions,
episodic retrieval, and semantic memory records. Procedural memory remains the
existing Skill registry kind. Operator profile state stays in personas, voice
profiles, frontend settings, and future profile registry objects.

**No automatic durable memory from model output.** A model may propose a memory
candidate, but only an operator action or an explicit workflow may publish it.
The publishing path is the registry path.

**Retrieval is bounded and provenance-first.** Every retrieved memory item
returns source, digest, version, confidence, timestamps, trust status, and a
reason for inclusion. Retrieved content enters prompt envelopes as `memory` or
`retrieval` segments, never as application/persona/contract instructions.

**Corrections are versioned.** Correcting a semantic memory publishes a new
version or marks the previous version blocked. Forgetting operator memory blocks
or removes the operator override; repository defaults remain governed by normal
registry behavior.

**Episodic memory is read-only over existing evidence.** Events and artifacts
remain the source for "what happened." The memory API adds retrieval and
summaries over those rows; it does not copy Run history into semantic memory by
default.

**Frontend access is protocol-only.** CLI and GUI use JSON-RPC methods for
memory list/get/search/publish/correct/forget/pin operations. They do not read
or write `data/registry/`, `data/awf_db/`, or derived memory indexes directly.

## Rationale

Registry-shaped semantic memory satisfies the Project Vision boundary while
reusing the strongest existing AWF machinery: versioning, digest checks,
operator overrides, trust status, and publish validation.

Separating active-session, episodic, semantic, and procedural memory prevents
one weak signal from becoming a durable fact. A turn can stay coherent without
becoming memory. A Run can be retrieved without being promoted to a preference.
A Skill can remain procedural without being mixed into user facts.

Keeping retrieval as prompt-envelope segments preserves ADR-0018 authority
boundaries. Memory can inform a model, but it does not become an instruction
source with higher authority than the operator or the workflow contract.

Using explicit publication for durable memory follows the same safety shape as
ADR-0019: models may propose, operators or approved workflows publish.

## Deviation recorded

| Requirement | Deviation | Compensating control |
|---|---|---|
| Section 9.3 registry kinds do not include memory records | Adds `memory-profiles` and `semantic-memories` registry kinds | Same config/data resolution, digest, trust, publish, and block rules as existing kinds |
| Section 8 schema has no active-session or retrieval tables | Adds small SQLite tables for sessions and derived retrieval indexes | Registry files remain authoritative for semantic memory; indexes are rebuildable |
| ADR-0019 proposal rows only allow `kind = 'workflows'` | Widens `registry_proposals.kind` to include `semantic-memories` | Existing workflow proposal behavior remains unchanged; semantic-memory publication uses the same digest-bound proposal table |
| Section 16.3 JSON-RPC method list does not include memory methods | Adds `awf/memory.*` methods | Methods map to core operations and add no frontend-only authority |
| Section 14 event log is forensic, not a retrieval surface | Adds episodic retrieval over existing events/artifacts | Events and artifacts remain unchanged and authoritative |

## Mechanism

### Task A — Registry kinds

Add two registry kinds.

```python
MEMORY_PROFILES = RegistryKind("memory-profiles", "yaml", False)
SEMANTIC_MEMORIES = RegistryKind("semantic-memories", "yaml", False)
```

`memory-profiles/<name>/<version>.yaml` defines retrieval policy:

```yaml
apiVersion: awf/v1
kind: MemoryProfile
metadata:
  name: default
  version: 1.0.0
  digest: sha256:...
spec:
  enabled: true
  maximum_data_class: internal
  retrieval:
    maxItems: 8
    maxTokens: 1600
    includeEpisodic: true
    includeSemantic: true
    minConfidence: 0.6
  retention:
    activeSessionTtlHours: 72
    requireExplicitSemanticPublish: true
  embedding:
    enabled: false
    modelProfileRef: null
    version: none
```

`semantic-memories/<name>/<version>.yaml` stores one durable fact, preference,
or profile assertion:

```yaml
apiVersion: awf/v1
kind: SemanticMemory
metadata:
  name: operator-prefers-concise-status
  version: 1.0.0
  digest: sha256:...
spec:
  subject: operator
  predicate: prefers_status_style
  value: concise factual progress updates
  memoryType: preference
  scope: operator
  confidence: 0.85
  data_classification: internal
  provenance:
    sourceType: operator|run|artifact|manual
    sourceRef: manual
    artifactId: null
    runId: null
    eventId: null
    observedAt: "2026-08-09T00:00:00Z"
  validity:
    validFrom: "2026-08-09T00:00:00Z"
    validUntil: null
  correction:
    supersedes: null
    correctedBy: null
    correctionReason: null
  pinned: false
  enabled: true
```

Validation rules:

- closed top-level field set;
- `metadata.name` and `metadata.version` match path;
- `confidence` is `0.0 <= confidence <= 1.0`;
- `data_classification` is one of AWF's existing `public`, `internal`, or
  `confidential` classes;
- at least one provenance field identifies where the memory came from;
- secrets and raw credentials are rejected;
- executable instructions in `value` are allowed only as quoted data and are
  never rendered into trusted prompt segments.

### Task B — Active-session store

Widen the existing proposal table first:

```sql
CREATE TABLE registry_proposals (
    ...
    kind TEXT NOT NULL CHECK (kind IN ('workflows', 'semantic-memories')),
    ...
)
```

For an existing database, `init_db` needs a migration equivalent to creating a
replacement table with the wider check, copying rows, dropping the old table,
and renaming the replacement. A `CREATE TABLE IF NOT EXISTS` statement alone
will not change the existing check constraint.

Add `active_sessions` and `active_session_entries` tables.

```sql
CREATE TABLE IF NOT EXISTS active_sessions (
    session_id TEXT PRIMARY KEY,
    title TEXT,
    status TEXT NOT NULL CHECK (status IN ('active', 'summarized', 'expired')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    expires_at TEXT
)
```

```sql
CREATE TABLE IF NOT EXISTS active_session_entries (
    entry_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES active_sessions (session_id),
    role TEXT NOT NULL CHECK (role IN ('operator', 'assistant', 'system', 'tool')),
    content_json TEXT NOT NULL,
    summary TEXT,
    created_at TEXT NOT NULL
)
```

Active-session data is working context. It can be summarized or expired. It is
not semantic memory until a separate publish action creates a
`SemanticMemory`.

### Task C — Episodic retrieval service

Add `awf.memory.episodic`:

```python
def search_events(
    conn: sqlite3.Connection,
    *,
    query: str,
    run_id: str | None = None,
    limit: int = 20,
) -> list[dict]: ...


def run_timeline(conn: sqlite3.Connection, *, run_id: str) -> dict: ...
```

The implementation starts with deterministic SQLite search over:

- `events.reason_code`;
- `events.actor`;
- `events.payload_json`;
- `runs.workflow_ref`;
- `steps.node_id`;
- `approvals.action_digest` and approval status;
- artifact metadata.

Semantic/vector retrieval is optional and may be added behind a
`memory-profile` embedding setting after deterministic retrieval is stable.

### Task D — Semantic memory service

Add `awf.memory.semantic`:

```python
def parse_semantic_memory(raw: dict) -> SemanticMemory: ...
def load_semantic_memory(path: Path) -> SemanticMemory: ...
def search_semantic_memories(
    repo_root: Path,
    conn: sqlite3.Connection,
    *,
    query: str,
    profile_ref: str = "default@1.0.0",
) -> list[dict]: ...
```

Initial retrieval uses deterministic lexical scoring over subject, predicate,
value, type, scope, and provenance fields. Results include digest and source
from `registry_index` when available. `blocked` memories do not retrieve.

### Task E — Memory proposal and publication flow

Reuse ADR-0019's proposal pattern for model-suggested semantic memories:

```text
data/proposals/semantic-memories/<proposal-id>/<name>/<version>.yaml
```

Add core operations:

```python
op_memory_propose_semantic(...)
op_memory_publish(proposal_id, digest)
op_memory_reject(proposal_id, reason)
```

`op_memory_publish` calls `op_registry_publish(..., kind="semantic-memories")`
after validating the draft digest. Model output is never written directly into
`data/registry/`.

### Task F — Prompt-envelope integration

Add `awf.memory.context`:

```python
def retrieve_memory_context(
    repo_root: Path,
    conn: sqlite3.Connection,
    *,
    query: str,
    profile_ref: str = "default@1.0.0",
) -> tuple[PromptSegment, ...]: ...
```

Rules:

- semantic memories render as `PromptSegment("memory", "context", False, ...)`;
- episodic retrieval renders as `PromptSegment("retrieval", "context", False, ...)`;
- each segment text is a compact `ref: subject predicate value (confidence)` line — governance fields (digest, trust_status, provenance, source) are not injected into the prompt;
- token and item caps are enforced before rendering;
- memory is injected for agent invocations by default using
  `default@1.0.0`; callers may override the profile with
  `constraints.memory_profile_ref`.

### Task G — CLI, JSON-RPC, and frontend app flow

Add CLI commands (consolidated under `awf memory` per ADR-0029):

```text
awf memory search <query> [--profile <name>@<version>]
awf memory get <name>@<version>
awf memory propose --file <path>
awf memory publish <proposal-id> --digest <draft-digest>
awf memory reject <proposal-id> --reason <text>
awf memory block <name>@<version>
awf memory session start [--title <title>]
awf memory session append <session-id> --role <role> --json <path>
awf memory session show <session-id>
awf memory session summarize <session-id>
awf memory episodic search <query> [--run-id <run-id>]
awf memory episodic timeline <run-id>
```

Add JSON-RPC methods:

```text
awf/memory.search
awf/memory.get
awf/memory.propose
awf/memory.publish
awf/memory.reject
awf/memory.block
awf/session.start
awf/session.append
awf/session.show
awf/session.summarize
awf/episodic.search
awf/episodic.timeline
```

Frontend shared adds typed client methods. AWF-CLI adds matching slash
commands. AWF-GUI adds a memory panel with:

- search;
- memory detail;
- provenance and confidence display;
- publish/reject for proposed memories;
- block/forget controls;
- run timeline drill-down.

Voice may request memory lookup. Voice may not publish, block, or forget
memory without on-screen confirmation.

## Acceptance criteria

- Memory Profile and Semantic Memory registry objects parse, validate, publish,
  index, resolve, trust, and block through existing registry infrastructure.
- A semantic memory under `data/registry/` overrides a repository default with
  the same name according to normal registry resolution rules.
- Active-session entries can be appended, summarized, shown, and expired
  without creating semantic memory.
- Episodic search returns events/artifacts with run, step, actor, reason,
  timestamp, and source evidence.
- Semantic search returns only enabled, unblocked records allowed by the active
  Memory Profile.
- Prompt-envelope integration renders memory and retrieval as untrusted
  context with provenance.
- A model-suggested semantic memory cannot publish without a proposal digest
  check and the registry publish path.
- Correcting memory creates a new version or blocks the older one; it does not
  mutate prior registry bytes.
- Frontends use JSON-RPC only.
- Voice-only flows cannot publish, block, or forget memory.

## Test plan

Focused backend tests:

```text
backend/tests/unit/test_memory_profile.py
backend/tests/unit/test_semantic_memory.py
backend/tests/integration/test_memory_registry.py
backend/tests/integration/test_memory_sessions.py
backend/tests/integration/test_memory_episodic.py
backend/tests/integration/test_phase10_server_stdio.py
backend/tests/integration/test_phase10_cli_main.py
```

Focused frontend tests:

```text
frontend/shared/tests/client.test.ts
frontend/cli/tests/commands.test.ts
frontend/gui/tests/MemoryPanel.test.tsx
frontend/gui/tests/ipc.test.ts
```

Validation commands:

```text
backend/.venv/bin/python -m pytest backend/tests/unit/test_memory_profile.py backend/tests/unit/test_semantic_memory.py backend/tests/integration/test_memory_registry.py backend/tests/integration/test_memory_sessions.py backend/tests/integration/test_memory_episodic.py backend/tests/integration/test_phase0_bootstrap.py backend/tests/integration/test_phase10_server_stdio.py backend/tests/integration/test_phase10_cli_main.py
npm --prefix frontend --workspace @awf/protocol-client test
npm --prefix frontend --workspace awf-cli test
npm --prefix frontend --workspace awf-gui test
npm --prefix frontend run build
backend/.venv/bin/python -m ruff check backend/src backend/tests
git diff --check
```

Live LLM validation is not required for ADR-0020. If memory proposals are
generated by resident-mind during implementation validation, live AWF runtime
commands that start, probe, or stop `llama-server` must run on the real host
outside the Codex sandbox.

Implementation evidence:

```text
backend/.venv/bin/python -m pytest backend/tests/unit/test_memory_profile.py backend/tests/unit/test_semantic_memory.py backend/tests/integration/test_memory_registry.py backend/tests/integration/test_memory_sessions.py backend/tests/integration/test_memory_episodic.py backend/tests/integration/test_phase0_bootstrap.py backend/tests/integration/test_phase10_server_stdio.py backend/tests/integration/test_phase10_cli_main.py
# 42 passed

npm --prefix frontend --workspace @awf/protocol-client test -- --run
# 9 passed

npm --prefix frontend --workspace awf-cli test -- --run
# 36 passed

npm --prefix frontend --workspace awf-gui test -- --run
# 32 passed

npm --prefix frontend run build
# passed

backend/.venv/bin/python -m ruff check backend/src/awf backend/tests
# passed

git diff --check
# passed
```

Frontend commands were validated in the current shell with Node v22.19.0. The
repo policy remains Node.js 24 LTS `>=24.15.0`.
