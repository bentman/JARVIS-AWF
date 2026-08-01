# Agentic Workflow Fabric (AWF)
## Normative Specification for a Single-Operator, Minimal-Infrastructure Build

**Document status:** Normative design specification — active implementation target  
**Intended reader:** Software-building agents (Claude Code, Codex CLI, Antigravity CLI, GitHub Copilot CLI, Cline CLI, and successors) and human implementers  
**License:** Apache License 2.0 (this document and the reference implementation it describes)  
**Status:** Self-contained — every contract, schema, state machine, and rule needed to build is defined here. The data contracts (Workflow, Agent, Capability, Skill, Artifact, Finding, Verdict, Voice Profile) are shaped to survive a future swap of the durability, policy, or secrets backend without renaming or restructuring; no such migration is in scope.

---

## 1. Normative language

**MUST**, **MUST NOT**, **REQUIRED**, **SHOULD**, **SHOULD NOT**, and **MAY** are used per RFC 2119 and RFC 8174. A conforming implementation MUST satisfy every MUST/MUST NOT statement. Deviating requires an ADR: a short Markdown file in `docs/adr/` naming the requirement, the rationale, and the compensating control.

The build sequence (Section 6) is normative: phases are built in order.

**Definition over ambiguity.** This document states decisions, not options: every choice point names its default; every SHOULD/MAY names the behavior when the option is not taken; prohibitions are paired with the required behavior. Where this document is silent, an implementing agent follows AGENTS.md or stops and asks the operator — it MUST NOT invent a preference. Evaluated-but-unselected technologies are unnamed; re-opening any selection is an ADR, never an inference.

**Reading path for implementers.** To execute a build phase: read its Section 6 row, then the sections that row cites, with Sections 7 (layout) and 8 (schema) as shared ground truth for every phase. Section 7's module map names the code target for each phase. Frontend work (Phases 11–12) consumes the core exclusively through Section 16.3's protocol and needs no core internals beyond it.

---

## 2. System definition

**AWF** is a durable, local-first control system for running AI coding/research agents against explicit, versioned Workflow definitions, with crash-recoverable state, human approval gates, tiered independent verification, and an audit trail — all backed by SQLite and the filesystem, with no required background services.

The primary unit of operation is a **Run** of a versioned **Workflow Definition**. Agents are bounded executors inside a Run; they are never the durable orchestrator.

**System boundaries.** Each boundary names the mechanism and the section that owns it; an implementation builds exactly these mechanisms and nothing beyond them:

- **Process model:** every AWF process is operator-started (the `awf` command directly, or a frontend holding `awf serve --stdio` as its child) and may exit at any time. Continuity between sessions lives entirely in durable state under `data/`; a later `awf resume` picks up exactly where work stopped (Section 13.2). Section 15 preserves the seams through which a scheduler later starts the same commands unattended.
- **Isolation:** provided by Git worktrees, a disposable scratch directory, and each CLI adapter's own permission/sandbox system (Section 10); a rootless container is the documented escalation tier for explicitly untrusted content (Section 10.4).
- **Authorization:** performed by the Capability Guard — a small, deterministic, versioned Python module in this repo reading YAML Capability Records (Section 9).
- **Agent execution:** performed by the named CLI coding agents through the adapter contract (Section 10). AWF is the durable layer above them: it invokes them, records what they did, verifies the result, and remembers it.

---

## 3. From AGENTS.md principles to architecture decisions

Each infrastructure choice below follows directly from an AGENTS.md principle.

| AGENTS.md principle | AWF consequence |
|---|---|
| KISS: smallest design that satisfies the current contract | SQLite for all durable state; an in-process Capability Guard function; LiteLLM as an in-process library; Git worktrees + a scratch directory for isolation |
| YAGNI: no services before a caller exists | No scheduler/daemon until an unattended workflow actually needs one (Section 15); no A2A wire protocol until a genuinely remote agent needs calling; no container backend until a workflow actually runs untrusted content |
| DRY: centralize shared contracts | One SQLite database (`data/awf_db/awf.db`) is the single source of durable execution truth; one Capability Guard function is the single authorization chokepoint; one Agent Invocation / AgentResult envelope covers all five named adapters |
| Idempotent: repeated commands are safe | Every mutating step carries an idempotency key (the step's `attempt` UUID); the `secrets` table is overwrite-only; registry publication is content-addressed (same bytes → same digest → no duplicate) |
| Deterministic: no hidden network/clock/random/host-state deps in tests | Workflow replay determinism rule (Section 13.2): all non-deterministic operations (model calls, tool calls, subprocess execution) MUST be recorded as Steps, never inlined in workflow-selection logic |

---

## 4. Resolved architecture decisions (binding)

Substituting an alternative for any resolution below requires a new ADR.

| Decision area | Resolution |
|---|---|
| Durable state | SQLite only — no additional database, orchestrator, or background service. All durable state lives under `data/`, structured so the whole directory can be copied to another machine or shared later without a migration step. |
| Sandbox/isolation | No mandatory container backend. Each named CLI adapter's own sandbox/permission system is the primary isolation boundary (Section 10). AWF additionally provides a Git worktree per mutating Run and a disposable, non-durable scratch directory at `cache/sandbox/<run_id>/` (gitignored, never backed up, safe to delete anytime). Containers are an optional, documented escalation path for explicitly untrusted content only. |
| Attendance model | Mostly attended (operator-initiated). Multi-agent handoff loops (producer↔reviewer, agent-to-agent cycles) are a first-class pattern (Section 13). Unattended operation is a near-term direction the architecture MUST NOT preclude; it is not built in this pass (Section 15). |
| Secrets | Encrypted `secrets` table inside `data/awf_db/awf.db`. Values are opaque ciphertext, never human-readable, overwrite-only (no partial edit — a write replaces the whole value). The symmetric key lives at `./.env` as `AWF_SECRET_KEY`, gitignored, machine-local, and **not** part of the relocatable `data/` bundle — moving `data/` to another machine requires re-supplying the key there. |
| Verification rigor | Tiered by risk, structured as a **Trifecta** (Builder → Verifier → Adversary/Optimizer — Section 12.3). Default tier: Builder + Verifier. High-risk tier (Section 12.2 trigger list): full Trifecta. No role may assess its own output; the final Verdict is written by deterministic control code, never by any agent. |
| Model access | LiteLLM used as a Python library, in-process, no proxy server, by default. Self-hosted LiteLLM Proxy (Docker) is documented as an optional escalation for sharing one gateway across machines/clients — never required. Model/routing configuration is stored as durable, versioned registry data under `data/registry/model-profiles/`. |
| Named CLI adapters | Claude Code, OpenAI Codex CLI, Google Antigravity CLI (`agy`), GitHub Copilot CLI, Cline CLI — each with a documented adapter (Section 10) — plus a generic adapter contract so more can be added later without a spec revision. |
| Operator interfaces | Two frontends over one Python core. **AWF-CLI**: an npm-distributed, inline (scrollback-preserving) terminal UI with a slash-command surface (Section 16.2), in the style of Claude Code / Codex CLI / Antigravity CLI. **AWF-GUI**: a desktop voice app (STT/TTS) in which agent roles carry assignable personas and audibly distinct voices (Sections 16.4–16.5). Both are pure presentation layers speaking JSON-RPC 2.0 over stdio to the Python core (Section 16.3); neither may bypass the Capability Guard, approvals, or Gates. |
| Frontend language exception | The AWF core (durable state, policy, execution, adapters) stays Python per AGENTS.md. AWF-CLI and the AWF-GUI shell are TypeScript on Node ≥22 — a bounded exception to AGENTS.md's Python preference, recorded here (no separate ADR required). No durable state or authorization logic may live in frontend code. |
| Voice stack | **One selected engine per function**, all open-source, behind a single speech-adapter contract on an ONNX Runtime base, execution provider chosen by the Hardware Profiler (Section 16.4). Selections: STT = **Whisper** (faster-whisper as the CUDA variant); TTS = **Kokoro-82M** (multi-voice); VAD = **Silero VAD**; wake word = **openWakeWord** (`hey jarvis`). Models are operator-downloaded at Phase 12 setup — never bundled — license accepted at download. A selection is replaced only via ADR against the same contract. Cloud voice is an optional per-profile escalation, never required. |
| License | Apache License 2.0 for this specification and the reference implementation. Third-party CLI tools driven by an adapter remain under their own upstream licenses (Section 17). |
| AGENTS.md wiring | `AGENTS.md`'s Source Of Truth list designates this document as the active implementation target. |

---

## 5. Reference technology stack

| Function | Choice | Reference |
|---|---|---|
| Language/runtime | Python `>=3.12,<3.15`, venv — per AGENTS.md | — |
| Durable state | SQLite 3, accessed via Python's standard `sqlite3` module or a thin wrapper | https://docs.python.org/3/library/sqlite3.html |
| Durable-execution pattern | Step-boundary persistence + deterministic replay + startup recovery scan, following the pattern documented by DBOS Transact (used as the reference pattern, not a dependency — AWF implements it on SQLite) | https://docs.dbos.dev/ , https://github.com/dbos-inc/dbos-transact-py |
| Secrets encryption | `cryptography` package, `Fernet` recipe (AES-128-CBC + HMAC, safe defaults, no manual nonce handling) | https://cryptography.io/en/latest/fernet/ |
| Tool/resource/prompt interoperability | Model Context Protocol, current spec **2026-07-28** (stateless core, Extensions framework, Tasks, MCP Apps; Roots/Sampling/Logging deprecated — do not build against them) | https://modelcontextprotocol.io/specification/2026-07-28 , https://blog.modelcontextprotocol.io/posts/2026-07-28/ |
| Portable procedural skills | Agent Skills open standard (SKILL.md), Apache-2.0, stewarded via the Agentic AI Foundation | https://agentskills.io/specification , https://github.com/agentskills/agentskills |
| Repository-scoped agent instructions | AGENTS.md open convention (in use in this repo) | https://agents.md/ |
| Remote/independently-deployed agents (future extension point only) | Agent2Agent (A2A) 1.0 | https://github.com/a2aproject/A2A/blob/main/docs/specification.md |
| Model access | LiteLLM Python library (optional: LiteLLM Proxy via Docker) | https://docs.litellm.ai/ |
| AWF-CLI TUI | Ink 7 (React ≥19.2) + `@inkjs/ui` on Node ≥22, distributed via npm; inline rendering with append-only transcript (Ink `<Static>` pattern) | https://github.com/vercel/ink |
| Frontend↔core protocol | JSON-RPC 2.0 over stdio, shaped on the Agent Client Protocol (ACP); Python side via the official `agent-client-protocol` PyPI SDK | https://agentclientprotocol.com , https://github.com/agentclientprotocol/python-sdk |
| AWF-GUI shell | Electron (official Windows ARM64 builds; mature microphone capture), Python core as sidecar | https://www.electronjs.org/docs/latest/tutorial/windows-arm |
| Speech runtime | ONNX Runtime execution providers per the Section 16.4 hardware-profile enum (cpu/gpu/cuda/qnn across Windows/Linux × x64/arm64; Adreno OpenCL for arm64 `-gpu`), integrated through sherpa-onnx (Apache-2.0) | https://onnxruntime.ai/docs/execution-providers/QNN-ExecutionProvider.html , https://github.com/k2-fsa/sherpa-onnx |
| STT | Whisper family (MIT) — ONNX exports via sherpa-onnx as the base (incl. QNN builds for Windows ARM64); faster-whisper (CTranslate2) as the CUDA acceleration variant behind the same adapter interface | https://github.com/openai/whisper , https://github.com/SYSTRAN/faster-whisper , https://github.com/k2-fsa/sherpa-onnx |
| TTS | Kokoro-82M ONNX (Apache-2.0, 54 voices — distinct per-role voices, ~6× realtime on CPU) | https://huggingface.co/hexgrad/Kokoro-82M |
| Voice activity detection | Silero VAD (MIT, ONNX) | https://github.com/snakers4/silero-vad |
| Wake word | openWakeWord (code Apache-2.0; prebuilt ONNX models incl. `hey jarvis`, model weights CC-BY-NC-SA — operator-downloaded at setup, never redistributed with AWF) | https://github.com/dscripka/openWakeWord |
| Voice pipeline pattern | In-process VAD → streaming STT → core → streaming TTS with barge-in (Pipecat's local services as the reference pattern, not a required dependency) | https://docs.pipecat.ai/ |
| Isolation (default) | Git worktrees; each named CLI adapter's native permission/sandbox system | https://git-scm.com/docs/git-worktree |
| Isolation (optional escalation for untrusted content) | Rootless Podman (OCI) | https://docs.podman.io/en/latest/ |
| Observability (required) | Structured events persisted to the `events` table in `data/awf_db/awf.db` | Section 14 |
| Observability (optional) | OpenTelemetry Python SDK, GenAI semantic conventions, for correlation with external tooling — no Collector required for normal operation | https://opentelemetry.io/docs/specs/semconv/registry/attributes/gen-ai/ |
| Security threat model | OWASP Top 10 for Agentic Applications 2026 | https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/ |
| Content-addressing | SHA-256 | — |
| Identifiers | UUIDv7 | https://www.rfc-editor.org/rfc/rfc9562 |
| Time | UTC, RFC 3339 | — |

---

## 6. Build sequence (mandatory order)

Each phase MUST be functionally complete — with its own passing tests — before the next phase begins. "Complete" means the phase's stated exit condition is met, not that every future feature under that heading exists.

| Phase | Scope | Exit condition | Depends on |
|---|---|---|---|
| 0 — Bootstrap | Repo layout (Section 7); `data/awf_db/awf.db` schema created (Section 8); `.env` template with `AWF_SECRET_KEY` generated; `cache/sandbox/` created and gitignored | Fresh checkout + one setup command produces a valid empty `data/awf_db/awf.db` and a populated `.env` | none |
| 1 — Registry + Capability Guard | Registry file layout under `data/registry/`; Capability Record schema (Section 9.1); Capability Guard authorization function (Section 9.2) | A hand-written Capability Record loads, validates, and a sample allow/deny check returns the correct decision, with a test for each risk class R0–R3 | Phase 0 |
| 2 — Secrets | `secrets` table; Fernet encrypt/decrypt round trip; the in-process secrets-access function; `awf secret set` / `list` / `rotate-key` (Section 16.1) | Set → restart process → the secrets-access function returns the same plaintext; `awf secret list` shows names only; rotate-key re-encrypts every row and the old key no longer decrypts | Phase 0 |
| 3 — Model Gateway | LiteLLM library integration; Model Profile contract (Section 11); at least one working profile | A trivial completion call succeeds end-to-end through a registered Model Profile, sourcing its API key from Phase 2's secrets store | Phases 1, 2 |
| 4 — Durable execution core | `runs`/`steps`/`events`/`artifacts` tables; Run/Step state machine (Section 13); startup recovery scan | A synthetic no-op two-step workflow survives a mid-run process kill and resumes from the last completed step with no duplicate side effects | Phase 0 |
| 5 — Isolation + first reference adapter | Git worktree manager; `cache/sandbox/<run_id>/` lifecycle; the generic Agent Runtime Adapter interface (Section 10.1); **one** fully working named adapter (Claude Code recommended first, since it has the most complete documented permission/sandbox surface) | An Agent node in a workflow drives the reference adapter against a real repo change inside a dedicated worktree, and the change is committed only after the workflow marks the step successful | Phases 1, 3, 4 |
| 6 — Remaining named adapters | Codex CLI, Antigravity CLI (`agy`), GitHub Copilot CLI, Cline CLI, each per Section 10.2 | Each adapter passes the same synthetic task the reference adapter passed in Phase 5 | Phase 5 |
| 7 — Workflow engine | All eight node types (Section 12.2); workflow validation; one worked example workflow (produce → gate → repair) | The example workflow runs end to end against two different named adapters | Phase 4; Phase 5 plus ≥1 Phase 6 adapter (two named adapters total) |
| 8 — Verification & acceptance gate | Tiered evaluation (Section 12.3); Finding/Verdict schema; bounded repair loop; GPU-utilization sampler in `backend/src/awf/hardware/` (Section 12.3) | The example workflow's gate correctly fails on an injected defect, repairs once, and passes on the corrected candidate, with a full Verdict artifact | Phase 7 |
| 9 — Handoff pattern | Handoff node (Section 13.4); a real two-agent producer↔reviewer loop | A workflow using a Handoff node completes a bounded 2–4 hop cycle between two different adapters and terminates correctly on both the success path and the `maxHops` path | Phases 6, 8 |
| 10 — AWF core CLI + protocol | Thin `awf` command wrapper (Section 16.1) over everything above, plus the `awf serve --stdio` JSON-RPC endpoint (Section 16.3) | Every command in Section 16.1 works against a real Run created by the Phase 7 example workflow, and a scripted JSON-RPC client can drive run/status/approve over stdio | Phases 0–9 |
| 11 — AWF-CLI (TUI) | npm workspace `frontend/cli/`: inline Ink TUI with the slash-command surface of Section 16.2, driving the core exclusively through Section 16.3's protocol | Every built-in slash command in Section 16.2 works against a real Run; killing the TUI process mid-Run leaves the Run resumable via `awf resume` with no state loss | Phase 10 |
| 12 — AWF-GUI (voice) | Desktop shell `frontend/gui/`; Voice Profile registry objects (Section 16.5); Hardware Profiler + wake-word/VAD/STT/TTS adapters (Section 16.4) | A round-trip voice interaction (wake word or push-to-talk → spoken command → spoken response) works end to end; two different agent roles speak with audibly distinct registered voices; an R2 approval attempted by voice alone is refused pending on-screen confirmation | Phase 10 |

Observability (Section 14) is **not** a separate phase — every phase from Phase 0 onward MUST write to the `events` table as it is built. Retrofitting logging at the end is disallowed.

The build sequence ends at Phase 12. Section 15 documents seams every phase preserves, not scheduled work.

---

## 7. Repository & data layout

This layout is definitive. No placeholder directories, no empty stub files beyond what's noted.

```
JARVIS/
  AGENTS.md
  docs/
    AGENTIC_WORKFLOW_FABRIC_SPEC.md             (this document)
    adr/                                        (short deviation records, created on first use)
  config/                                        <- repo-owned, git-tracked
    voice/{stt,tts,vad,wake}/                    (hardware-profile manifests: one YAML per profile pinning artifact URL + sha256 — Section 16.4)
  data/                                          <- durable, relocatable; back this up
    artifacts/                                   (content-addressed: artifacts/<sha256[0:2]>/<sha256>)
    awf_db/
      awf.db                                     (SQLite: all durable state, Section 8)
    registry/                                    (git-trackable source of truth, Section 9.3)
      agents/<name>/<version>.yaml
      capabilities/<name>/<version>.yaml
      MCP/<name>/<version>.yaml
      model-profiles/<name>/<version>.yaml
      skills/<name>/<version>/SKILL.md           (+ optional scripts/, references/, assets/)
      voice-profiles/<name>/<version>.yaml
      workflows/<name>/<version>.yaml
  cache/
    sandbox/<run_id>/                            <- ephemeral, gitignored, deletable anytime
  .env                                            (gitignored: AWF_SECRET_KEY, any provider keys not routed through the secrets table, local overrides)
  backend/                                        (per AGENTS.md: Python source + .venv)
    src/awf/
      db/                                         (SQLite schema + connection — Section 8; Phase 0)
      events/                                     (append-only event writer — Section 14; Phase 0, used by every module)
      registry/                                   (load/validate/publish/index — Section 9.3; Phase 1)
      guard/                                      (Capability Guard — Section 9.2; Phase 1)
      secrets/                                    (Fernet store + secrets-access function — Section 9.4; Phase 2)
      gateway/                                    (LiteLLM Model Gateway — Section 11; Phase 3)
      engine/                                     (Run/Step state machine + recovery scan — Section 13; Phase 4)
      isolation/                                  (worktree + scratch-dir manager — Section 10.4; Phase 5)
      adapters/                                   (generic contract + named adapters — Section 10; Phases 5–6)
      workflow/                                   (definition validation + node execution incl. handoff — Section 12, 13.4; Phases 7, 9)
      gates/                                      (Trifecta orchestration, Finding/Verdict — Section 12.3; Phase 8)
      hardware/                                   (GPU-utilization sampler, Phase 8; Hardware Profiler, Phase 12 — Sections 12.3, 16.4)
      cli/                                        (the `awf` command — Section 16.1; Phase 10)
      server/                                     (`awf serve --stdio` JSON-RPC endpoint — Section 16.3; Phase 10)
      speech/                                     (STT/TTS/VAD/wake adapter contracts — Section 16.4; Phase 12)
    tests/
  frontend/                                       (one npm-workspaces monorepo — Section 16.2)
    cli/                                          (package awf-cli: TypeScript inline TUI, Node >=22 — Section 16.2)
    gui/                                          (package awf-gui: desktop voice app shell — Section 16.4)
    shared/                                       (package @awf/protocol-client: the single TS protocol client — Section 16.3)
  models/                                         <- operator-downloaded model storage, gitignored, re-fetchable
    {stt,tts,vad,wake}/                           (speech models per function, per the Section 16.4 manifests)
```

Rules:
- `data/` MUST be relocatable: nothing under it may hardcode an absolute path from the machine it was created on.
- `cache/` MUST NOT be treated as durable by any code path. Nothing under `cache/` may be a required input to resuming a Run — the startup recovery scan MUST be able to fully reconstruct pending work from `data/awf_db/awf.db` alone.
- `.env` MUST be in `.gitignore` and MUST NOT be copied when `data/` is relocated or shared; the receiving machine generates or is given its own.
- Modules under `backend/src/awf/` are created in the phase noted beside them: Phase 0 creates only `db/` and `events/`; later modules appear when their phase begins, never as empty stubs.
- `models/` MUST be gitignored and re-fetchable: it holds operator-downloaded models (some under non-commercial licenses) and MUST NOT be required for resuming a Run, included in the relocatable `data/` bundle, or redistributed with AWF. The manifests that pin its contents live in repo-owned, git-tracked `config/voice/`.

---

## 8. SQLite schema (durable state, Phase 4/0)

All tables live in one file, `data/awf_db/awf.db`. Column shapes are a contract, not literal SQL: every column below MUST exist with equivalent semantics.

| Table | Key columns | Notes |
|---|---|---|
| `runs` | `run_id` (TEXT, UUIDv7, PK) · `workflow_ref` (TEXT, `name@version#sha256:digest`) · `status` (TEXT, enum §13.1) · `input_json` · `output_json` (nullable) · `budget_json` · `created_at` · `updated_at` | One row per Run. `status` transitions only through Section 13.1's state machine. |
| `steps` | `step_id` (TEXT, PK) · `run_id` (FK) · `node_id` (TEXT) · `attempt` (INTEGER) · `status` (TEXT, enum §13.2) · `input_json` · `output_json` (nullable) · `failure_class` (TEXT, nullable, enum §13.3) · `started_at` · `ended_at` | Every attempt is its own immutable row — a retry inserts a new row with `attempt+1`, it never overwrites the prior attempt. |
| `events` | `event_id` (TEXT, UUIDv7, PK) · `run_id` · `step_id` (nullable) · `attempt` (nullable) · `prior_status` · `new_status` · `occurred_at` · `actor` · `reason_code` · `payload_json` | Append-only. This table is the required observability record — never pruned automatically. |
| `artifacts` | `artifact_id` (TEXT, PK) · `run_id` · `step_id` · `sha256` · `relative_path` (under `data/artifacts/`) · `media_type` · `artifact_type` (enum: candidate, plan, patch, report, test-result, finding, verdict) · `complete` (BOOLEAN) · `created_at` | An artifact row MUST NOT be marked `complete=true` until the bytes at `relative_path` are fully written and hashed. |
| `approvals` | `approval_id` (TEXT, PK) · `run_id` · `step_id` · `action_digest` (sha256 of the exact proposed action) · `status` (enum: pending, approved, rejected, expired) · `reason` (nullable) · `requested_at` · `decided_at` (nullable) | A changed `action_digest` invalidates any prior decision — re-request required. |
| `secrets` | `name` (TEXT, PK) · `ciphertext` (BLOB) · `created_at` · `updated_at` | Overwrite-only. Never queried by anything other than the secrets-access function. |
| `registry_index` | `kind` · `name` · `version` · `digest` (sha256) · `path` (relative, under `data/registry/`) · `trust_status` (enum: local, trusted, quarantined, blocked) · `indexed_at` | A derived, rebuildable cache over `data/registry/`. Git + the files themselves remain the source of truth; this table exists purely for fast lookup. |

---

## 9. Registry, capabilities, and authorization

### 9.1 Capability Record

Every callable capability — an MCP tool, a local Python activity, or a named CLI adapter action — MUST have a Capability Record file under `data/registry/capabilities/<name>/<version>.yaml` with this shape:

```yaml
identity: {type: mcp-tool|activity|cli-adapter-action, provider: <id>, name: <name>, version: <semver>}
schema: {input: <json-schema-ref>, output: <json-schema-ref>}
effects: {operation: read|create|update|delete|execute|communicate, reversible: true|false, idempotent: true|false, external_side_effect: true|false}
risk_class: R0|R1|R2|R3
approval: never|per-run|per-invocation
```

Risk classes: R0 = safe/read-only autoallow, R1 = reversible/idempotent bounded write, R2 = irreversible or externally communicative → per-invocation approval, R3 = prohibited. The high-risk trigger list in Section 12.2 below is the AWF-specific enumeration of what MUST be classified R2 or higher.

### 9.2 Capability Guard

The Capability Guard is a single, deterministic, versioned Python module (not a service, not a sidecar) that:
- loads the Capability Record for any requested action;
- checks it against the invoking Agent Manifest's declared capability allowlist (the manifest's `capabilities` field is a maximum, never a grant beyond what's listed);
- returns an allow/deny/approval-required decision;
- writes the decision to the `events` table before the action executes.

Authorization is code outside the model, never a model's self-assessment. The Guard MUST be pure with respect to its inputs (Capability Record + Agent Manifest + declared risk class in, decision out) so it is unit-testable.

### 9.3 Registry as source of truth

`data/registry/` (Workflows, Agents, Capabilities, MCP server definitions, Model Profiles, Voice Profiles, Skills) is git-trackable and content-addressed: each file's SHA-256 is its digest, computed at publish time. `registry_index` in SQLite is a derived cache, rebuildable at any time by rescanning `data/registry/` — it MUST NOT be treated as authoritative if it and the files on disk disagree; the files win.

Each `data/registry/MCP/<name>/<version>.yaml` file is an MCP server definition: it declares how AWF starts or connects to that MCP server (transport, command/args or URL, required environment references), which tools/resources/prompts it exposes (by name, for cross-referencing with Capability Records in `capabilities/`), and its trust status. The `provider` field on a Capability Record MUST reference a registered MCP server name when the capability type is `mcp-tool`.

Trust tiers: `local` (authored here), `trusted` (reviewed and approved), `quarantined` (installed but not usable in normal workflows), `blocked`. Anything pulled from a community source (a shared Skill, an external MCP server definition) enters as `quarantined` by default and requires an explicit promotion action to `trusted`, which is itself an R2 action.

### 9.4 Secrets

The `secrets` table stores name → ciphertext pairs. Encryption MUST use the `cryptography` package's `Fernet` recipe, with the key read from `AWF_SECRET_KEY` in `.env` at process start — never hardcoded, never logged, never written to the `events` table or any artifact. Writes are overwrite-only: setting a secret with an existing name replaces the ciphertext and `updated_at`; there is no partial update. Key rotation (`awf secret rotate-key`) MUST decrypt every row with the old key and re-encrypt with a freshly generated key inside a single transaction, then overwrite `.env` last, only after every row has been re-encrypted successfully.

Because `.env` lives outside `data/`, relocating or sharing `data/awf_db/awf.db` does **not** carry secrets in usable form: the ciphertext is portable but useless without the key, which the operator transfers through a separate, explicit channel.

**Key loss is unrecoverable.** A lost `AWF_SECRET_KEY` leaves every row in `secrets` permanently unreadable; the only remedy is re-entering each secret from its original source. The operator MUST keep a backup of `AWF_SECRET_KEY` outside both `data/` and `.env` (e.g., a password manager or offline store) — never inside the relocatable `data/` bundle.

---

## 10. Agent Runtime Adapters

### 10.1 Generic adapter contract

Every adapter — named or future — MUST implement two normalized envelopes: an `AgentInvocation` in (objective, inputs, workspace root/mode, available capabilities, available skills, constraints, completion contract, trace context) and an `AgentResult` out (`status` ∈ `COMPLETED|NEEDS_INPUT|BLOCKED|FAILED|LIMIT_EXCEEDED|CANCELED`, structured output, artifact candidates, findings, usage, termination reason). `COMPLETED` means the invocation satisfied its completion contract — it does **not** mean accepted; acceptance is computed by the Gate node, never by the agent itself.

Every adapter MUST also satisfy, at minimum:
- non-interactive/headless invocation (no adapter that requires a human at a TTY prompt for every action can be used inside a Run);
- a way to supply the objective and constraints as input without relying on shared terminal state;
- a way to read repository instructions from `AGENTS.md` (directly, if the tool supports it, or via that tool's own convention if AWF must additionally mirror `AGENTS.md` content into a tool-specific file — check each tool's current documentation, since support for reading `AGENTS.md` directly varies and changes over time);
- a documented way to constrain filesystem/network reach, even if that constraint is advisory rather than kernel-enforced (10.3 flags which tools fall into which category).

### 10.2 Named adapters

Vendor CLI flags and config keys change on each vendor's release cadence, so this section specifies the **required configuration state** for each adapter; an implementing agent MUST consult the linked docs for the current flag/key names before writing the adapter.

| Adapter | Required default configuration state | Escalation for high-risk steps | Primary docs |
|---|---|---|---|
| **Claude Code** | Non-interactive invocation; permission mode equivalent to `acceptEdits` with a repo-scoped, version-controlled allow/deny rule set; `bypassPermissions` / `--dangerously-skip-permissions` MUST NOT be used outside an explicit container/VM escalation | Enable Claude Code's OS-level sandbox (filesystem + network isolation for Bash) | https://code.claude.com/docs/en/permissions , https://www.anthropic.com/engineering/claude-code-sandboxing |
| **OpenAI Codex CLI** | Non-interactive invocation; `sandbox_mode` equivalent to `workspace-write`; `approval_policy` equivalent to `on-request`; a named profile checked into `data/registry/` (not the operator's home directory) so it's versioned with everything else | `sandbox_mode: read-only` for reviewer/adversary roles; `danger-full-access` only inside an explicit container escalation and only for an R2-approved action | https://developers.openai.com/codex/concepts/sandboxing , https://developers.openai.com/codex/config-reference |
| **Google Antigravity CLI (`agy`)** | Non-interactive/headless invocation with an explicit approval policy set (never rely on an implicit default in headless mode); permission preset equivalent to `proceed-in-sandbox`; native OS-level terminal sandbox (`enableTerminalSandbox`) enabled | Permission preset equivalent to `strict` for reviewer/adversary roles | https://antigravity.google/docs/cli/features , https://github.com/google-antigravity/antigravity-cli |
| **GitHub Copilot CLI** | Non-interactive invocation; explicit `--allow-tool`/`--available-tools` entries only — `--allow-all`/`--yolo` MUST NOT be used by AWF's default profile; a `preToolUse` hook wired to call the Capability Guard, because this adapter's permission model is application-level and advisory, **not** OS-enforced (recheck current docs before relying on it) | Enable the tool's local sandbox (`/sandbox enable`) or cloud sandbox for anything above R0/R1, since there is no default kernel-level isolation | https://docs.github.com/en/copilot/how-tos/copilot-cli/ |
| **Cline CLI** | Non-interactive invocation with structured (NDJSON) output; per-category auto-approve limited to read operations and an explicit safe-command allowlist; `--yolo` MUST NOT be used by AWF's default profile; repository instructions supplied via `AGENTS.md` (and mirrored to `.clinerules/` if the installed version does not yet read `AGENTS.md` directly) | Manual review required before any auto-approved terminal command outside the safe-command allowlist runs, regardless of adapter setting | https://docs.cline.bot/ , https://github.com/cline/cline |

### 10.3 Isolation strength by adapter group

Adapters above fall into two groups, and AWF MUST treat them differently when deciding whether a step needs the optional container escalation (10.4):

- **OS-kernel-enforced sandboxing available**: Claude Code, Antigravity CLI. These can provide real filesystem/network containment independent of the model's cooperation.
- **Application-level / advisory permission model only**: GitHub Copilot CLI (no default OS sandbox), Cline CLI (approval is a model-classified flag, not kernel-enforced). For these, a bug or a successful prompt-injection in the tool itself can bypass the permission layer. AWF MUST NOT treat an advisory-only adapter's "approved" state as equivalent in strength to a kernel-enforced one when deciding whether a step qualifies for the default (non-container) isolation tier for anything above R1.

Codex CLI sits with the kernel-enforced group on Linux/macOS (its sandbox uses OS primitives) and has a documented native Windows sandbox mode as well — verify current behavior per-platform before relying on it for R2 work.

### 10.4 Isolation model

Every mutating Run MUST execute inside a dedicated Git worktree (one worktree per Run, never shared concurrently between Runs). Every Run additionally gets a disposable scratch directory at `cache/sandbox/<run_id>/` for temp files, gitignored and safe to delete at any time — nothing durable may be written there.

This combination (worktree + scratch dir + the adapter's own permission system, per 10.2–10.3) is the **default** isolation tier and is sufficient for an operator's own repositories and locally authored work.

A **second, optional, escalation tier** — a rootless Podman container (pattern reference only, not built in the initial phases: https://docs.podman.io/en/latest/) — MUST be used instead of the default tier whenever a step:
- executes a Skill or MCP server sourced externally and still in `quarantined` trust status;
- executes code fetched from the web in the same step that fetched it;
- is classified R2 or R3 and is running on an adapter from the advisory-only group (10.3).

---

## 11. Model Gateway

LiteLLM is used as a Python library, in-process: control code imports it and calls it inside a Step; no proxy process exists in normal operation (https://docs.litellm.ai/).

A **Model Profile** is a registry object at `data/registry/model-profiles/<name>/<version>.yaml` with this required shape:

```yaml
purpose: general-reasoning|coding|judge|adversary|embedding
privacy: {maximum_data_class: public|internal|confidential, local_only: false}
candidates:
  - {provider: <litellm-provider-id>, model: <litellm-model-id>, priority: 1, enabled: true}
fallback: {mode: none|ordered, allow_quality_degrade: false}
limits: {max_input_tokens_per_call: <int>, max_output_tokens_per_call: <int>, max_cost_usd_per_call: <decimal>}
```

Candidates reference LiteLLM's own `provider/model` naming so a profile can point at any LiteLLM-supported provider, including local OpenAI-compatible endpoints (Ollama, llama.cpp server, LM Studio) for the operator's GPU/NPU-equipped machines. API keys referenced by a candidate MUST be resolved through the `secrets` table by name, never embedded in the profile file itself, since profile files are git-tracked.

**Escalation**: for one shared gateway across machines or clients, the self-hosted **LiteLLM Proxy** (Docker) MAY be introduced as a single additional local service, addressed like any other provider endpoint; the Model Profile contract is unchanged.

For a high-assurance Gate, the reviewer/adversary role's Model Profile SHOULD resolve to a different `provider` (or at minimum a different underlying model family) than the producer's profile.

---

## 12. Workflow Definition contract

### 12.1 Shape

A Workflow's `spec` MUST contain `inputSchema`, `outputSchema`, `budgets`, `nodes`, and `outputs`. The registry envelope MUST include `apiVersion`, `kind`, and `metadata` with `name`, `version`, and `digest` fields.

### 12.2 Node types

Eight node types, exactly:

| Type | Purpose | Notes |
|---|---|---|
| `activity` | Run a registered deterministic/side-effecting Python function | — |
| `agent` | Invoke a named CLI adapter through the generic contract | Adapter set: Section 10.2's five plus the generic contract |
| `approval` | Wait for an operator decision bound to an exact action digest | The default gate for anything R2+ under the attended model |
| `gate` | Evaluate candidate artifacts through a tiered Eval Suite | Tiering per Section 12.3 |
| `subworkflow` | Start a version-pinned child Workflow | — |
| `map` | Bounded fan-out over an input array | `maxItems`/`maxConcurrency` mandatory |
| `loop` | Repeat a child Workflow while a condition holds, bounded by `maxIterations` | — |
| `handoff` | Transfer control between two Agent invocations, allowing cycles | Section 13.4 |

**High-risk trigger list** (MUST be classified R2 or higher, MUST require the escalated Gate tier (12.3), regardless of what any individual capability's own default risk class says):
- any write to `data/awf_db/awf.db`, `.env`, or anything under `data/registry/capabilities/` from within a Run (i.e., a Run modifying its own authorization surface);
- any edit to `AGENTS.md`, this document, or AWF's own control-plane source under `backend/src/awf/`;
- any delete/overwrite of a file outside the Run's own Git worktree;
- any new outbound network destination added to an adapter's or capability's allowlist;
- promotion of a registry object from `quarantined` to `trusted`;
- any `git push` to a remote branch, any force-push, or any remote tag creation.

### 12.3 Gate tiering and Trifecta Validation

AWF gates are built around three distinct agent roles — **Builder**, **Verifier**, and **Adversary/Optimizer** — collectively called the **Trifecta**. This structure enforces zero-trust between production and verification: no role may assess its own output, and each role operates in a fresh `AgentInvocation` context with no shared reasoning trace.

**Role definitions**

| Role | Responsibility | Permitted operations |
|---|---|---|
| **Builder** | Writes the initial implementation: code, patches, config, or plan artifacts | Full worktree write access within the Run's dedicated Git worktree; commits to worktree only — never directly to a tracked branch |
| **Verifier** | Performs independent code review and runs regression tests against the Builder's candidate artifacts; produces structured Finding records | Read-only filesystem access + test execution only; MUST NOT write to the worktree or alter candidate artifacts |
| **Adversary/Optimizer** | Stress-tests the candidate for resource safety, safety-gate bypass attempts, and memory contamination; produces structured Finding records | Probe-only: read, execute in sandbox, write findings to `events` table; MUST NOT commit, merge, or modify candidate artifacts |

**Adapter and model-family interchangeability.** All three roles are adapter-agnostic across the kernel-enforced adapter group (Claude Code, Codex CLI, Antigravity CLI `agy`). Assignments for a given Gate evaluation MUST satisfy:
- Builder and Verifier MUST NOT share the same adapter instance.
- Adversary MUST resolve to a different model family than the Builder — use a `purpose: adversary` Model Profile that routes to a different provider.
- A workflow SHOULD rotate adapter-to-role assignments across Runs to prevent systematic blind spots from one adapter's failure modes.

**Prompt enforcement.** Each role is passed a `role` field inside the `AgentInvocation` `constraints` block (`role: builder|verifier|adversary`). The Capability Guard enforces the constraint: a `verifier`-scoped invocation MUST be denied any write capability above R0; an `adversary`-scoped invocation MUST be denied any capability that would alter the candidate artifact or worktree state. Role enforcement is performed by the Guard, not by agent self-assessment — an agent claiming a different role in its output MUST be treated as a `POLICY_DENIED` failure.

**Adversary/Optimizer obligations.** In addition to general Finding generation, the Adversary role MUST check and report structured Findings on all three of the following:

1. **Resource safety** — GPU utilization MUST NOT exceed 0.55 (55%) at any point during the candidate's execution path. The Adversary triggers an R0 hardware-probe activity at Step boundaries that samples current GPU utilization (sampler: `backend/src/awf/hardware/`); any sample above the ceiling raises a `resource_safety` Finding with `severity: high`. A candidate that triggers this Finding MUST NOT receive a passing Verdict regardless of tier.

2. **Safety-gate bypass** — The Adversary attempts a bounded set of known prompt-injection patterns against the candidate's tool-use surface and reports whether any attempt caused the Capability Guard to be bypassed, circumvented, or silenced. A confirmed bypass is a `SANDBOX_VIOLATION` failure class and terminates the repair loop immediately — it does not consume one of the 3 repair iterations.

3. **Memory contamination** — The Adversary verifies that no cross-run shared mutable state exists in `cache/` or in in-process globals: specifically, that `cache/sandbox/<run_id>/` contains no artifacts from a prior Run's `run_id`, and that no module-level mutable object in `backend/src/awf/` retains state between Step invocations.

**Gate tiers mapped to Trifecta**

Default tier (applies unless the 12.2 high-risk trigger list fires): Builder + Verifier only. The Adversary/Optimizer pass is omitted. The Verifier MAY use the same model family as the Builder.

High-risk tier (applies whenever the 12.2 trigger list fires, or the operator explicitly flags a change as high-risk): full Trifecta — Builder, Verifier, and Adversary/Optimizer — all three MUST complete and produce structured Findings before a Verdict is issued.

In both tiers: the Builder MUST NOT issue the final Verdict. A `Verdict` artifact (`artifact_type: verdict`) is written by deterministic control code aggregating structured Finding records from Verifier and Adversary — never by summarizing any agent's prose. The bounded repair loop has a maximum of 3 iterations, overridable per workflow via `budgets.maxRepairIterations`; if the candidate still fails when the limit is reached, the Run moves to `FAILED`.

---

## 13. Durable execution & the Run/Step state machine

### 13.1 Run states

Run states: `CREATED → VALIDATING → QUEUED → RUNNING → {WAITING_INPUT, WAITING_APPROVAL} → RUNNING → {SUCCEEDED, FAILED}`, with `CANCELING → CANCELED` reachable from any non-terminal state.

### 13.2 Step states and the durability rule

Step states: `PENDING, READY, RUNNING, WAITING_INPUT, WAITING_APPROVAL, RETRY_WAIT, SUCCEEDED, FAILED, SKIPPED, CANCELED`. The durability rule, adapted from the DBOS pattern referenced in Section 5: a workflow's node-selection logic MUST be deterministic given its inputs and the set of already-completed Steps; every non-deterministic operation (a model call, a tool call, a subprocess) MUST execute as a Step whose input and output are persisted to the `steps` table **before** the workflow logic proceeds past it. On process start, AWF MUST scan `runs` for any row not in a terminal state (`SUCCEEDED|FAILED|CANCELED`) and resume each from its last `SUCCEEDED` Step. The scan is triggered by running `awf resume` — by the operator now, by a scheduler later; no background process is involved.

### 13.3 Failure classes and retry

Failure classes: `TRANSIENT, TIMEOUT, INVALID_INPUT, POLICY_DENIED, APPROVAL_REJECTED, TOOL_ERROR, SANDBOX_VIOLATION, NONDETERMINISTIC_OUTPUT, INTEGRITY_FAILURE, UNKNOWN_SIDE_EFFECT, INTERNAL`. `TRANSIENT` and `TIMEOUT` are retry-eligible; all others are not by default. Every mutating invocation MUST carry an idempotency key (here: the Step's `attempt` identifier).

### 13.4 Handoff node — bounded multi-agent cycles as a normal pattern

Agent-to-agent handoff cycles (producer↔reviewer, planner↔worker, drafting↔critique) are a first-class pattern. A `handoff` node MUST declare:
- the initiating Agent reference and the receiving Agent reference (which MAY be the same Agent invoked in a fresh context, or a different named adapter);
- a structured handoff payload schema — the artifact/summary passed between hops, **never** raw conversation history (artifacts over conversational memory);
- `maxHops` (required integer ceiling, no default);
- a termination condition: a structured field the receiving Agent's output MUST set (e.g., `handoff_complete: true`) OR reaching `maxHops` OR budget exhaustion, whichever comes first.

Each hop is a normal, durable Step — a crash mid-loop resumes at the last completed hop, not at the start of the cycle. A handoff loop that reaches `maxHops` without the termination condition being set MUST move the Run to `WAITING_INPUT` for operator disposition — it MUST NOT silently continue or silently succeed.

Handoff is for locally-invoked adapters only; calling a remote, independently-deployed agent (Agent Cards, Tasks, cross-service auth) is the A2A extension point.

---

## 14. Observability (required, cross-cutting, not a phase)

The `events` table is the required, always-on observability record. Every Run/Step state transition, every Capability Guard decision, every approval decision, and every Gate verdict MUST write an event row before the corresponding action proceeds. This table MUST be queryable with plain SQL — no dependency on a separate log aggregator to answer "what happened in Run X" is acceptable.

OpenTelemetry Python SDK instrumentation, using the GenAI semantic conventions, is RECOMMENDED for anyone who wants trace correlation with external tooling (Jaeger, Grafana, etc.), but MUST NOT be required for normal operation — no Collector, no exporter configuration, should ever block a Run from completing.

Prompt/response bodies are opt-in: default event payloads carry artifact references, digests, token/byte counts, and result codes, not raw content.

---

## 15. Path to autonomous / unattended operation (extension points, not built now)

This section is documentation of seams to preserve. None of it is part of the build sequence.

- **Trigger.** Today, a Run starts because the operator runs `awf run ...`. Later, a scheduler (a cron entry, a systemd timer, or Windows Task Scheduler — a platform-native choice, not a new dependency) MAY call the same command on a timer, or a lightweight file/webhook watcher MAY call it on an event. Nothing in Sections 12–13 assumes a human typed the command.
- **Recovery.** The startup recovery scan is already unattended-safe: any process that starts and calls `awf resume` picks up incomplete work, whether a human or a scheduler started that process.
- **Approval.** The default `approval` node blocks until an operator decision. For unattended workflows, a future policy MAY allow specific, narrowly-scoped, pre-declared action classes to auto-approve within a budget ceiling — but that MUST be an explicit, reviewed change to a workflow's policy declaration (itself a high-risk-tier change per the 12.2 trigger list), never a silent default.
- **Handoff.** The Handoff node's bounded cycles already support fully autonomous multi-agent loops; nothing about the node design changes for unattended use.
- **Remote agents.** A2A is the seam for calling an independently-deployed agent once one exists; it is not needed for any locally-invoked adapter.

---

## 16. Operator interfaces: core CLI, AWF-CLI (TUI), AWF-GUI (voice)

One Python core, three surfaces. The headless `awf` command (16.1) is the scriptable base and the only component that touches durable state. **AWF-CLI** (16.2) is the interactive terminal frontend; **AWF-GUI** (16.4) is the desktop voice frontend. Both frontends are presentation layers only: every mutation they perform travels through the protocol in 16.3 into the same core code paths. No frontend may bypass the Capability Guard, mark a Gate as passed, grant an approval outside 16.1's semantics, or invoke an unregistered adapter.

### 16.1 `awf` core CLI (headless, scriptable)

```
awf run <workflow>@<version> --input <file>
awf status <run-id>
awf resume
awf approvals
awf approve <approval-id>
awf reject <approval-id> --reason <text>
awf artifacts <run-id>
awf registry validate <definition-file>
awf registry publish <definition-file>
awf secret set <name>
awf secret list                                  (names only — no CLI surface ever prints a value)
awf secret rotate-key
awf serve --stdio                                (16.3 protocol endpoint)
```

No command may bypass the Capability Guard, mark a Gate as passed, or invoke an unregistered adapter.

### 16.2 AWF-CLI — inline terminal UI

AWF-CLI is an npm-distributed TypeScript application — npm package **`awf-cli`**, installed binary **`awf-cli`** — at `frontend/cli/` (Node ≥22, Ink 7 + React ≥19.2), in the interaction style of Claude Code, Codex CLI, and Antigravity CLI. It spawns the Python core as a child process (`awf serve --stdio`) and is otherwise stateless.

`frontend/` is one npm-workspaces monorepo (root `frontend/package.json`; workspaces `cli`, `gui`, `shared`; package manager: npm; TypeScript `strict: true`). `frontend/shared/` is the package `@awf/protocol-client` — the single TypeScript protocol client (16.3) consumed by both frontends; neither frontend may implement its own protocol layer.

**Rendering (normative):**
- The TUI MUST render **inline** in the main terminal buffer and preserve native scrollback: completed output (agent transcript blocks, event log lines, verdicts) is appended permanently via Ink's `<Static>` pattern; only the active input/progress region re-renders. It MUST NOT use the alternate screen: terminal-native scrollback, copy, and tmux behavior are operator requirements.
- Streaming agent output renders incrementally in the active region and is flushed to scrollback when the step completes.

**Slash commands.** Typing `/` at the start of the input line opens a fuzzy-filtered autocomplete menu (name, description, argument hint); text after the command name becomes its arguments. Built-ins, all read/write through 16.3:

| Command | Action |
|---|---|
| `/help` | List commands and keybindings |
| `/run <workflow>@<version>` | Start a Run (prompts for input) |
| `/status [run-id]`, `/runs` | Run state, step progress, budgets |
| `/resume` | Trigger the startup recovery scan |
| `/approvals`, `/approve <id>`, `/reject <id> <reason>` | Approval queue with rendered action digests |
| `/artifacts <run-id>` | List/open artifacts |
| `/agents` | Registered Agent Manifests (adapter, capabilities, voice profile) |
| `/skills` | Registry Skills; each Skill is also directly invocable as `/<skill-name>` |
| `/workflows` | Registry Workflow definitions |
| `/capabilities` | Capability Records with risk classes |
| `/mcp` | Registered MCP servers and trust status |
| `/model` | Model Profiles |
| `/voices` | Voice Profiles (16.5) |
| `/secrets` | Secret **names** only — never values |
| `/settings` | TUI presentation settings |
| `/theme`, `/keybindings` | Presentation |
| `/clear`, `/quit` | Session housekeeping |

**Custom slash commands are registry Skills** — a Skill published at `data/registry/skills/<name>/<version>/SKILL.md` (Agent Skills standard) surfaces as `/<name>`, with its frontmatter `description` and argument hint shown in the autocomplete menu. There is no second custom-command file format: the registry Skill is the single source of truth, already versioned, digest-pinned, and trust-tiered.

**Configuration.** Frontend settings live at `~/.awf/settings.json` (user), `<repo>/.awf/settings.json` (project), `<repo>/.awf/settings.local.json` (gitignored); precedence local > project > user. The schema is exactly: `theme` (`"dark"|"light"|"system"`, default `"system"`), `keybindings` (map, default empty), `verbosity` (`"quiet"|"normal"|"verbose"`, default `"normal"`), `defaultWorkflow` (`name@version`, default unset), plus GUI-only `wakeWordEnabled` (boolean, default `false`) and `inputDevice`/`outputDevice` (audio device ids, default: system default). A key outside this schema MUST fail validation with an error naming the key. Anything that affects execution — capabilities, approvals, model routing, trust — lives in the registry and core, never in frontend settings.

**Crash safety.** The TUI holds no durable state; killing it (and the child core process with it) mid-Run MUST leave the Run resumable via `awf resume`. On next start, the TUI MUST surface any non-terminal Runs found by the recovery scan.

### 16.3 Frontend↔core protocol

- The core exposes `awf serve --stdio`: **JSON-RPC 2.0 over stdio**, frontend as parent process. Message shapes SHOULD follow the **Agent Client Protocol (ACP)** — sessions, streamed content blocks, tool-call and permission-request flows — implemented on the Python side with the official `agent-client-protocol` SDK. Where AWF needs more than ACP models (run/step queries, approvals bound to action digests, registry operations), methods are added under an `awf/` namespace rather than distorting ACP shapes. ACP shaping makes AWF drivable by ACP-capable editors (Zed, JetBrains, Neovim).
- **Method surface (exhaustive):** `awf/run.start`, `awf/run.status`, `awf/run.list`, `awf/run.resume`, `awf/approval.list`, `awf/approval.approve`, `awf/approval.reject`, `awf/artifact.list`, `awf/artifact.read`, `awf/registry.list`, `awf/registry.get`, `awf/registry.validate`, `awf/registry.publish`, `awf/secret.set`, `awf/secret.listNames`, and `awf/events.subscribe` (server→client stream of `events` rows). Each method maps 1:1 onto a 16.1 operation, a registry read, or a Section 8 table read. Adding a method is a change to this list; a frontend needing an unlisted method fixes this section, never reads `data/` directly.
- Stdio is the only transport in the initial build: no ports, no auth surface, no orphaned daemons. A local HTTP/WebSocket daemon mode for multi-client or detached use is a documented escalation, not built now.
- The protocol adds no authority: every mutating method maps 1:1 onto a core operation that passes the Capability Guard and writes `events` rows exactly as if invoked from 16.1.

### 16.4 AWF-GUI — desktop voice app

AWF-GUI (`frontend/gui/`) is a desktop application whose defining capability is **voice**: the operator can hear agent feedback and speak to the system, with each agent role speaking in its own persona and voice (16.5).

- **Shell:** Electron with the Python core as a sidecar over the 16.3 protocol. The renderer UI is React — the same UI framework as AWF-CLI. The GUI is the `awf-gui` package in the `frontend/` workspace (16.2).
- **Activation:** wake word **"hey jarvis"** via openWakeWord's prebuilt ONNX model, plus push-to-talk, which MUST always remain available and MUST be the default until the operator downloads the wake-word model. openWakeWord's code is Apache-2.0 but its prebuilt model weights are CC-BY-NC-SA: the model MUST be fetched by the operator at setup (into `models/wake/`, gitignored) and MUST NOT be redistributed with AWF. Wake-word detection runs locally and continuously only while the operator has enabled it; the microphone stream is never sent to any network service for activation.
- **Pipeline:** wake word / push-to-talk → Silero VAD (endpointing, barge-in) → Whisper STT → core → Kokoro TTS. One selected engine per function behind the adapter contract: audio in → text out; text + voice_id in → audio out; both streaming.
- **Hardware Profiler (canonical profile enum):** the Hardware Profiler is a deterministic probe module (`backend/src/awf/hardware/`) that resolves the host to exactly one profile ID. It runs at Phase 12 voice setup and before any voice model is downloaded or loaded, writing its resolution and probe evidence to the `events` table. The canonical profile IDs:

  | | CPU | GPU | CUDA | QNN |
  |---|---|---|---|---|
  | Windows x64 | `windows-x64-cpu` | `windows-x64-gpu` | `windows-x64-cuda` | — |
  | Windows arm64 | `windows-arm64-cpu` | `windows-arm64-gpu` | — | `windows-arm64-qnn` |
  | Linux x64 | `linux-x64-cpu` | `linux-x64-gpu` | `linux-x64-cuda` | — |
  | Linux arm64 | `linux-arm64-cpu` | `linux-arm64-gpu` | — | `linux-arm64-qnn` |

  On arm64 (both OSes), `-gpu` denotes Qualcomm **Adreno GPU acceleration via OpenCL**. On x64, `-gpu` denotes a probe-verified non-CUDA GPU execution provider (DirectML on Windows; the vendor GPU EP on Linux). A profile above `-cpu` is valid only when the Profiler verifies its execution provider actually loads. Resolution order per arch is QNN/CUDA → GPU → CPU, and **every profile falls back to its arch's `*64-cpu` profile** — the guaranteed floor on every host. WSL2 resolves as Linux.
- **Model acquisition (Phase 12 setup, hardware-aware):** speech models are never bundled. Setup downloads the variant of each selected model matching the resolved hardware profile into the gitignored `models/` tree (`models/stt/`, `models/tts/`, `models/vad/`, `models/wake/`), plus the `*64-cpu` fallback artifact whenever the resolved profile is above CPU. The operator accepts each model's upstream license at download. Every probe result and fallback decision is written to the `events` table.
- **Selection basis (decision record):** *STT = Whisper* — ONNX exports via sherpa-onnx include QNN builds for Snapdragon NPUs; faster-whisper is the fastest CUDA path. *TTS = Kokoro-82M* — Apache-2.0, 54 voices in one install (audibly distinct role personas), ~6× realtime on CPU, ONNX-native. *VAD = Silero* — MIT, ONNX, ~2 MB. *Wake word = openWakeWord* — Apache-2.0 code, ONNX models, prebuilt `hey jarvis`. Replacing a selection is an ADR against the same adapter contract.
- **Pinned model variants.** Hardware-profile manifests under repo-owned `config/voice/{stt,tts,vad,wake}/` — one YAML per canonical profile ID per function (`<profile-id>.yaml`, e.g. `config/voice/stt/windows-arm64-qnn.yaml`) — pin the exact artifact URL and SHA-256 digest for every speech model and are the authority for bytes; the table below is their initial content. Profiles that pin identical artifacts repeat the pin. Downloads land in the matching `models/<function>/` directory. Only the STT artifact varies by acceleration class — TTS, VAD, and wake word use one artifact in every profile, with only the execution provider changing at runtime:

  | Function | `*-cpu` / `*-gpu` profiles | `*-cuda` profiles | `*-qnn` profiles |
  |---|---|---|---|
  | STT | Whisper `small` int8 ONNX (sherpa-onnx export) | faster-whisper `large-v3-turbo` | Whisper `base` QNN build (sherpa-onnx) |
  | TTS | Kokoro-82M v1.0 ONNX | same artifact | same artifact |
  | VAD | Silero VAD ONNX (sherpa-onnx-packaged) | same artifact | same artifact |
  | Wake word | openWakeWord `hey_jarvis` ONNX | same artifact | same artifact |
- **Text-first invariant:** every recognized utterance is displayed as text before it is submitted to the core, and every spoken response has a visible transcript. Voice is an alternate modality over the same command surface as 16.2 — there are no voice-only capabilities.
- **Approval rule:** an approval decision for an R2+ action MUST NOT be granted from voice input alone. The GUI MUST display the exact action digest and require a non-voice confirmation (click/keypress). Voice MAY acknowledge R0/R1 prompts.
- **Resource ceiling:** local speech inference counts toward the GPU-utilization ceiling (Section 12.3); under contention with a running Gate evaluation, STT/TTS MUST degrade to CPU/smaller models rather than push GPU utilization past the limit.

### 16.5 Personas and Voice Profiles

A **Voice Profile** is a registry object at `data/registry/voice-profiles/<name>/<version>.yaml` — versioned, digest-pinned, and trust-tiered like every other registry kind:

```yaml
persona:
  name: <display name>
  description: <one-line character summary, shown in both frontends>
  style_prompt: <short speaking-style instruction — tone/delivery only>
tts:
  candidates:
    - {engine: kokoro|cloud:<provider>, model: <id>, voice_id: <id>,
       speed: <float>, style: {<engine-specific: exaggeration | audio_tags | instructions>},
       priority: 1, enabled: true}
  fallback: {mode: none|ordered, allow_quality_degrade: true|false}
privacy: {local_only: true|false}
limits: {max_seconds_per_utterance: <int>}
```

Rules:
- An Agent Manifest MAY declare `voice: <name>@<version>`. When that agent's output is spoken, the GUI resolves the referenced profile; agents without a profile use the `narrator` profile.
- Bootstrap (Phase 12 setup) MUST publish four Voice Profiles at version `1.0.0`, all Kokoro: `narrator` (voice_id `bf_isabella`), `builder` (`am_michael`), `verifier` (`bf_emma`), `adversary` (`bm_george`). These are the defaults for the Trifecta roles and unassigned agents; the operator edits them like any other registry object.
- Roles active in the same workflow SHOULD map to audibly distinct `voice_id`s (e.g., Builder/Verifier/Adversary as three different Kokoro voices) so the operator can attribute speech without looking at the screen.
- `persona.style_prompt` styles **delivery only** — the phrasing and tone of spoken/rendered feedback. It MUST NOT be injected into the agent's working prompt, MUST NOT alter the Trifecta role constraints, and MUST NOT change the substance of any Finding or Verdict: findings are verbalized faithfully, styled only in delivery. Persona is a presentation attribute, never an authorization or behavior attribute.
- `cloud:<provider>` candidates MUST be skipped when `privacy.local_only: true`; their API keys resolve by name through the secrets table, never appearing in the profile file, which is git-tracked.
- **License isolation:** the core links only permissively-licensed speech code. Concretely for the selected stack: Kokoro G2P runs through `misaki`'s permissive path, and the GPL `espeak-ng` fallback MUST NOT be imported or compiled into the core. Non-commercial model weights (including openWakeWord's prebuilt models) MUST NOT be redistributed with AWF — they exist only in the operator-downloaded `models/` tree.

---

## 17. Licensing

This specification and the reference implementation it describes are licensed **Apache License 2.0**. Source files SHOULD carry an `SPDX-License-Identifier: Apache-2.0` header; a `NOTICE` file at the repository root is REQUIRED once third-party code is vendored.

The five named CLI adapters remain governed by their own upstream terms — verify current terms before redistribution. Apache-2.0 governs the orchestrator (this spec, the registry format, the Capability Guard, the adapter contracts), not the tools it drives.

---

## 18. Explicit prohibitions

1. No workflow logic may bypass the Capability Guard (Section 9.2).
2. No agent invocation may write its own acceptance verdict (Section 12.3).
3. No secret may appear in plaintext in `data/registry/`, the `events` table, or any artifact.
4. No handoff loop may omit `maxHops` (Section 13.4).
5. No mutating step may run outside its Run's dedicated Git worktree.
6. No registry object may be republished under an existing `name@version` with different bytes — a content change requires a new version.
7. No workflow may promote a `quarantined` registry object to `trusted` without that promotion itself passing through the Capability Guard as an R2 action.
8. `.env` MUST NOT be committed, and MUST NOT travel with `data/` when it is relocated or shared.
9. No CLI adapter may be invoked with an unattended, fully-permissive flag (`--dangerously-skip-permissions`, `--yolo`, `--allow-all`, `danger-full-access`, or equivalent) as a default profile — only as an explicit, logged escalation inside the container tier (Section 10.4).
10. No two Trifecta roles (Builder, Verifier, Adversary) may share the same adapter instance within a single Gate evaluation. Role isolation is enforced by the Capability Guard's `role` constraint field — agent self-declaration of a different role is treated as `POLICY_DENIED`.
11. No frontend (AWF-CLI or AWF-GUI) may read or write durable state directly — all mutations go through the Section 16.3 protocol into core code paths. Frontend settings files hold presentation state only.
12. No R2+ approval may be granted from voice input alone (Section 16.4) — on-screen action digest plus non-voice confirmation is required.
13. No persona or voice styling may alter an agent's working prompt, role constraints, or the substance of any Finding or Verdict (Section 16.5).
14. No speech model with a non-permissive or non-commercial license (GPL engines, CC-BY-NC weights including openWakeWord's prebuilt models) may be bundled into the distributed artifact — such models are operator-downloaded into the gitignored `models/` tree only.

---

## 19. Research basis

| Topic | Source |
|---|---|
| MCP 2026-07-28 (current spec) | https://modelcontextprotocol.io/specification/2026-07-28 , https://blog.modelcontextprotocol.io/posts/2026-07-28/ |
| Agent Skills open standard | https://agentskills.io/specification |
| AGENTS.md convention | https://agents.md/ |
| A2A 1.0 | https://github.com/a2aproject/A2A/blob/main/docs/specification.md |
| Lightweight durable-execution pattern (reference, not a dependency) | https://docs.dbos.dev/ |
| Anthropic — building effective agents / effective harnesses (basis for Trifecta: independent reviewer in fresh context, producer/reviewer separation, artifacts-over-memory) | https://www.anthropic.com/engineering/building-effective-agents , https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents |
| Claude Code permissions & sandboxing | https://code.claude.com/docs/en/permissions , https://www.anthropic.com/engineering/claude-code-sandboxing |
| OpenAI Codex CLI sandboxing & config | https://developers.openai.com/codex/concepts/sandboxing , https://developers.openai.com/codex/config-reference |
| Google Antigravity CLI | https://antigravity.google/docs/cli/features , https://github.com/google-antigravity/antigravity-cli |
| GitHub Copilot CLI permissions | https://docs.github.com/en/copilot/how-tos/copilot-cli/ |
| Cline CLI | https://docs.cline.bot/ , https://github.com/cline/cline |
| LiteLLM | https://docs.litellm.ai/ |
| `cryptography` / Fernet | https://cryptography.io/en/latest/fernet/ |
| OWASP Top 10 for Agentic Applications 2026 (basis for Trifecta zero-trust: self-verdict prohibition, prompt injection as gate-bypass vector, excessive agency) | https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/ |
| OpenTelemetry GenAI semantic conventions | https://opentelemetry.io/docs/specs/semconv/registry/attributes/gen-ai/ |
| Rootless Podman | https://docs.podman.io/en/latest/ |
| Ink (inline TUI framework; basis for AWF-CLI rendering rules) | https://github.com/vercel/ink |
| Agent Client Protocol (ACP) + official Python SDK (basis for Section 16.3) | https://agentclientprotocol.com , https://github.com/agentclientprotocol/python-sdk |
| Codex app-server / stdio JSON-RPC precedent | https://github.com/openai/codex/blob/main/codex-rs/docs/codex_mcp_interface.md |
| Slash-command & settings conventions (Claude Code commands/skills/settings) | https://code.claude.com/docs/en/commands , https://code.claude.com/docs/en/skills , https://code.claude.com/docs/en/settings |
| ONNX Runtime QNN execution provider (Windows ARM64 NPU) | https://onnxruntime.ai/docs/execution-providers/QNN-ExecutionProvider.html |
| sherpa-onnx (Apache-2.0 speech integration layer: STT/TTS/VAD/KWS, QNN support) | https://github.com/k2-fsa/sherpa-onnx |
| Whisper / faster-whisper (selected STT + CUDA acceleration variant) | https://github.com/openai/whisper , https://github.com/SYSTRAN/faster-whisper |
| Kokoro-82M (selected TTS — Apache-2.0, 54 voices) | https://huggingface.co/hexgrad/Kokoro-82M |
| Silero VAD (selected VAD — MIT, ONNX) | https://github.com/snakers4/silero-vad |
| openWakeWord (`hey jarvis` prebuilt ONNX model; Apache-2.0 code, CC-BY-NC-SA model weights) | https://github.com/dscripka/openWakeWord |
| Pipecat (reference local voice-pipeline pattern) | https://docs.pipecat.ai/ |
| Electron Windows ARM64 support (basis for GUI shell choice) | https://www.electronjs.org/docs/latest/tutorial/windows-arm |
| Agent-facing documentation authoring guidance (basis for Section 1's definition-over-ambiguity rule and Section 2's system boundaries) | https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-4-best-practices , https://developers.openai.com/cookbook/examples/gpt-5/gpt-5_prompting_guide , https://code.claude.com/docs/en/best-practices , https://kiro.dev/docs/specs/best-practices/ , https://addyosmani.com/blog/good-spec/ |
