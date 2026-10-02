# ADR-0035: automated continuous integration and static license attribution

## Status

Implemented. Acceptance evidence: `.github/workflows/ci.yml` validates syntax, formatting, and test execution across both Python 3.12 (`scripts/validate_backend.py ci`) and Node.js 24 LTS (`npm test --workspaces`); static attribution verified in `NOTICE`; vulnerability reporting established in `SECURITY.md`.

## Context

The repository operating contract (`AGENTS.md`) establishes that testing is evidence, not a work product, and mandates reproducible verification. Prior to this decision, validation occurred entirely via local CLI execution (`scripts/validate_backend.py ci` and `npm --prefix frontend test --workspaces`). While rigorous, manual execution creates operator overhead and risk of unverified branches.

Additionally, ADR-0026 and `plans/remaining-gap-remediation.md` identified the need for:
1. Automated CI pipelines running backend protocol parity, argument consistency, linting, and regression suites alongside frontend workspace test suites.
2. Plaintext static license attribution (`NOTICE`) acknowledging open-source dependencies (Kokoro-82M, Whisper, Silero VAD, openWakeWord, LiteLLM).
3. Coordinated vulnerability disclosure policy (`SECURITY.md`).

## Decision

1. **Continuous Integration Workflow (`.github/workflows/ci.yml`)**:
   - Establish GitHub Actions workflow triggered on push and pull request to `main`.
   - `backend` job: Ubuntu runner, Python 3.12, installs dev dependencies, executes `python scripts/validate_backend.py ci`, and archives validation reports.
   - `frontend` job: Ubuntu runner, Node.js 24 LTS, installs dependencies via `npm ci`, runs `npm test --workspaces --if-present`, and builds packages via `npm run build --workspaces --if-present`.
   - Concurrency group cancels redundant in-flight runs on the same branch.

2. **Static License Attribution (`NOTICE`)**:
   - Maintain a top-level plaintext `NOTICE` file with upstream citations, licenses (Apache 2.0, MIT), and descriptions for embedded speech, voice, and gateway components.

3. **Security Policy (`SECURITY.md`)**:
   - Publish vulnerability disclosure guidelines requiring private coordinated disclosure before public reporting, defining `0.1.x` as the supported release series.

## Consequences

- Regression verification is completely automated on every push and PR without manual intervention.
- Shipped third-party component licenses are fully documented and compliant.
- No administrative daemons, external collectors, or container escalations are introduced, preserving the minimal single-operator footprint required by `plans/remaining-gap-remediation.md`.
