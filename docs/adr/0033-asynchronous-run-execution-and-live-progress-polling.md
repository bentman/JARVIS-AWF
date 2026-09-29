# ADR-0033: asynchronous run execution and live progress polling

## Status

Implemented. Acceptance run: `pytest backend/tests/integration/test_ops_run_start.py backend/tests/integration/test_cli_main.py backend/tests/integration/test_protocol_stdio.py -q` -> 54 passed; `npm test --workspaces` -> 143 passed (17 shared, 52 cli, 74 gui); `ruff check` passed. Refines Section 13.1 and Section 16 of `docs/AGENTIC_WORKFLOW_FABRIC_SPEC.md` and fulfills the first pending dependency of ADR-0026.

## Context

In the workflow execution engine, `op_run_start` (`awf.ops.run`) historically executes the entire workflow synchronously inside a single request. When an operator triggers a workflow via the JSON-RPC interface (`awf/run.start`), the connection blocks until all steps finish or the run reaches `WAITING_APPROVAL`.

During long-running agent steps (which can take several minutes across multi-turn reasoning and tool calls), this synchronous blocking model causes two issues:
1. **Frontend Muteness & Freezing:** The CLI and GUI interfaces remain stuck on a static `working...` state or disabled button, unable to display intermediate step transitions, progress updates, or partial agent outputs.
2. **Transport Head-of-Line Blocking:** Because `awf.server.stdio` processes input requests sequentially, a synchronously blocked `run.start` prevents concurrent status queries (`awf/run.status` or `awf/events.subscribe`) from executing over the same transport channel until the entire run completes.

ADR-0024 explicitly parked server-push streaming (WebSockets, SSE, long-polling protocols) to preserve minimal operator footprint and avoid distributed connection state. ADR-0026 consequently unbundled live in-flight progress into ADR-0033, specifying that live progress must be achieved through start-and-poll without introducing streaming protocols.

## Decision

AWF implements asynchronous run execution and request/response progress polling:

1. **Asynchronous Run Execution in `awf.ops.run`:**
   - `op_run_start` accepts an optional `async_execution: bool = False` flag (preserving full backward compatibility for existing synchronous callers and test suites).
   - When `async_execution=True`:
     - Validates input schema against the workflow's `input_schema`.
     - Allocates a UUIDv7 `run_id` and registers the run in SQLite with `status = 'RUNNING'`.
     - Creates the Git worktree and scratch directory for the run.
     - Spawns background execution of `_run_workflow_safely` on a supervised worker thread.
     - The background worker creates an isolated SQLite connection (`get_connection(db_path)` with WAL mode), executes each node, records steps and event transitions, updates the run's final status and outcome, cleans up the workspace, and safely closes its connection.
     - `op_run_start` immediately returns the initial run reference:
       ```json
       {
         "run_id": "<run_id>",
         "status": "RUNNING",
         "workflow_ref": "<workflow_ref>"
       }
       ```

2. **Protocol Integration:**
   - `backend/src/awf/protocol/methods.py` updates the `awf/run.start` method definition to accept `async: bool = False`.
   - Protocol mirrors (`backend/src/awf/server/protocol_generated.py` and `frontend/shared/src/protocol.generated.ts`) are regenerated to expose the `asyncExecution` parameter.

3. **Frontend Polling & Step Observability:**
   - Frontends or callers desiring real-time progress invoke `runStart` with `async: true`, receive the initial `run_id`, and poll `awf/run.status` (or `awf/events.subscribe`) at regular intervals (e.g. 400ms).
   - In `frontend/gui`, `App.tsx` activates `pollRunProgress` when a workflow starts in `RUNNING` status, periodically updating `selectedRunDetail` until a terminal or waiting status is reached.
   - `awf/run.status` already returns the complete run record, all executed/running `steps`, and the current `outcome`.
   - Polling terminates deterministically when the run reaches any terminal state (`SUCCEEDED`, `FAILED`, `CANCELLED`) or waiting state (`WAITING_APPROVAL`, `WAITING_INPUT`).

## Consequences

- **Live Progress Visualization:** Frontends can render live step transitions and incremental progress without freezing.
- **Protocol Parity & Compatibility:** Existing synchronous callers continue to function unchanged with `async_execution=False`.
- **Zero Daemon Overhead:** Employs standard library threading and SQLite WAL concurrency without introducing background daemons, Celery, Redis, or external brokers.
- **Fulfills ADR-0026 Dependency:** Resolves the live in-flight progress polling requirement tracked under ADR-0026.
