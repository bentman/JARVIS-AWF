# ADR-0019: the mind authors the work

## Status

Proposed.

## Context

`docs/archives/ProjectVisionAWF.md` defines the second promise as authorship:
an operator describes an outcome, the resident mind proposes a Workflow, and
that proposal becomes registry truth only after operator review. The boundary
is exact: a generated workflow is a proposal until approved, publication is an
approval event, and the diff reviewed is the diff that runs.

The current implementation already has most of the required control points:

- `awf.cli.core_ops.op_registry_validate` parses and validates Workflow files.
- `awf.cli.core_ops.op_registry_publish` writes registry objects under
  `data/registry/` and updates `registry_index`.
- `awf.cli.core_ops.op_run_start` resolves a published Workflow and starts the
  Run.
- `awf.server.stdio` exposes the same core operations over JSON-RPC.
- `frontend/shared/src/client.ts` is the single TypeScript protocol client used
  by both frontends.
- `awf.cognition` provides the ADR-0018 prompt envelope.
- `awf.gateway.client.complete` routes model calls through LiteLLM and Model
  Profiles.

The current implementation does not have a proposal object, a generated
Workflow draft path, or an approval boundary that binds publication to the
exact draft bytes the operator reviewed. Existing `approvals` rows are scoped
to Run Steps and are appropriate for workflow execution. Workflow authorship is
pre-run registry work, so it needs a small proposal lifecycle rather than a
fake Run.

Provider and community practices point to the same shape:

- Request structured output using JSON Schema when the provider supports it.
- Validate the returned JSON in application code before any side effect.
- Persist the review state so a UI restart does not lose the pending decision.
- Allow approve, edit, or reject before the side effect.
- Bind the final side effect to the exact payload that was reviewed.

Relevant provider references:

- OpenAI function calling and Structured Outputs:
  <https://help.openai.com/en/articles/8555517>
- Anthropic structured outputs:
  <https://platform.claude.com/docs/en/build-with-claude/structured-outputs>
- LiteLLM structured output support:
  <https://docs.litellm.ai/>
- LangGraph human-in-the-loop review and persistence:
  <https://docs.langchain.com/oss/python/langchain/frontend/human-in-the-loop>
  and <https://docs.langchain.com/oss/python/langgraph/persistence>

Live validation may use CPU fallback. The local model candidate is:

- `models/llm/assistant-qwen3-8b-q5-balanced/Qwen3-8B-Q5_K_M.gguf`
- `awf.llm.discovery.local_models()` discovers it.
- `awf.llm.discovery.model_by_name()` resolves it.

The implementation should not require an accelerator for authorship testing.
When an accelerator-specific manual runtime is unavailable or unsuitable, the
Linux x64 CPU llama.cpp runtime is sufficient for live functional validation:
the resident mind profile points at the same OpenAI-compatible endpoint, and
the model artifact remains the same. Functional tests that require a live model
server must still be marked live and skipped unless the endpoint is reachable.

## Decision

**Workflow authorship is a proposal pipeline.** The resident mind may generate
a Workflow draft from an operator objective, but it may not publish or run that
Workflow directly.

**Generated drafts are durable operator work product.** AWF writes Workflow
drafts under `data/proposals/workflows/<proposal-id>/`. Drafts are readable,
editable, digestible, and recoverable across process restarts.

**Publication is digest-bound.** Publishing a proposal requires the caller to
provide the digest of the draft they reviewed. AWF recomputes the digest from
disk immediately before publication. If the digest changed, publication fails
and the operator must review the new draft.

**Edits replace the candidate.** If the operator edits a generated draft, the
edited bytes are the candidate. The resident mind receives no special
authority over the edited form.

**The existing registry publish path remains authoritative.** Once a proposal
is approved, AWF calls the existing `op_registry_publish` path. Registry
resolution, indexing, trust status, and digest verification remain centralized.

**The existing Run path remains authoritative.** A generated Workflow can run
only after it is published and then passed to `op_run_start` like any other
Workflow.

**Structured model output is required for the authoring step.** AWF asks the
Model Gateway for JSON matching an authoring schema. The result is validated
with `jsonschema`, transformed to canonical Workflow YAML, and then validated
again with `parse_workflow`.

**The first implementation targets Workflow proposals only.** The Project
Vision also names Skills, Agent Manifests, and Capability Records. They use
the same proposal pattern later; they are not part of this ADR's initial
mechanism.

## Rationale

The Project Vision requires reviewable registry objects, not hidden plans in a
context window. A proposal object gives the frontends something stable to show,
the backend something stable to validate, and the operator an exact digest to
approve.

Digest-bound publication is the smallest control that makes "the diff reviewed
is the diff that ran" enforceable. It avoids trusting UI state, model output
text, or path names as proof of review.

Keeping publication and execution on existing core operations avoids a second
registry writer and a second Run starter. That preserves the AWF rule that
frontends add no authority.

Structured output is necessary but not sufficient. Provider-side schema
conformance reduces malformed responses; application-side validation and
registry validation still decide whether the draft is acceptable.

## Deviation recorded

| Requirement | Deviation | Compensating control |
|---|---|---|
| Section 7 repository layout enumerates `data/registry/` and `data/artifacts/`, but not proposal storage | Adds `data/proposals/workflows/<proposal-id>/` | Proposal storage is operator data, gitignored with `data/`, and never used by registry resolution |
| Section 8 SQLite schema does not include registry proposals | Adds proposal tables | Existing Run, Step, approval, artifact, and registry tables are unchanged; proposal rows represent pre-run registry work |
| Section 16.1 core CLI does not include authorship commands | Adds author/proposal commands | Commands delegate to core operations and do not bypass registry validation, publication, or Run startup |
| Section 16.3 JSON-RPC method list does not include proposal methods | Adds proposal methods | Methods map one-to-one to core operations and grant no frontend-only authority |

No change is made to the Workflow Definition contract, node vocabulary,
Capability Guard, registry resolution order, Model Profile schema, or Run state
machine.

## Mechanism

### Task A — Proposal schema and lifecycle

Add two SQLite tables.

```sql
CREATE TABLE IF NOT EXISTS registry_proposals (
    proposal_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN ('workflows')),
    name TEXT NOT NULL,
    version TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN (
        'draft', 'pending_review', 'published', 'rejected', 'superseded'
    )),
    draft_path TEXT NOT NULL,
    draft_sha256 TEXT NOT NULL,
    model_profile_ref TEXT,
    objective TEXT NOT NULL,
    validation_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    published_at TEXT,
    rejected_at TEXT,
    rejection_reason TEXT
)
```

```sql
CREATE TABLE IF NOT EXISTS registry_proposal_events (
    event_id TEXT PRIMARY KEY,
    proposal_id TEXT NOT NULL REFERENCES registry_proposals (proposal_id),
    prior_status TEXT,
    new_status TEXT NOT NULL,
    actor TEXT NOT NULL,
    reason_code TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    occurred_at TEXT NOT NULL
)
```

Proposal draft files live at:

```text
data/proposals/workflows/<proposal-id>/<name>/<version>.yaml
```

Status transitions:

```text
draft -> pending_review
pending_review -> published
pending_review -> rejected
pending_review -> draft
draft -> superseded
```

`published`, `rejected`, and `superseded` are terminal.

### Task B — Structured authoring module

Add `awf.authoring.workflow` with these public functions:

```python
def author_workflow_draft(
    repo_root: Path,
    conn: sqlite3.Connection,
    *,
    objective: str,
    model_profile_ref: str = "resident-mind@1.0.0",
    name: str | None = None,
    version: str = "1.0.0",
) -> dict: ...

def get_proposal(repo_root: Path, conn: sqlite3.Connection, *, proposal_id: str) -> dict: ...

def update_proposal(
    repo_root: Path,
    conn: sqlite3.Connection,
    *,
    proposal_id: str,
    content: str,
) -> dict: ...

def publish_proposal(
    repo_root: Path,
    conn: sqlite3.Connection,
    *,
    proposal_id: str,
    expected_sha256: str,
) -> dict: ...

def reject_proposal(
    conn: sqlite3.Connection,
    *,
    proposal_id: str,
    reason: str,
) -> dict: ...
```

`author_workflow_draft`:

1. Resolves the Model Profile.
2. Builds a `PromptEnvelope` with:
   - application instructions for AWF Workflow authorship;
   - contract text naming the JSON output schema;
   - repository context containing available registry entries;
   - the operator objective as untrusted user input.
3. Calls `complete_structured`.
4. Validates the JSON authoring payload.
5. Converts it to Workflow YAML.
6. Validates the YAML with `parse_workflow`.
7. Writes the draft file.
8. Writes `registry_proposals` and a proposal event.
9. Returns proposal id, path, digest, validation status, and a summary.

`update_proposal`:

1. Rejects terminal proposals.
2. Writes the caller-provided content to the same draft path.
3. Recomputes the digest.
4. Revalidates through `parse_workflow`.
5. Updates the proposal row and event log.

`publish_proposal`:

1. Requires `status == 'pending_review'`.
2. Recomputes the draft digest from disk.
3. Requires `actual_sha256 == expected_sha256`.
4. Validates the Workflow again.
5. Calls `op_registry_publish(repo_root, conn, path=draft_path, kind="workflows")`.
6. Marks the proposal `published`.

### Task C — Model Gateway structured output

Extend `awf.gateway.client`:

```python
def complete_structured(
    profile: ModelProfile,
    messages: list[dict],
    *,
    schema_name: str,
    schema: dict,
    conn: sqlite3.Connection | None = None,
    secret_key: bytes | None = None,
) -> dict: ...
```

For each candidate, call LiteLLM with:

```python
response_format={
    "type": "json_schema",
    "json_schema": {
        "name": schema_name,
        "schema": schema,
        "strict": True,
    },
}
```

Then parse `response.choices[0].message.content` as JSON and validate it with
`jsonschema.validate`. If a provider returns valid JSON but violates the
schema, fail the candidate and follow the Model Profile fallback policy.

### Task D — Core operations, CLI, and JSON-RPC

Add core operations in `awf.cli.core_ops` that delegate to
`awf.authoring.workflow`:

```python
op_workflow_author_draft(...)
op_proposal_get(...)
op_proposal_update(...)
op_proposal_publish(...)
op_proposal_reject(...)
```

Add CLI commands:

```text
awf author workflow --objective <text> [--profile <name>@<version>] [--name <name>] [--version <version>]
awf proposal show <proposal-id>
awf proposal update <proposal-id> --file <path>
awf proposal publish <proposal-id> --digest sha256:<digest>
awf proposal reject <proposal-id> --reason <text>
```

Add JSON-RPC methods:

```text
awf/workflow.authorDraft
awf/proposal.get
awf/proposal.update
awf/proposal.publish
awf/proposal.reject
```

All methods call the same core operations as the CLI.

### Task E — Frontend app flow

Extend `frontend/shared` with proposal types and ProtocolClient methods.

AWF-CLI adds slash commands:

```text
/author workflow <objective>
/proposal <id>
/proposal-publish <id> <sha256:digest>
/proposal-reject <id> <reason>
```

AWF-GUI adds a proposal review card:

- objective;
- proposed name and version;
- validation result;
- draft path;
- digest;
- readable Workflow content;
- approve/publish button;
- reject button.

Voice input may request authoring. Voice input may not publish a proposal.
Publishing requires an on-screen confirmation because publication changes
operator registry state.

## Acceptance criteria

- A mocked structured-output model response creates a Workflow proposal and
  draft file.
- The proposal is listed/readable through CLI and JSON-RPC.
- The draft validates through existing Workflow validation.
- Publishing with the current digest writes the Workflow through
  `op_registry_publish`.
- Publishing with a stale digest fails and does not write registry state.
- Editing a proposal changes the digest and requires the new digest for
  publication.
- Rejecting a proposal prevents later publication.
- A published proposal can be run only through the normal `awf run` /
  `awf/run.start` path.
- Frontends use JSON-RPC methods only; they do not read or write proposal or
  registry files directly.

## Test plan

Focused backend tests:

```text
backend/tests/unit/test_workflow_authoring.py
backend/tests/unit/test_model_gateway_structured.py
backend/tests/integration/test_workflow_proposals.py
backend/tests/integration/test_phase10_server_stdio.py
```

Focused frontend tests:

```text
frontend/shared/tests/client.test.ts
frontend/cli/tests/commands.test.ts
frontend/gui/tests/App.dashboard.test.tsx
```

Validation commands:

```text
backend/.venv/bin/python -m pytest backend/tests/unit/test_workflow_authoring.py backend/tests/unit/test_model_gateway_structured.py backend/tests/integration/test_workflow_proposals.py backend/tests/integration/test_phase10_server_stdio.py -q
npm --prefix frontend/shared test
npm --prefix frontend/cli test
npm --prefix frontend/gui test
scripts/validate_backend.py lint
```

Live model validation is optional and must be skipped unless a reachable
resident-mind endpoint exists. CPU fallback with the Linux x64 llama.cpp runtime
is an acceptable live validation path; accelerator-backed validation is not
required for ADR-0019.

Live AWF runtime commands that start, probe, or stop `llama-server` must be run
on the real host outside the Codex sandbox. The sandbox can misreport hardware
capability and can block loopback bind/probe behavior, so sandboxed results are
not acceptance evidence for resident-mind runtime readiness.
