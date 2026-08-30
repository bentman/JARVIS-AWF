# AGENTS.md - Repository Operating Contract for JARVIS-AWF

## Source Of Truth

1. Explicit user instruction.
2. This `AGENTS.md`.
3. `docs\AGENTIC_WORKFLOW_FABRIC_SPEC.md` (AWF) — active implementation target.
4. Architecture and implementation docs under `docs/`.
5. Source code and tests in this repo.

- If sources conflict, follow higher-priority source and record conflict in implementation notes or final report.
- `AGENTS.md` may refine repository-local operating rules, but deviations from MUST/MUST NOT requirements in `docs\AGENTIC_WORKFLOW_FABRIC_SPEC.md` require an ADR.  
- Honor `.agentignore` as a repository contract for folders/files agents should not read, index, embed, or transmit. 

## Development Principles

- KISS: choose the smallest design that satisfies the current contract.
- YAGNI: do not add services, schemas, providers, or abstractions before a caller exists.
- DRY: centralize shared contracts for capabilities, events, manifests, and harness targets.
- Idempotent: repeated commands must be safe and produce the same state unless inputs change.
- Deterministic: tests and generators must avoid hidden network, clock, random, and host-state dependencies unless explicitly marked live.

Always prefer to use existing shapes, patterns, code, and tests over creating new ones.

## Platform Contract

The system must support these targets without assuming any one acceleration path:

- Linux (and Windows WSL2/WSLg + available accelerators).  
- Windows AMD64 (with NVIDIA GPU CUDA).  
- Windows ARM64 (with Qualcomm GPU Adreno/OpenCL).  
- Windows ARM64 (with Qualcomm NPU QNN).  
- CPU-only fallback on every platform.  

> Every hardware claim must come from a capability probe or operator-provided command output.  
> GPU, NPU, camera, audio, WSLg, and model-provider availability are runtime facts, not assumptions.  

## Implementation Rules

- Prefer Python `>=3.12,<3.15` for repo work.  
  - If a minimal Linux OS (WSL image) lacks, stop and request `altinstall`.  
- Use the workspace venv Python for Python commands.  
  - `python3.12 -m venv backend/.venv` # Linux (bash)  
    - `backend/.venv/bin/python` # Linux/WSL  
  - `py -m venv .\backend\.venv` # Windows (pwsh)  
    - `.\backend\.venv\Scripts\python.exe` # Windows  
- Keep platform-specific behavior behind adapters or capability checks.
- Prefer Python standard library for foundation code unless a dependency materially reduces complexity.
- Follow the AWF reference implementation choices (`docs\AGENTIC_WORKFLOW_FABRIC_SPEC.md`) unless an ADR supersedes them.
- Use simple, community-standard shapes:
  - agents: directory with `main.py`, `manifest.yaml`, health endpoint or health command, structured logs.
  - MCP servers: JSON-RPC/MCP-compliant tools/resources/prompts, JSON Schema inputs, explicit errors, timeouts, audit logs.
  - skills: `SKILL.md` as the entry point, scoped instructions, optional scripts/templates/examples directories.
- Generated MCP/agent/service artifacts must be linted before registration.
- Published workflows, agents, activities, policies, eval suites, skills, capabilities, model profiles, and sandbox profiles must be semantic-versioned and digest-pinned.
- Registry root by durability/portability, not convenience:
  - `cache/` — non-durable/temp; untracked, safe to delete anytime.
  - `config/app_registry/` — repo-tracked application defaults; no operator-specific endpoints/secrets/local paths.
  - `data/registry/` — operator data and customizations; portable, untracked, operator's own backup responsibility.
- Untrusted commands and agent steps must run through declared sandbox profiles; direct host execution requires an explicit approved exception.
- Secrets must never be logged, written to flywheel records, or sent to external APIs without redaction policy review.
- Destructive operations, credential rotation, backup restore, and chaos testing default to dry-run or disabled until explicitly enabled.

## Validation

- Update tests with every behavioral change - add new only when shape/pattern does not exist.
- Use proportional validation:
  - Comment/docstring-only edits should not trigger a test run by default; use a quick syntax/import/type check only when useful.
  - A change to one function or module should run the focused tests for that file/module first.
  - Run broad `ci`/full frontend tests at natural milestones: before a changelog entry, before reporting a multi-file implementation complete, or when targeted coverage cannot bound the risk.
  - When unsure, prefer the smallest command that can falsify the change. The full suite is the exception, not the default check-in step.
- Hardware-dependent tests must report `SKIP` with a reason when the provider is unavailable, unless the test explicitly requires that provider.
- The harness should expose focused targets plus a cumulative smoke target.
- Do not claim runtime support from documentation alone; include command evidence.
- Producer reports are evidence, not acceptance; final acceptance requires independent gate evidence where applicable.

## Testing Discipline And Test-Sprawl Control

Testing is evidence, not a work product. Preserve the smallest durable test surface that can falsify the changed behavior.

- Search existing tests before creating any test artifact.
- Prefer extending, parameterizing, reformatting, or consolidating an existing test over adding another test or fixture.
- Add a new test only for a distinct contract, branch, regression, boundary, or failure mode that existing tests cannot represent cleanly.
- Do not add tests to justify implementation choices, restate existing assertions, increase test counts, or duplicate coverage at another layer without a distinct risk reason.
- Prefer the cheapest layer that can falsify the change; use integration/E2E only when the changed behavior crosses that boundary.
- Do not create new test helpers, fixture frameworks, test directories, snapshots, or harness paths unless the existing shape cannot express the required behavior.
- Before adding a test, identify the unique failure it would catch. If an existing test already catches it, do not add another.
- Follow the proportional validation ladder already defined above; passing a focused check does not require automatically escalating to broader suites.
- After a corrective edit, rerun the failed/focused test first.
- Do not rerun an unchanged passing command for reassurance.
- Do not repeat the same failing command when code, tests, environment, and inputs are unchanged; diagnose or report the blocker.
- Run broad `ci`/full-suite validation once at a natural closeout milestone when required by blast radius or repository policy, not after each intermediate edit.
- Report exactly what each command proves; test quantity and repeated green runs are not completion evidence.
- When redundant tests are encountered within task scope, prefer consolidation or removal of obsolete duplication while preserving the strongest behavioral contract.
