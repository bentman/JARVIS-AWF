# ADR-0034: conversational intent router

## Status

Implemented. Acceptance run: `pytest backend/tests/unit/test_cognition_router.py backend/tests/integration/test_ops_intent.py backend/tests/integration/test_protocol_stdio.py backend/tests/integration/test_voice_sessions.py -q` -> 34 passed; `npm test --workspaces` -> 145 passed; `ruff check` passed. Fulfills the final pending dependency of ADR-0026.

## Context

Prior to this decision, all conversational inputs submitted to AWF—whether from the CLI assistant input, voice interactions via `op_voice_submit_text`, or GUI text submission—were hard-coded to invoke `assistant-default@1.0.0` (`_assistant_reply`).

While the assistant could converse, it had no operational reach into the fabric:
- An operator saying "run the deploy workflow" received a generic chat response instead of triggering `op_run_start`.
- An operator saying "draft a workflow to backup the database" received an conversational answer instead of triggering `op_workflow_author_draft`.
- An operator stating "remember that the staging server is 10.0.0.1" did not record persistent memory.

ADR-0026 flagged this conversational blind spot and unbundled intent routing into ADR-0034, noting that a structured-output router in front of the assistant represents the largest single intuitiveness jump available to the operator.

## Decision

AWF implements a hybrid Conversational Intent Router spanning cognition and operations:

1. **Four Canonical Intents:**
   - `answer`: Conversational interaction with the assistant via `assistant-default@1.0.0` (using `_assistant_reply`).
   - `run_workflow`: Direct execution of a registered workflow via `op_run_start`.
   - `draft_workflow`: Authoring a workflow proposal draft via `op_workflow_author_draft`.
   - `propose_memory`: Recording a persistent fact via session context and memory proposals.

2. **Cognition Router (`awf.cognition.router`):**
   - Implements `classify_intent(repo_root, conn, text) -> ClassifiedIntent`:
     - **Deterministic Fast Path:** Direct operational commands (e.g. `run <workflow>`, `start workflow <name>`, `draft workflow <desc>`, `remember <fact>`) match prefix patterns and return immediately with high confidence without LLM latency or token cost.
     - **Structured Model Classification:** Nuanced or conversational text queries `resident-mind@1.0.0` using `complete_structured` against a strict JSON schema (`INTENT_ROUTER_SCHEMA`).
     - **Zero-Crash Graceful Fallback:** If the LLM is offline, unprovisioned, or returns an error, the router defaults to `intent: "answer"` (`assistant-default@1.0.0`), ensuring uninterrupted conversational dialogue.

3. **Operations Layer (`awf.ops.intent`):**
   - Exposes `op_intent_classify(repo_root, conn, *, text)` and `op_intent_dispatch(repo_root, conn, *, text, voice_session_id=None, turn_id=None, async_execution=False)`.
   - Dispatches each intent to its corresponding subsystem:
     - `run_workflow` $\to$ `op_run_start` with extracted `workflow_ref` and `input_data`.
     - `draft_workflow` $\to$ `op_workflow_author_draft` with extracted `objective`.
     - `propose_memory` $\to$ `append_entry` in the active session and creates memory proposals.
     - `answer` $\to$ `op_run_start` executing `assistant-default@1.0.0`.

4. **Integration Across Operator Surfaces:**
   - In `awf.ops.voice`: `op_voice_submit_text` dynamically routes through intent classification when `workflow_ref` is omitted.
   - In `awf.protocol.methods`: Added `awf/intent.classify` and `awf/intent.dispatch` methods with generated Python and TypeScript mirrors.
   - In `frontend/cli/src/commands.ts`: `dispatchAssistantInput` leverages `intentDispatch` when available.
   - In `frontend/gui`: `App.tsx` routes typed composer input for the default assistant workflow through `onIntentDispatch`, surfacing intent outcomes, proposals, and memory actions in the conversation stream.

## Consequences

- **Intuitiveness:** The operator can conversationally execute workflows, draft proposals, and store memory without manually prefixing slash commands or writing CLI arguments.
- **Robustness:** Direct prefixes execute with zero latency, while offline environments gracefully fall back to standard assistant replies.
- **ADR-0026 Fulfillment:** Resolves the final pending item for ADR-0026, unblocking transition of ADR-0026 to `Implemented`.
