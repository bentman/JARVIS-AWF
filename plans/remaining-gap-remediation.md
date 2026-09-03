# Architecture Scope: Minimal Operator Footprint

## Design Boundaries

AWF adheres to a minimal-infrastructure, single-operator operational model:
- Zero required background daemons, container runtimes, or external services.
- Local SQLite database and filesystem as the single sources of truth.
- Tooling and automation exist solely to reduce operator overhead, not add administrative surface. Any capability that introduces operational friction or daemon management without direct safety benefit is classified as excessive overhead and omitted.

---

## What We Have

### 1. Durable Execution & Fault Resilience
- **Durable State Engine**: Single SQLite database (`data/awf_db/awf.db`) managing atomic transitions for `runs`, `steps`, `events`, `artifacts`, `approvals`, and `secrets`.
- **Crash Recovery**: Startup recovery scan (`awf system resume`) resuming interrupted workflows from the last completed step with zero duplicate side effects.
- **Transient Failure Resilience (ADR-0030)**: Automatic retry with exponential backoff and randomized jitter for `TRANSIENT` and `TIMEOUT` step failure classes.

### 2. Authorization & Process Isolation
- **Capability Guard**: Deterministic, in-process authorization engine validating every tool and activity against declared agent capability allowlists across risk classes R0 through R3.
- **Filesystem & Git Isolation**: Dedicated, disposable Git worktrees (`cache/worktrees/<run_id>/`) per mutating Run and ephemeral scratch directories (`cache/sandbox/<run_id>/`).
- **Native CLI Sandboxes**: Process-level confinement leveraging native execution controls across Claude Code, OpenAI Codex CLI, Google Antigravity CLI, GitHub Copilot CLI, and Cline CLI.

### 3. Unified Operator Surfaces (ADR-0029)
- **Core CLI**: 8 task-oriented top-level commands (`run`, `status`, `control`, `doctor`, `review`, `registry`, `memory`, `system`).
- **AWF-CLI**: Inline Ink 7 terminal user interface preserving terminal scrollback, supporting slash commands and streaming execution transcripts.
- **AWF-GUI**: Local Electron desktop interface with local ONNX voice pipeline (Silero VAD, Whisper STT, Kokoro-82M TTS, openWakeWord), requiring physical on-screen confirmation for R2+ approvals.

### 4. In-Database Observability Ledger
- **Event Stream**: Append-only, SQL-queryable `events` table recording every state transition, policy decision, approval, and verification verdict without external dependencies.

### 5. Governed Self-Improvement (ADR-0021, ADR-0022)
- **Proposal Lifecycle**: Automated branch preparation, diff generation, safety assessments, and operator-consented merges bound to cryptographic action digests.

---

## What We Want

### 1. Automated Continuous Integration (`.github/workflows/ci.yml`)
- **Purpose**: Eliminates manual pre-commit test execution overhead by verifying changes automatically on push and pull request.
- **Specification**:
  - `backend` job (Ubuntu, Python 3.12): Installs `backend[dev]`, executes `scripts/validate_backend.py ci` (enforcing protocol parity, CLI argument consistency, Ruff formatting/linting, and regression suites), and archives validation logs.
  - `frontend` job (Ubuntu, Node 24 LTS): Installs dependencies via `npm ci` and runs `npm test --workspaces --if-present`.

### 2. Autonomous Proposal Verification Gate (`awf.eval.runner`)
- **Purpose**: Eliminates manual operator testing of self-improvement proposals by automatically executing declared check sets before presenting changes for review.
- **Specification**:
  - Deterministic evaluation runner (`backend/src/awf/eval/runner.py`) executing declared verification commands within the candidate proposal worktree.
  - Generates immutable `test-result` artifact rows in the `artifacts` table.
  - `awf.improvement.proposals.merge` gates on a valid passing `test-result` artifact before executing a branch merge.

### 3. Static License Attribution (`NOTICE`)
- **Purpose**: Plaintext copyright and licensing notice file at the repository root covering third-party open-source components (Kokoro-82M, Whisper, Silero VAD, openWakeWord).

---

## Excluded As Excessive Overhead ("Too Much")

The following items from theoretical specification models are explicitly excluded to prevent administrative overhead and operational drag:

### 1. External OpenTelemetry Collectors & Daemons
- **Status**: Excluded.
- **Boundary**: Running Jaeger, OpenTelemetry Collector daemons, network exporters, or port mappings adds significant operational friction to a local, single-operator environment.
- **Standard**: The embedded SQLite `events` ledger fulfills 100% of audit and timeline inspection requirements via standard SQL.

### 2. Container Runtime Escalation Tier (Podman / Docker)
- **Status**: Excluded.
- **Boundary**: Mandating a container engine introduces daemon maintenance, rootless user mapping complications, and filesystem mount friction across Windows, Linux, and macOS.
- **Standard**: Dedicated Git worktrees, ephemeral scratch paths, and native CLI process sandboxes provide sufficient isolation for single-operator local execution. Steps requiring unavailable permissions fail closed via Capability Guard policy denial.


