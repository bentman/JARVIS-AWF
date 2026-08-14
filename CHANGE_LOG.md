# CHANGE_LOG.md
> No edits/reorders/deletes of past entries.  
> Amendments require approved corrective work.

## Rules
- Write an entry for codebase change only after objective is complete and supported by evidence.
- Ordering: Entries are maintained in descending chronological order (newest first, oldest last).
- Append location: New entries must be added at the top directly under `## Change Entries`.
- Each entry must include:

- Timestamp: `YYYY-MM-DD HH:MM`
  - Host class(es): validated on
  - Summary: description of capability added, 1–2 lines, past tense
  - Scope: exact folders, files, tests, or areas
  - Validation: reproducible evidence
  - Notes: optional constraints or exclusions

---

## Change Entries

- Timestamp: 2026-08-14 08:57
  - Host class(es): Windows AMD64 documentation validation
  - Summary: Shortened the Windows and Linux QuickStart docs around the bootstrap/helper path and rewrote the README to describe the current project state without marketing language.
  - Scope: `docs/QuickStart-{windows,linux}.md`, `README.md`, `CHANGE_LOG.md`.
  - Validation: QuickStart/README grep found no stale `AWF_REPO_ROOT`, `AWF_CORE_COMMAND`, direct venv `awf`, or direct venv Python command instructions; `git diff --check` passed.
  - Notes: QuickStart now points deeper operation, troubleshooting, and validation details to `docs/OperatorsGuide.md`; contributions are open for ideas, feedback, and bug reports, not fork/branch work.

- Timestamp: 2026-08-14 08:49
  - Host class(es): Windows AMD64 operator-launch validation; Linux/WSL helper syntax and function validation outside the sandbox
  - Summary: Added session-local AWF command helpers so operators can run `awf`, `awf-speech`, `awf-gui`, and `awf-cli` from the repo root without global PATH edits or backend environment-variable preambles.
  - Scope: `scripts/{use-awf.ps1,use-awf.sh,bootstrap.ps1,bootstrap.sh}`, `docs/OperatorsGuide.md`, `CHANGE_LOG.md`.
  - Validation: PowerShell helper dot-source resolved all six helper functions; `awf doctor` passed through the helper; Bash helper syntax passed outside the sandbox after WSL/Bash returned `E_ACCESSDENIED` inside the sandbox; Bash helper sourcing exposed the expected functions; operator guide grep found no stale `AWF_REPO_ROOT`, `AWF_CORE_COMMAND`, or direct venv `awf` command instructions; `git diff --check` passed.
  - Notes: Helpers are session-local functions only; no profile, global install, PATH mutation, or persistent alias is introduced.

- Timestamp: 2026-08-14 07:57
  - Host class(es): Windows AMD64 backend/frontend validation
  - Summary: Completed the AWF DRY cleanup by centralizing protocol/CLI drift checks, splitting `core_ops` into real domain ops modules, removing machine activity placeholders, moving voice/LLM settings into registry-shaped objects, schema-backing every registry kind, and eliminating the remaining approval/gate import cycle and stale config directories.
  - Scope: `.gitignore`, `backend/src/awf/approval_policy.py`, `backend/src/awf/{artifacts.py,pyexec.py,setup.py}`, `backend/src/awf/{cli,gates,llm,machine,ops,protocol,registry,server,speech,workflow}`, `config/app_registry/{hardware-voice-manifests,llm-servers}`, `data/registry/{hardware-voice-manifests,llm-servers}`, `frontend/shared/src/{client.ts,protocol.generated.ts,types.ts}`, `scripts/{generate_protocol.py,validate_backend.py}`, renamed backend tests/fixtures, quickstart/spec/helper docs, aligned ADRs, `CHANGE_LOG.md`.
  - Validation: Focused backend pytest passed (`126 passed`); generated protocol check passed; argparse parity check passed with argument metadata comparison; backend CI passed (`642 passed, 17 deselected`, report `reports/validation/20260814125646-ci.txt`); frontend shared tests passed outside the Windows sandbox after the known Vite `spawn EPERM` sandbox failure (`15 passed`).
  - Notes: `awf.cli.core_ops` remains a public compatibility re-export; internal implementation and tests now use `awf.ops.*` domain modules and generated-only protocol files.

- Timestamp: 2026-08-12 14:28
  - Host class(es): Windows AMD64 focused backend/frontend validation
  - Summary: Closed the B11-B15 registry/governance gaps by adding direct Skill invocation, fail-closed MCP execution for unguarded adapters, deterministic workflow proposal verification, a shipped `network_fetch` Capability Record, complete memory registry data-root scaffolding, and strict Workflow `metadata.digest` format validation.
  - Scope: `backend/src/awf/{authoring/workflow.py,cli/core_ops.py,db/{bootstrap.py,schema.py},engine/agent_step.py,server/stdio.py}`, `frontend/{shared,cli}`, `config/app_registry/{capabilities/network_fetch/1.0.0.yaml,workflows/*/1.0.0.yaml}`, `data/registry/{memory-profiles,semantic-memories}/.gitkeep`, `.gitignore`, focused backend/frontend tests, `docs/adr/{0003,0004,0011,0012,0019,0020,0021,0022,0023}*.md`, `CHANGE_LOG.md`.
  - Validation: Focused backend pytest passed (`36 passed` after schema fix; earlier focused slice `42 passed` with two proposal verifier failures corrected); frontend shared client test passed (`12 passed`) and AWF-CLI commands test passed (`37 passed`) outside the Windows sandbox after Vite `.vite-temp` EPERM inside the sandbox.
  - Notes: MCP execution is currently guarded only for Copilot; adapters whose MCP tool calls would be ungoverned deny `mcp_refs` before adapter startup.

- Timestamp: 2026-08-12 14:17
  - Host class(es): Windows AMD64 focused backend/frontend validation
  - Summary: Wired execution memory retrieval, made the default assistant workflow model-backed, moved voice default workflow handling into core, added stdio event snapshots with concurrent request handling, and enabled browser speech recognition for live GUI push-to-talk.
  - Scope: `backend/src/awf/{engine/agent_step.py,workflow/{activities.py,engine.py},cli/core_ops.py,server/stdio.py}`, `frontend/shared`, `frontend/gui/src/{main,preload,renderer}`, focused backend/frontend tests, `config/app_registry/capabilities/assistant_reply/1.0.0.yaml`, `docs/adr/{0016,0017,0018,0020,0023,0024}*.md`, `CHANGE_LOG.md`.
  - Validation: Focused backend pytest passed (`27 passed`); backend unit validation passed (`311 passed`, report `reports/validation/20260812191805-unit.txt`); GUI voice-focused tests passed (`14 passed`); shared protocol tests passed (`12 passed`).
  - Notes: Direct pytest emitted the known Windows sandbox `.pytest_cache` warning; the pre-existing hardware-probe activity test can stall in sandbox and was excluded from the focused backend batch.

- Timestamp: 2026-08-12 13:39
  - Host class(es): Windows AMD64 focused backend validation
  - Summary: Fixed registry model-profile defaults, workflow self-digest enforcement, conn-less registry integrity checks, and distinct hosted LLM completion authorization.
  - Scope: `backend/src/awf/{registry/kinds.py,registry/resolve.py,cli/core_ops.py,gateway/client.py}`, `backend/tests/{unit,integration}`, `config/app_registry/{model-profiles/resident-mind/1.0.0.yaml,capabilities/hosted_llm_complete/1.0.0.yaml,workflows/*/1.0.0.yaml}`, `docs/adr/{0001,0012,0017,0019}*.md`, `CHANGE_LOG.md`.
  - Validation: Focused registry/authoring/gateway pytest passed (`56 passed`); gateway-focused pytest passed (`22 passed`); backend unit validation passed (`311 passed`, report `reports/validation/20260812183947-unit.txt`).
  - Notes: Pytest emitted the known Windows sandbox `.pytest_cache` write warning; test results were green.

- Timestamp: 2026-08-12 13:21
  - Host class(es): Windows AMD64 backend validation
  - Summary: Aligned Win/Linux path handling and registry skill fixture placement, using portable relative metadata paths and config-owned demo skills.
  - Scope: `backend/src/awf/{adapters/copilot_cli.py,authoring/workflow.py,cli/core_ops.py,machine/policy.py,memory/proposals.py,registry/index.py}`, `backend/tests/{unit,integration}`, `config/app_registry/skills/demo-skill/1.0.0/SKILL.md`, `docs/adr/0004-skills-registry-schema.md`, `CHANGE_LOG.md`.
  - Validation: Focused registry/skill tests passed (`37 passed`); full backend unit validation passed (`309 passed`, report `reports/validation/20260812181832-unit.txt`).
  - Notes: Lint remains blocked by pre-existing Ruff formatting drift outside this focused change.

- Timestamp: 2026-08-11 23:59
  - Host class(es): Windows AMD64 syntax and tee smoke validation
  - Summary: Fixed Windows bootstrap reports to capture native command stdout/stderr with `Tee-Object` instead of relying on `Start-Transcript`.
  - Scope: `scripts/bootstrap.ps1`, `docs/adr/0015-validation-category-reports.md`, `CHANGE_LOG.md`.
  - Validation: PowerShell bootstrap parsed OK; a native Python stdout/stderr smoke piped through `Tee-Object` wrote both streams to `cache/temp/tee-smoke.txt`; `git diff --check` passed.
  - Notes: Microsoft PowerShell docs describe `Tee-Object` as writing output to a file and the pipeline; the PowerShell team documents native command output as a `Start-Transcript` gap.

- Timestamp: 2026-08-11 23:59
  - Host class(es): Windows AMD64 syntax/provision validation
  - Summary: Added durable bootstrap diagnostics so every wrapper run leaves a timestamped report with full setup evidence for issue reporting.
  - Scope: `scripts/bootstrap.{ps1,sh}`, `README.md`, `docs/{OperatorsGuide.md,QuickStart-linux.md,QuickStart-windows.md,adr/0015-validation-category-reports.md}`, `CHANGE_LOG.md`.
  - Validation: PowerShell bootstrap parsed OK; `awf.setup --provision` reported `hw-ort-cuda,speech,wake-word,dev`; docs grep confirmed the report path is documented; `git diff --check` passed.
  - Notes: Linux Bash syntax validation could not run in this Windows shell because WSL/Bash returned `E_ACCESSDENIED`.

- Timestamp: 2026-08-11 23:59
  - Host class(es): Windows AMD64 validation; Linux/WSL x64 CUDA by operator output and JARVISv7 read-only reference
  - Summary: Restored speech and wake to the normal host-selected bootstrap path, using the sibling-project Linux OpenWakeWord `--no-deps` install pattern while keeping Windows ARM64 STT on the ONNX CPU/QNN-capable path.
  - Scope: `pyproject.toml`, `scripts/bootstrap.{sh,ps1}`, `backend/src/awf/{setup.py,hardware/provisioning.py,hardware/readiness.py,speech/wake_openwakeword.py}`, `backend/tests/unit/{test_setup_run.py,test_hardware_provisioning.py,test_hardware_readiness.py}`, `docs/{OperatorsGuide.md,QuickStart-linux.md,QuickStart-windows.md,adr/0008-profile-provision-preflight-readiness.md}`, `README.md`, `CHANGE_LOG.md`.
  - Validation: `awf.setup --provision` reported `hw-ort-cuda,speech,wake-word,dev` on this host; Ruff passed for touched backend source/tests; focused pytest passed with repo temp workaround (`49 passed`, one known cache warning); PowerShell bootstrap parsed OK; `pyproject.toml` parsed and exposed `wake-word = ['openwakeword==0.6.0']`; `git diff --check` passed.
  - Notes: Linux Bash syntax validation could not run in this Windows shell because WSL/Bash returned `E_ACCESSDENIED`; the Linux OpenWakeWord behavior was aligned to `..\JARVISv7\scripts\provision.py`.

- Timestamp: 2026-08-11 23:52
  - Host class(es): Linux/WSL x64 CUDA by operator output; Windows AMD64 syntax/parse validation
  - Summary: Prevented optional voice dependencies from blocking repo bootstrap when `openwakeword` requires unavailable Linux/Python 3.12 `tflite-runtime` wheels.
  - Scope: `pyproject.toml`, `scripts/bootstrap.{sh,ps1}`, `docs/{QuickStart-linux.md,QuickStart-windows.md,OperatorsGuide.md}`, `README.md`, `CHANGE_LOG.md`.
  - Validation: Operator-provided Linux/WSL output showed `openwakeword==0.6.0` failing on `tflite-runtime`; local validation parsed `pyproject.toml` and `scripts/bootstrap.ps1`; `pip install -e . --no-deps --dry-run --no-build-isolation` reached `Would install awf-0.1.0`; `git diff --check` passed.
  - Notes: Core bootstrap now skips optional speech setup by default; operators can attempt voice setup with `--with-speech` or `-WithSpeech`, and `openwakeword` is split into a separate `wake-word` extra.

- Timestamp: 2026-08-11 23:44
  - Host class(es): Windows ARM64 install path by operator output; Windows AMD64 syntax/parse validation
  - Summary: Fixed repo bootstrap after Windows ARM64 dependency resolution exposed that core install was coupled to optional speech packages and PowerShell continued after native command failures.
  - Scope: `pyproject.toml`, `scripts/bootstrap.ps1`, `scripts/bootstrap.sh`, `docs/{OperatorsGuide.md,QuickStart-windows.md,QuickStart-linux.md}`, `README.md`, `CHANGE_LOG.md`.
  - Validation: Operator-provided `pip` output showed `faster-whisper` could not resolve `ctranslate2` on Windows ARM64; local validation parsed `pyproject.toml` and `scripts/bootstrap.ps1`; `pip install -e . --no-deps --dry-run --no-build-isolation` reached `Would install awf-0.1.0`; `git diff --check` passed.
  - Notes: Core AWF now installs without speech dependencies; speech remains optional via `.[speech]`, with `faster-whisper` excluded on Windows ARM64 and the bootstrap wrapper reporting the voice readiness gap instead of blocking core setup.

- Timestamp: 2026-08-11 23:36
  - Host class(es): Windows AMD64
  - Summary: Added installability support for repo-local operators with `awf doctor`, `awf/system.doctor`, Windows/Linux bootstrap wrappers, and setup creation of `cache/temp`.
  - Scope: `backend/src/awf/{cli/core_ops.py,cli/main.py,server/stdio.py,setup.py}`, `scripts/bootstrap.ps1`, `scripts/bootstrap.sh`, `frontend/shared/src/{client.ts,types.ts}`, `frontend/shared/tests/client.test.ts`, setup sections in README and quickstart/operator docs.
  - Validation: Ruff passed for touched backend source/tests; focused backend pytest passed outside the sandbox after the known Windows temp permission failure (`43 passed`); shared protocol focused test passed (`12 passed`); `awf doctor --json` returned the expected actionable report for this host.
  - Notes: This is a repo-local bootstrap path, not packaged Windows/Linux desktop installers.

- Timestamp: 2026-08-11 23:35
  - Host class(es): Windows AMD64
  - Summary: Made Run results outcome-oriented by persisting completed Run output, returning a compact Run Outcome summary, and rendering result/evidence/next-action text in CLI, AWF-CLI, and AWF-GUI.
  - Scope: `backend/src/awf/cli/{core_ops.py,main.py}`, `backend/tests/integration/{test_core_ops_status_approval_artifacts.py,test_phase10_cli_main.py,test_phase10_server_stdio.py}`, `frontend/cli/src/commands.ts`, `frontend/cli/tests/commands.test.ts`, `frontend/gui/src/renderer/{Dashboard.tsx,Overview.tsx,RunsView.tsx}`, `frontend/gui/tests/Dashboard.test.tsx`.
  - Validation: Focused backend pytest passed outside the sandbox (`43 passed`); focused frontend tests passed (`shared 12`, `cli 36`, `gui 13`); full frontend workspace tests passed (`shared 12`, `cli 43`, `gui 62`); `awf run assistant-default@1.0.0 --objective "operator smoke check"` passed outside the sandbox and `awf status <run-id> --json` returned persisted `outcome`.
  - Notes: CLI raw payloads remain available with `--json`; default output now favors operator-readable summaries.

- Timestamp: 2026-08-11 23:34
  - Host class(es): Windows AMD64
  - Summary: Added the repo-local operator readiness path with `awf doctor`, Windows/Linux bootstrap wrappers, durable Run Outcome summaries, human-readable CLI output with `--json` fallback, and GUI outcome/doctor display.
  - Scope: `backend/src/awf/{cli/core_ops.py,cli/main.py,server/stdio.py,setup.py}`, `scripts/bootstrap.{ps1,sh}`, `frontend/{shared,cli,gui}`, `docs/{OperatorsGuide.md,QuickStart-windows.md,QuickStart-linux.md}`, `README.md`, focused backend/frontend tests.
  - Validation: Ruff passed for touched backend source/tests; focused backend pytest passed outside the sandbox after the known Windows temp permission failure (`43 passed`); focused frontend tests passed (`shared 12`, `cli 36`, `gui 13`); `npm --prefix frontend run build --workspaces` passed; full frontend workspace tests passed (`shared 12`, `cli 43`, `gui 62`); `awf doctor --json` reported actionable setup state; `awf run assistant-default@1.0.0 --objective "operator smoke check"` passed outside the sandbox and returned operator-visible outcome text.
  - Notes: `awf doctor` correctly reported missing `.env` and speech artifacts on this host; LiteLLM emitted its existing network-blocked remote cost-map warning and used the local fallback.

- Timestamp: 2026-08-10 23:06
  - Host class(es): Windows AMD64
  - Summary: Reviewed the assistant usability sweep for contract drift and aligned the active AWF spec plus ADR-0025 with activity-output response rendering and the widened GUI/CLI/backend assistant path.
  - Scope: `docs/AGENTIC_WORKFLOW_FABRIC_SPEC.md`, `docs/adr/0025-control-center-look-usability.md`, `backend/tests/unit/test_baseline_io_schema.py`, `CHANGE_LOG.md`.
  - Validation: `backend\.venv\Scripts\python.exe -m ruff check backend\tests\unit\test_baseline_io_schema.py` passed; `backend\.venv\Scripts\python.exe -m pytest backend\tests\unit\test_baseline_io_schema.py backend\tests\unit\test_phase7_workflow_definition.py -q -o cache_dir=cache/temp/pytest-cache` -> 17 passed outside the sandbox after the known Windows temp permission issue; registry validation still passed for `assistant-default@1.0.0` and `assistant_reply@1.0.0`; `git diff --check` passed; `git check-attr` showed `text: auto` and `eol: lf` for touched docs/test files.

- Timestamp: 2026-08-10 23:03
  - Host class(es): Windows AMD64
  - Summary: Made the default assistant path first-run usable by adding a local `assistant-default@1.0.0` workflow, a deterministic `assistant_reply` activity, activity-output response rendering, and `awf run --objective` for quick core CLI use.
  - Scope: `backend/src/awf/{cli/main.py,cli/core_ops.py,workflow/activities.py,workflow/engine.py,workflow/io_schema.py}`, `config/app_registry/{capabilities/assistant_reply/1.0.0.yaml,workflows/assistant-default/1.0.0.yaml}`, `backend/tests/{integration/test_baseline_activity_node.py,integration/test_core_ops_run_start.py,integration/test_phase10_cli_main.py,unit/test_phase7_workflow_definition.py}`, `frontend/cli/src/commands.ts`, `frontend/gui/src/renderer/App.tsx`, `frontend/gui/tests/{App.nav.test.tsx,App.voiceRoundTrip.test.tsx}`, `docs/{OperatorsGuide.md,adr/0025-control-center-look-usability.md}`.
  - Validation: `backend\.venv\Scripts\python.exe -m ruff check ...` passed for touched backend source/tests; focused backend pytest sets passed outside the sandbox after the known Windows temp permission failure (`18 passed`, `25 passed`); `npm --prefix frontend run build --workspaces` passed; `npm --prefix frontend test --workspaces` -> shared 12 passed, CLI 43 passed, GUI 62 passed; registry validation passed for `assistant-default@1.0.0` and `assistant_reply@1.0.0`; `git diff --check` passed.

- Timestamp: 2026-08-10 22:57
  - Host class(es): Windows AMD64
  - Summary: Added repo-level LF normalization, made CLI plain-assistant requests honor `settings.defaultWorkflow`, and preselected submitted GUI Run details for faster operator inspection.
  - Scope: `.gitattributes`, `frontend/cli/src/App.tsx`, `frontend/cli/tests/commands.test.ts`, `frontend/gui/src/renderer/{App,VoiceActivation}.tsx`, `frontend/gui/tests/{App.nav.test.tsx,App.voiceRoundTrip.test.tsx}`, `docs/adr/0025-control-center-look-usability.md`.
  - Validation: `git check-attr text eol -- frontend\cli\src\App.tsx frontend\gui\src\renderer\App.tsx backend\src\awf\cli\core_ops.py CHANGE_LOG.md .gitattributes` showed `text: auto` and `eol: lf`; `npm --prefix frontend --workspace awf-cli test -- commands.test.ts App.test.tsx` -> 37 passed; `npm --prefix frontend --workspace awf-gui test -- App.nav.test.tsx App.voiceRoundTrip.test.tsx` -> 14 passed; `npm --prefix frontend run build --workspaces` passed; `npm --prefix frontend test --workspaces` -> shared 12 passed, CLI 43 passed, GUI 62 passed.

- Timestamp: 2026-08-10 22:52
  - Host class(es): Windows AMD64
  - Summary: Made regular assistant use work end-to-end by letting CLI plain text start the default workflow and by adapting voice/assistant metadata for strict single-string workflow schemas.
  - Scope: `backend/src/awf/cli/core_ops.py`, `backend/tests/integration/test_core_ops_run_start.py`, `frontend/cli/src/{App,commands}.ts(x)`, `frontend/cli/tests/{App.test.tsx,commands.test.ts}`, `docs/adr/0025-control-center-look-usability.md`.
  - Validation: `backend\.venv\Scripts\python.exe -m ruff check backend\src\awf\cli\core_ops.py backend\tests\integration\test_core_ops_run_start.py` passed; `backend\.venv\Scripts\python.exe -m pytest backend\tests\integration\test_core_ops_run_start.py -q -o cache_dir=cache/temp/pytest-cache` -> 9 passed outside the sandbox after the known Windows temp permission failure; `npm --prefix frontend --workspace awf-cli test -- commands.test.ts App.test.tsx` -> 36 passed; `npm --prefix frontend run build --workspace awf-cli` passed.

- Timestamp: 2026-08-10 22:45
  - Host class(es): Windows AMD64
  - Summary: Made chat and voice workflow selection practical by sharing the default workflow, offering registry-backed workflow suggestions, and adapting chat `objective` input to single-string workflow schemas such as `topic`.
  - Scope: `backend/src/awf/cli/core_ops.py`, `backend/tests/integration/test_core_ops_run_start.py`, `frontend/gui/src/renderer/{App,Transcript,VoiceActivation}.tsx`, `frontend/gui/tests/{App.nav.test.tsx,App.voiceRoundTrip.test.tsx,setup.ts}`, `docs/adr/0025-control-center-look-usability.md`.
  - Validation: `backend\.venv\Scripts\python.exe -m ruff check backend\src\awf\cli\core_ops.py backend\tests\integration\test_core_ops_run_start.py` passed; `backend\.venv\Scripts\python.exe -m pytest backend\tests\integration\test_core_ops_run_start.py -q -o cache_dir=cache/temp/pytest-cache` -> 8 passed; `npm --prefix frontend --workspace awf-gui test -- App.nav.test.tsx App.voiceRoundTrip.test.tsx Transcript.test.tsx` -> 19 passed; `npm --prefix frontend run build --workspace awf-gui` passed; `npm --prefix frontend test --workspaces` -> shared 12 passed, CLI 41 passed, GUI 62 passed.

- Timestamp: 2026-08-10 22:41
  - Host class(es): Windows AMD64
  - Summary: Added a core `outputs.response_text` fallback for Run results so GUI/voice surfaces receive useful transcript text even when a workflow does not declare a response output.
  - Scope: `backend/src/awf/cli/core_ops.py`, `backend/tests/integration/test_core_ops_run_start.py`, `docs/adr/0025-control-center-look-usability.md`.
  - Validation: `backend\.venv\Scripts\python.exe -m ruff check backend\src\awf\cli\core_ops.py backend\tests\integration\test_core_ops_run_start.py` passed; `backend\.venv\Scripts\python.exe -m pytest backend\tests\integration\test_core_ops_run_start.py -q -o cache_dir=cache/temp/pytest-cache` -> 7 passed; `npm --prefix frontend --workspace awf-gui test -- App.nav.test.tsx` -> 10 passed.

- Timestamp: 2026-08-10 22:37
  - Host class(es): Windows AMD64
  - Summary: Gave AWF-GUI typed chat a runnable shipped default workflow (`produce-gate-repair-demo@1.0.0`) while preserving manual workflow override and the cleared-field error path.
  - Scope: `frontend/gui/src/renderer/App.tsx`, `frontend/gui/tests/App.nav.test.tsx`, `docs/adr/0025-control-center-look-usability.md`.
  - Validation: `npm --prefix frontend --workspace awf-gui test -- App.nav.test.tsx Transcript.test.tsx` -> 15 passed; `npm --prefix frontend run build --workspace awf-gui` passed; `npm --prefix frontend test --workspaces` -> shared 12 passed, CLI 41 passed, GUI 61 passed.

- Timestamp: 2026-08-10 22:35
  - Host class(es): Windows AMD64
  - Summary: Swept backend cross-platform execution policy so shipped Python gate commands and governed `command_run` activities resolve through the repo venv/current interpreter, and platform-native absolute allowed roots work on Windows and Linux.
  - Scope: `backend/src/awf/cli/core_ops.py`, `backend/src/awf/machine/{activities,policy}.py`, `backend/tests/{integration/test_core_ops_run_start.py,integration/test_machine_activities.py,unit/test_machine_policy.py}`, `docs/adr/0021-governed-reach-into-the-machine.md`.
  - Validation: `backend\.venv\Scripts\python.exe -m ruff check backend\src\awf\cli\core_ops.py backend\src\awf\machine\activities.py backend\src\awf\machine\policy.py backend\tests\integration\test_core_ops_run_start.py backend\tests\integration\test_machine_activities.py backend\tests\unit\test_machine_policy.py` passed; `backend\.venv\Scripts\python.exe -m pytest backend\tests\integration\test_core_ops_run_start.py backend\tests\integration\test_machine_activities.py backend\tests\unit\test_machine_policy.py -q -o cache_dir=cache/temp/pytest-cache` -> 18 passed; `git diff --check` passed.

- Timestamp: 2026-08-10 22:29
  - Host class(es): Windows AMD64
  - Summary: Moved AWF-GUI live voice response audio output path selection from the renderer to the Electron main process, using the host temp directory for Windows/Linux compatibility.
  - Scope: `frontend/gui/src/main/voicePipeline.ts`, `frontend/gui/src/preload/preload.ts`, `frontend/gui/src/renderer/{App,index}.tsx`, `frontend/gui/tests/{voicePipeline.test.ts,App.voiceRoundTrip.test.tsx,setup.ts}`.
  - Validation: `npm --prefix frontend --workspace awf-gui test -- voicePipeline.test.ts App.voiceRoundTrip.test.tsx` -> 13 passed; `npm --prefix frontend run build --workspace awf-gui` passed; `npm --prefix frontend test --workspaces` -> shared 12 passed, CLI 41 passed, GUI 61 passed.

- Timestamp: 2026-08-10 22:23
  - Host class(es): Windows AMD64
  - Summary: Updated AWF-GUI typed chat to show workflow response text or failure details in the shared transcript instead of only a generic run status.
  - Scope: `frontend/gui/src/renderer/App.tsx`, `frontend/gui/tests/App.nav.test.tsx`.
  - Validation: `npm --prefix frontend --workspace awf-gui test -- App.nav.test.tsx Transcript.test.tsx` -> 15 passed; `npm --prefix frontend run build --workspace awf-gui` passed; `npm --prefix frontend test --workspaces` -> shared 12 passed, CLI 41 passed, GUI 59 passed.

- Timestamp: 2026-08-10 22:19
  - Host class(es): Windows AMD64
  - Summary: Made gate check execution work across Windows and Linux repo venv layouts with explicit platform markers, and auto-escalated risky gate checks to the high-risk Trifecta tier with an audit event.
  - Scope: `backend/src/awf/cli/core_ops.py`, `backend/src/awf/gates/gate_node.py`, `backend/tests/integration/test_core_ops_run_start.py`.
  - Validation: `backend\.venv\Scripts\python.exe -m ruff check backend\src\awf\cli\core_ops.py backend\src\awf\gates\gate_node.py backend\tests\integration\test_core_ops_run_start.py` passed; `backend\.venv\Scripts\python.exe -m pytest backend\tests\integration\test_core_ops_run_start.py backend\tests\integration\test_phase8_gate_node.py -q -o cache_dir=cache/temp/pytest-cache` -> 12 passed; `git diff --check` passed.

- Timestamp: 2026-08-10 22:06
  - Host class(es): Windows AMD64
  - Summary: Wired AWF-GUI typed chat to start real durable Runs through the shared `awf/run.start` protocol path instead of appending local-only transcript text.
  - Scope: `frontend/gui/src/main/ipc.ts`, `frontend/gui/src/preload/preload.ts`, `frontend/gui/src/renderer/{App,Transcript,index}.tsx`, `frontend/gui/src/renderer/styles.css`, focused GUI tests.
  - Validation: `npm --prefix frontend run build --workspaces` passed; `npm --prefix frontend test --workspaces` -> shared 12 passed, CLI 41 passed, GUI 58 passed; `git diff --check` passed.

- Timestamp: 2026-08-10 21:00
  - Host class(es): Linux/WSL2, AMD64
  - Summary: Implemented ADR-0025 control-center look and usability for AWF-GUI — a token-based stylesheet, a top-bar shell rendering one view at a time with chat as the landing page, shared semantic state classes, an inline icon set, and the renderer split into per-view components. No new dependency and no protocol, IPC, or authorization change.
  - Scope:
    - `frontend/gui/src/renderer/styles.css`, `css.d.ts`, `index.tsx` (CSS import on the esbuild entry point), `index.html` (`./index.css` link)
    - `frontend/gui/src/renderer/App.tsx` (shell, sticky top bar, `Views` nav with `aria-current`/pending badge, status bar, seven-view switch)
    - `frontend/gui/src/renderer/{Overview,RunsView,ApprovalsView,ProposalReview,MemoryPanel,RegistryActions,ApprovalConfirmation,Dashboard}.tsx`
    - `frontend/gui/src/renderer/Transcript.tsx` (chat window: title bar, auto-scrolling bubble stream, composer with mic + Send), `VoiceActivation.tsx` (voice bar)
    - `frontend/gui/src/renderer/state.ts` (`stateClass` over ok/warn/danger/idle), `icons.tsx` (`makeIcon` 24×24 stroke set)
    - `frontend/gui/src/main/main.ts` (window `backgroundColor: #070b12`, `minWidth`/`minHeight`), `src/main/ipc.ts`, `src/preload/preload.ts`
    - `frontend/gui/tests/{App.nav.test.tsx,App.dashboard.test.tsx,Transcript.test.tsx,Dashboard.test.tsx,ipc.test.ts,RegistryActions.test.tsx}`
    - `docs/adr/0025-control-center-look-usability.md`
  - Validation:
    - `npm --prefix frontend run build --workspaces` -> <fill>
    - `npm --prefix frontend test --workspaces` -> shared <n>, CLI <n>, GUI <n>
    - `dist/renderer/index.css` emitted and linked from `dist/renderer/index.html` -> <fill>
    - manual launch: dark navy surface, chat as landing page, Status/Registry views mutually exclusive, accent focus ring on keyboard traversal -> <fill>
  - Notes:
    - `frontend/gui/package.json` gained no `dependencies`/`devDependencies` entry; the CSS ships through the existing esbuild renderer bundle with no loader configuration.
    - The composer's Send appends the operator's text to the local transcript only — typed input does not submit a workflow turn; `VoiceActivation`/`onVoiceSubmitText` remains the only path that reaches the backend.
    - Dark theme only; no `backdrop-filter` on the top bar (WSLg software compositors mis-render blurred surfaces); the readiness inventory still renders as a bounded `.pre-scroll` JSON block.

- Timestamp: 2026-08-10 00:17
  - Host class(es): Linux/WSL2, AMD64
  - Summary: Fixed AWF-GUI backend spawn failure (`spawn awf ENOENT`) by resolving the `awf`/`awf-speech` venv binaries from the compiled main-process file location instead of `process.cwd()`, which npm workspace scripts leave pointed at `frontend/gui` rather than the repo root.
  - Scope: `frontend/gui/src/main/main.ts`.
  - Validation: manual launch via `npm --prefix frontend run dev` with `AWF_CORE_COMMAND`/`AWF_SPEECH_COMMAND`/`AWF_REPO_ROOT` unset confirmed `backend/.venv/bin/awf serve --stdio` spawned and the Control center populated live readiness/registry data; `npm --prefix frontend run build --workspaces` passed; `npm --prefix frontend test --workspaces` -> shared 12 passed, CLI 41 passed, GUI 39 passed.
  - Notes: no new automated test covers command resolution; this is an Electron main-process entrypoint path exercised by manual launch.

- Timestamp: 2026-08-09 22:39
  - Host class(es): Linux/WSL2, AMD64
  - Summary: Added Guard authorization for Model Gateway completion candidates, hardware-profile model defaults for resident-mind selection, and corrected ADR-0017 implementation drift.
  - Scope: Model Gateway, verifier/adversary LLM review callers, `llm_complete` Capability Record, LLM server config/schema/selector, focused backend tests, and ADR-0017.
  - Validation: focused Gateway/selector/Guard/gate tests -> 74 passed; `backend/.venv/bin/python -m ruff check .` passed; `backend/.venv/bin/python -m pytest backend/tests -q` -> 578 passed, 1 skipped, 7 warnings; `npm --prefix frontend run build --workspaces` passed; `npm --prefix frontend test --workspaces` -> shared 12 passed, CLI 41 passed, GUI 39 passed; `git diff --check` passed.
  - Notes: Voice streaming, Skill invocation, container escalation, and event streaming remain future surfaces.

- Timestamp: 2026-08-09 22:14
  - Host class(es): Linux/WSL2, AMD64
  - Summary: Added a GitHub Copilot CLI `preToolUse` hook path that routes Copilot tool calls through the AWF Capability Guard and records tool-level decisions in events.
  - Scope: Copilot adapter hook generation/cleanup, Copilot Guard hook module, Guard event metadata, agent-step trace context, ADR-0003 note, and focused backend tests.
  - Validation: focused Copilot/Guard tests -> 35 passed; `backend/.venv/bin/python -m ruff check .` passed; `backend/.venv/bin/python -m pytest backend/tests -q` -> 574 passed, 1 skipped, 7 warnings; `npm --prefix frontend run build --workspaces` passed; `npm --prefix frontend test --workspaces` -> shared 12 passed, CLI 41 passed, GUI 39 passed.
  - Notes: Skill invocation, container escalation for quarantined executable objects, and event streaming remain future execution/transport surfaces.

- Timestamp: 2026-08-09 21:54
  - Host class(es): Linux/WSL2, AMD64
  - Summary: Corrected ADR-0023 implementation wording to match the shipped push-to-talk/final-text voice path and completed ADR-0024 GUI registry action wiring through the shared protocol.
  - Scope: ADR-0023/ADR-0024, frontend shared registry client methods, AWF-GUI IPC/preload/renderer registry action panel, and focused frontend tests.
  - Validation: frontend shared targeted test -> 12 passed; frontend GUI targeted tests -> 9 passed; `npm --prefix frontend run build --workspaces` passed; `npm --prefix frontend test --workspaces` -> shared 12 passed, CLI 41 passed, GUI 39 passed; `backend/.venv/bin/python -m ruff check .` passed; `backend/.venv/bin/python -m pytest backend/tests -q` -> 570 passed, 1 skipped, 7 warnings; `git diff --check` passed.

- Timestamp: 2026-08-09 21:41
  - Host class(es): Linux/WSL2, AMD64
  - Summary: Implemented ADR-0024 familiar control center with read-only control summary/detail protocol methods, LLM and readiness status exposure, GUI overview/detail panels, and peer CLI status/Skill inspection commands.
  - Scope: backend core ops and stdio JSON-RPC, frontend shared protocol, AWF-GUI IPC/preload/renderer dashboard, AWF-CLI slash commands, focused tests, and ADR-0024.
  - Validation: `backend/.venv/bin/python -m pytest backend/tests -q` -> 570 passed, 1 skipped, 7 warnings; `backend/.venv/bin/python -m ruff check .` passed; `npm --prefix frontend run build --workspaces` passed; `npm --prefix frontend test --workspaces` -> shared 12 passed, CLI 41 passed, GUI 37 passed.
  - Notes: `awf/events.subscribe` remains unsupported over request/response stdio; Skill execution remains out of scope until a guarded core invocation path exists.

- Timestamp: 2026-08-09 21:12
  - Host class(es): Linux/WSL2, AMD64
  - Summary: Implemented ADR-0023 voice conversation sessions with durable voice state events, active-session transcript persistence, default-workflow voice submission, protocol voice methods, GUI push-to-talk controls, and Kokoro response synthesis.
  - Scope: `backend/src/awf/speech/session.py`, speech CLI/core ops, stdio JSON-RPC, frontend shared protocol, AWF-GUI voice IPC/preload/renderer controls, focused voice tests, and ADR-0023.
  - Validation: `backend/.venv/bin/python -m pytest backend/tests -q` outside the Codex sandbox -> 566 passed, 7 warnings; `backend/.venv/bin/python -m ruff check .` passed; `npm --prefix frontend run build --workspaces` passed; `npm --prefix frontend test --workspaces` -> shared 11 passed, CLI 38 passed, GUI 34 passed; `backend/.venv/bin/python -m awf.speech.cli models verify` passed with configured TTS/VAD/wake artifacts OK.
  - Notes: live microphone/speaker proof remains host-sensitive outside-sandbox validation; file-based round-trip remains available as the deterministic debug path.

- Timestamp: 2026-08-09 20:43
  - Host class(es): Linux/WSL2, AMD64
  - Summary: Implemented ADR-0022 system improvement with consent through durable Improvement Proposals, exact diff digests, R2 merge approvals, retained candidate worktrees, and JSON-RPC/CLI/GUI proposal surfaces.
  - Scope: `backend/src/awf/improvement/*`, SQLite schema/bootstrap, core ops, stdio JSON-RPC, Python CLI, frontend shared/CLI/GUI improvement surfaces, `config/app_registry/workflows/self-improvement/1.0.0.yaml`, focused tests, and ADR-0022.
  - Validation: `backend/.venv/bin/python -m pytest backend/tests -q` outside the Codex sandbox -> 559 passed, 7 warnings; `backend/.venv/bin/python -m ruff check .` passed; `npm --prefix frontend run build --workspaces` passed; `npm --prefix frontend test --workspaces` -> shared 10 passed, CLI 38 passed, GUI 32 passed.
  - Notes: local self-improvement closeout only; no external PR/forge integration or auto-merge is claimed.

- Timestamp: 2026-08-09 11:18
  - Host class(es): Linux/WSL2, AMD64
  - Summary: Implemented ADR-0021 governed machine reach with constrained filesystem, bounded writes, command, network, and MCP exposure paths bound to Capability Records, guard events, exact action digests, and approval previews.
  - Scope: `backend/src/awf/machine/*`, Capability Record constraints, workflow activity routing, MCP tool exposure checks, JSON-RPC/CLI/GUI approval preview surfaces, default filesystem/command machine capability records, focused tests, and ADR-0021.
  - Validation: `backend/.venv/bin/python -m pytest backend/tests -q` outside the Codex sandbox -> 550 passed, 7 warnings; `backend/.venv/bin/python -m ruff check .` passed; `npm --prefix frontend run build --workspaces` passed; `npm --prefix frontend test --workspaces` -> shared 9 passed, CLI 37 passed, GUI 32 passed.
  - Notes: network activity execution is covered with a deterministic fake opener; no live external network or host-destructive command support is claimed.

- Timestamp: 2026-08-09 09:36
  - Host class(es): Linux/WSL2, AMD64
  - Summary: Implemented ADR-0020 memory beyond workflows with registry-backed memory profiles, semantic memories, active sessions, episodic search, memory proposal actions, JSON-RPC/CLI methods, and frontend memory controls.
  - Scope: `backend/src/awf/memory/*`, memory registry schemas/loaders/kinds, SQLite bootstrap/schema, CLI/core ops/stdio methods, frontend shared/CLI/GUI memory surfaces, focused tests, and ADR-0020.
  - Validation: memory-focused backend tests -> 42 passed; frontend shared tests -> 9 passed; frontend CLI tests -> 36 passed; frontend GUI tests -> 32 passed; `npm --prefix frontend run build` passed; `backend/.venv/bin/python -m ruff check backend/src/awf backend/tests` passed; `git diff --check` passed.
  - Notes: deterministic lexical retrieval only; no embedding/vector-store path or live LLM validation. Frontend commands passed in the current shell with Node v22.19.0; the repo policy remains Node >=26.

- Timestamp: 2026-08-09 09:04
  - Host class(es): Linux/WSL2, AMD64
  - Summary: Implemented ADR-0019 workflow authorship as a digest-bound proposal pipeline backed by structured resident-mind output, durable proposal storage, CLI/JSON-RPC methods, and frontend proposal review controls.
  - Scope: `backend/src/awf/authoring/*`, proposal schema/bootstrap, Model Gateway structured output, CLI/core ops/stdio proposal methods, frontend shared/CLI/GUI proposal surfaces, focused tests, and ADR-0019.
  - Validation: `backend/.venv/bin/python -m pytest backend/tests/integration/test_workflow_authoring_proposals.py backend/tests/integration/test_phase3_model_gateway.py backend/tests/integration/test_phase10_server_stdio.py backend/tests/integration/test_phase10_cli_main.py backend/tests/integration/test_phase0_bootstrap.py` -> 53 passed; frontend shared tests -> 8 passed; frontend CLI tests -> 35 passed; frontend GUI tests -> 31 passed; `npm --prefix frontend run build` passed; `backend/.venv/bin/python -m ruff check backend/src backend/tests` passed; `git diff --check` passed.
  - Notes: live resident-mind runtime commands remain outside-sandbox evidence; deterministic acceptance uses mocked structured model output. Frontend commands passed in the current shell with Node v22.19.0; the repo policy remains Node >=26.

- Timestamp: 2026-08-09 08:32
  - Host class(es): Linux/WSL2, AMD64, NVIDIA CUDA
  - Summary: Fixed managed resident-mind sidecar lifecycle and fallback behavior so `awf llm serve start` leaves a stoppable process, CPU fallback is selected when an accelerator artifact is unavailable, and local OpenAI-compatible llama.cpp calls do not require an operator secret.
  - Scope: `backend/src/awf/llm/sidecar.py`, `backend/src/awf/cli/core_ops.py`, `backend/src/awf/workflow/activities.py`, `backend/src/awf/hardware/readiness.py`, `backend/src/awf/gateway/client.py`, focused LLM tests, and ADR-0017.
  - Validation: focused LLM sidecar/CLI/readiness/gateway tests passed; live host proof started AWF-managed CUDA `llama-server` on `127.0.0.1:8080`, verified `resident-mind@1.0.0` completion through the Model Gateway without manually setting `OPENAI_API_KEY`, and stopped the persisted sidecar by CLI.

- Timestamp: 2026-08-09 07:08
  - Host class(es): Linux/WSL2, AMD64
  - Summary: Reduced test sprawl by replacing the phase10 core-op catch-all with focused integration files, centralizing temporary repo helpers, and trimming duplicate GUI dashboard assertions.
  - Scope: backend test support helpers, focused core-op integration tests, removed `test_phase10_core_ops.py`, and GUI dashboard tests.
  - Validation: backend collection reduced from 530 to 507 tests; backend unit/integration tests passed; GUI tests passed; Ruff and whitespace checks passed.

- Timestamp: 2026-08-09 06:54
  - Host class(es): Linux/WSL2, AMD64
  - Summary: Normalized active documentation and source comments to remove editing-session and conversational framing while preserving technical facts and validation evidence.
  - Scope: active changelog entries, ADR text, and source comments/docstrings; archived docs preserved.
  - Validation: targeted prohibited-phrase scan over active files; `git diff --check`; `backend/.venv/bin/ruff check backend/src backend/tests scripts`.

- Timestamp: 2026-08-09 06:02
  - Host class(es): Linux/WSL2, AMD64; Windows ARM64
  - Summary: Added helper documentation and scripts for operator-built accelerator artifacts that back ADR-0017's manual llama.cpp runtime entries and the ARM64 Whisper/QNN artifact handoff.
  - Scope: `docs/helpers/*`, `.gitignore`, and ADR-0017.
  - Validation: `bash -n docs/helpers/jarvis-wsl-llamacpp.sh`; PowerShell parser validation for all copied `.ps1` helpers; path scan confirms helper staging paths align with `linux-x64-cuda`, `windows-arm64-gpu`, and `windows-arm64-qnn`; `docs/temp/` and `runtimes/` generated artifacts are ignored.
  - Notes: helpers were adapted from working JARVISv7 helper sources while preserving build behavior; repo-specific staging names now use JARVIS-AWF's canonical profile IDs.

- Timestamp: 2026-08-09 05:41
  - Host class(es): Linux/WSL2, AMD64
  - Summary: Expanded ADR-0017 llama.cpp runtime declarations to cover every canonical host profile, including Linux/Windows CPU, generic GPU, CUDA, ARM Adreno GPU, and QNN/Hexagon manual artifacts.
  - Scope: `config/llm/servers.yaml`, `backend/src/awf/llm/{servers.py,discovery.py}`, `backend/src/awf/hardware/{preflight.py,readiness.py}`, focused LLM tests, and ADR-0017.
  - Validation: focused LLM config/discovery/readiness/sidecar/CLI tests -> 22 passed; direct config check confirms `linux-x64-cuda` resolves to `runtimes/llama.cpp/linux-x64-cuda/llama-server` and the repaired binary is present.
  - Notes: official CPU/Vulkan artifacts and Windows x64 CUDA 12.4 remain acquire-able archives; Linux CUDA, QNN/Hexagon, and Windows ARM64 Adreno entries stay manual because those builds are operator-provided or backend-specific rather than universally acquire-able by the existing single-archive acquisition path.

- Timestamp: 2026-08-09 04:58
  - Host class(es): Linux/WSL2, AMD64
  - Summary: Added Ruff as the repo-standard Python formatter/linter, cleaned current backend compliance, and wired linting into setup/provision and validation.
  - Scope: `pyproject.toml`, `scripts/validate_backend.py`, `backend/src/awf/setup.py`, `backend/tests/unit/test_setup_run.py`, `backend/tests/unit/test_validate_backend_script.py`, both QuickStarts, and Ruff-normalized Python under `backend/src`, `backend/tests`, and `scripts`.
  - Validation: `awf-setup --verify` -> reports `ruff_version: 0.16.2` and `pip_check: OK`; `scripts/validate_backend.py lint` -> PASS; focused setup/validator tests -> 13 passed; `scripts/validate_backend.py runtime` -> 17 passed, 1 skipped; `scripts/validate_backend.py ci` -> 509 passed, 18 deselected; `git diff --check` -> PASS.
  - Notes: `awf-setup --install` installs `.[<hardware-extra>,dev]`, so Ruff is acquired through the setup/provision path rather than being a manual venv-only add.

- Timestamp: 2026-08-09 04:57
  - Host class(es): Linux/WSL2, AMD64
  - Summary: Implemented ADR-0018 (personas and the prompt envelope).
  - Scope: see `docs/adr/0018-personas-and-prompt-envelope.md` for full detail.
  - Validation: ADR-0018 status now records the acceptance run; backend CI evidence includes focused persona and prompt-envelope coverage.
  - Notes: corrective documentation entry added after implementation was completed.

- Timestamp: 2026-08-09 04:56
  - Host class(es): Linux/WSL2, AMD64
  - Summary: Implemented ADR-0017 (resident-mind local LLM server selection, acquisition, and lifecycle).
  - Scope: see `docs/adr/0017-resident-mind-llm.md` for full detail.
  - Validation: ADR-0017 status now records the acceptance run; backend CI evidence includes LLM discovery, readiness, sidecar, selector, CLI, and runtime coverage.
  - Notes: corrective documentation entry added after implementation was completed.

- Timestamp: 2026-08-08 09:35
  - Host class(es): Linux/WSL2, AMD64, NVIDIA CUDA
  - Summary: Fixed validation report host classification to use the same inventory and dependency-extra decision as `awf-setup --provision`; see ADR-0015.
  - Scope: `scripts/validate_backend.py`, its unit coverage, and ADR-0015.
  - Validation: mocked CUDA inventory confirms `profile` reports `linux-x64-cuda` even when separately captured runtime-readiness evidence resolves differently.

- Timestamp: 2026-08-08 08:24
  - Host class(es): Linux/WSL2, AMD64
  - Summary: `awf-speech models sync` now removes model artifacts that the current voice manifests no longer select; see ADR-0016.
  - Scope: voice model acquisition/reconciliation, ADR-0007, Section 16.4, and focused model tests.
  - Validation: focused reconciliation tests cover stale artifact/cache removal and failed-acquisition preservation.

- Timestamp: 2026-08-08 08:15
  - Host class(es): Linux/WSL2, AMD64
  - Summary: Capped retained text reports at 35 per report folder; see ADR-0015.

- Timestamp: 2026-08-08 08:15
  - Host class(es): Linux/WSL2, AMD64
  - Summary: Extended the backend validation harness so every test category streams readable per-test progress and writes a durable category report with host class and outcome counts.
  - Scope: `scripts/validate_backend.py`, `backend/tests/unit/test_validate_backend_script.py`, `docs/adr/0015-validation-category-reports.md`, and both QuickStarts.
  - Validation: `profile` wrote its diagnostic report; `unit` -> 213 passed, 1 skipped; `integration` -> 248 passed; `runtime` -> 17 passed, 1 skipped, 456 deselected; `regression` -> 213 passed, 1 skipped; `ci` -> 456 passed, 18 deselected. Each test command wrote a `reports/validation/` report with `host_class_id`, verbose per-test output, and a final summary.
  - Notes: ADR-0015 defines the evidence format and supersedes ADR-0006 only for the former regression-only report format; test selection and exit-code semantics are unchanged.

- Timestamp: 2026-08-08 07:15
  - Host class(es): Linux/WSL2, AMD64
  - Summary: Recorded the frontend's explicit npm 11 install-script approval for esbuild, so a normal workspace install can provision its platform-specific build binary without trusting unrelated package hooks.
  - Scope: `frontend/package.json` (`allowScripts` for `esbuild@0.28.1`) and `docs/adr/0014-node-26-current-frontend-policy.md`.
  - Validation: `npm --prefix frontend install-scripts ls` -> `No packages with unreviewed install scripts.`
  - Notes: ADR-0014 contains the policy, exact version pin, npm precedence behavior, and refresh/review procedure.

- Timestamp: 2026-08-08 07:00
  - Host class(es): Linux/WSL2, AMD64
  - Summary: Implemented ADR-0014 (Node.js 26+ current frontend policy).
  - Scope: see `docs/adr/0014-node-26-current-frontend-policy.md` for full detail.
  - Validation: ADR-0014 records the implemented policy and acceptance evidence; later changelog entries record follow-up frontend install-script approval.
  - Notes: corrective documentation entry added after the implementation entry was found missing.

- Timestamp: 2026-08-08 05:40
  - Host class(es): Linux/WSL2, AMD64
  - Summary: Renamed the shared throwaway-home scratch directory from `agy_home` to `scratch_home` - it was Antigravity-specific but is now shared by Cline and any future home-scoped adapter; the `<actor>` subdirectory keeps each separated.
  - Scope: `backend/src/awf/engine/agent_step.py` (`_apply_mcp` path), `backend/src/awf/mcp/render.py` (docstring), `backend/tests/integration/test_baseline_agent_step_mcp.py` (Antigravity + Cline scratch-home tests), `docs/adr/0003-...`, and `docs/adr/0013-...`.
  - Validation: no `agy_home` string remains; `pytest backend/tests` -> 472 passed, 0 skipped.
  - Notes: cosmetic naming only - nothing keys on the string (per-run scratch path, cleanup removes the whole sandbox dir), so the rename breaks nothing.

- Timestamp: 2026-08-08 05:21
  - Host class(es): Linux/WSL2, AMD64, NVIDIA GeForce RTX 3060
  - Summary: Implemented ADR-0013 - added the fifth and final named CLI adapter, Cline (`adapter: cline`), mirroring the other four in shape, pattern, and functionality, and resolved the historical blocker that had left Cline unbuilt (the current CLI's `--json` + `--auto-approve true` is a non-yolo headless mode).
  - Scope: `backend/src/awf/adapters/cline_cli.py` (new - `ClineAdapterError`, `DEFAULT_TIMEOUT_SECONDS = 300`, `FORBIDDEN_CONSTRAINT_KEYS = ("yolo", "dangerously_skip_permissions")`, `invoke` building `cline <objective> --json --auto-approve true --cwd <ws> [-m <model>]`, with NDJSON `run_result`/`error`, `agent_event`, `hook_event` stream parsing and exit-code + finishReason + error-event failure mapping); `backend/src/awf/cli/core_ops.py` (two lines: import + `"cline": cline_invoke` in `ADAPTER_REGISTRY`); `backend/src/awf/mcp/render.py` (`render_cline` writing `.cline/cline_mcp_settings.json` via `home_relative_files`, reusing `_apply_mcp`'s throwaway-`$HOME` isolation, + `"cline": render_cline` in `RENDERERS`); `config/app_registry/capabilities/cline_invoke/1.0.0.yaml` (new, `provider: cline`, R1 / `approval: never`). Tests: new `backend/tests/unit/test_phase6_cline_adapter.py` (11 tests); extended `backend/tests/integration/test_baseline_agent_step_mcp.py` (Cline scratch-home `.cline/cline_mcp_settings.json` test) and `backend/tests/integration/test_phase1_registry_guard.py` (`("cline_invoke", "cline", "R1")` row). Docs: `docs/adr/0013-cline-cli-adapter.md` status Proposed -> Accepted with research-based corrections (MCP file is `cline_mcp_settings.json`, not `mcp.json`; npm package is `cline`, platform binary `@cline/cli-<os-arch>`; JSON contract pinned to observed `run_result`/`error` NDJSON; historical yolo-blocker-resolved context added).
  - Validation: `pytest backend/tests` -> 472 passed, 0 skipped (up from 460 baseline; +12 net); `scripts/validate_backend.py ci` -> 454 passed, 18 deselected, exit 0; `ADAPTER_REGISTRY`/`RENDERERS` each confirmed 5 entries with matching keys; `awf registry validate config/app_registry/capabilities/cline_invoke/1.0.0.yaml` -> `{"kind": "CapabilityRecord", "ref": "cline_invoke@1.0.0", "valid": true}`; live-verified installed `cline` 3.0.51: a `--json` headless run under a throwaway `$HOME` created `~/.cline`/`~/.cline/data` only inside scratch (real `~/.cline` untouched) and emitted the `run_result`/`error`/`agent_event`/`hook_event` NDJSON schema the unit tests pin.
  - Notes: a fully authenticated live Cline run is gated on a provider key and is out of scope here (a live test must SKIP without `cline` on `PATH`/key). Because the current CLI reports internal failures in-stream and returns exit code 0 even then, this adapter's success check also treats a top-level `error` event and a non-success `run_result.finishReason` as failures - it does not rely on the exit code alone. No new agent manifest (YAGNI); Cline opts in later via `adapter: cline` + `capabilities: [cline_invoke@1.0.0]`.

- Timestamp: 2026-08-08 03:08
  - Host class(es): Linux/WSL2, AMD64, NVIDIA GeForce RTX 3060
  - Summary: Implemented ADR-0012's Task A and Task D - the registry index now verifies content digests and enforces `blocked` trust status at resolution time, shadowing keys on a real object instead of any file, all seven registry kinds publish through one path, and `awf registry reindex`/`retire`/`trust` give an operator lifecycle control over what the index already tracked but never used.
  - Scope: `backend/src/awf/registry/index.py` (new: `compute_digest`, `index_row`, `set_trust_status`, `reindex`, `latest_version`); `backend/src/awf/registry/resolve.py` (optional `conn` param, digest verification, `blocked` refusal, `RegistryIntegrityError`/`RegistryBlockedError`, shadowing test changed from `any(data_dir.iterdir())` to `any(version_names(data_dir, kind))`); `backend/src/awf/registry/voice_profile.py` and `model_profile.py` (required `name`/`version` fields, `ref` property, path-agreement check on load matching `load_skill`'s existing pattern); nine shipped config YAMLs under `config/app_registry/{voice-profiles,model-profiles}/*/1.0.0.yaml` gained `name`/`version`; `backend/src/awf/cli/core_ops.py` (`op_registry_publish`/`op_registry_validate` gained `voice-profiles`/`model-profiles` branches; `op_registry_get` now requires `conn` and returns `digest`/`trust_status`/`object`; `op_registry_list` optionally joins index data; new `op_registry_reindex`/`op_registry_retire`/`op_registry_trust`; `_resolve_workflow` resolves a bare name through `latest_version` before falling through to normal resolution); `backend/src/awf/cli/main.py` (`registry reindex`/`retire`/`trust` subcommands); `backend/src/awf/server/stdio.py` (matching `awf/registry.reindex`/`.retire`/`.trust` JSON-RPC methods). Test scope: new `backend/tests/unit/test_registry_index.py` (12 tests); extended `backend/tests/integration/test_phase10_core_ops.py` (voice/model profile publish round-trips, get/retire/trust, bare-name run-start pinning, resume-uses-the-pin-not-a-newer-publish) and `test_phase10_cli_main.py` (reindex/retire/trust CLI dispatch); seven pre-existing test files with inline Voice/Model Profile fixtures updated to carry `name`/`version`.
  - Validation: `pytest backend/tests` -> 460 passed (up from 436 baseline, same 0 skips); all six `scripts/validate_backend.py` commands returned exit 0; manually verified end to end in a scratch repo - `awf registry reindex` indexes a capability record, mutating its file then resolving with a connection raises `RegistryIntegrityError` naming both digests, `awf registry retire` then resolving raises `RegistryBlockedError`, `awf registry trust ... --status local` restores the row but resolution still raises `RegistryIntegrityError` until a fresh `reindex` accepts the mutated content; publishing a Voice Profile through `awf registry publish --kind voice-profiles` round-trips; `awf run demo` (no `@version`) resolves the newest version and records `demo@1.0.0` in `runs.workflow_ref`.
  - Notes: ADR-0012 used `awf run start --workflow <name>` while the actual CLI is `awf run <workflow>` (a bare positional, no `run start` subcommand, no `--workflow` flag). The existing positional now accepts a bare name in addition to `name@version`, reaching the same latest-version resolution without a CLI restructure. `WorkflowMetadata.digest` stays unchecked, per this ADR's "Open decisions" section. Operator-authored files under `data/registry/model-profiles/*` remain operator-owned; the ADR accepts that an existing operator file fails to load until the operator adds `name`/`version`.

- Timestamp: 2026-08-08 02:45
  - Host class(es): Linux/WSL2, AMD64, NVIDIA GeForce RTX 3060
  - Summary: Follow-up to ADR-0011's loader consolidation - converted the two remaining hand-rolled enum checks in `mcp_server.py` and `voice_profile.py` onto the shared `registry/schema.require_enum`, closing the last exceptions to "one loader shape."
  - Scope: `backend/src/awf/registry/mcp_server.py` (`type` check now goes through `_require_enum`); `backend/src/awf/registry/voice_profile.py` (`tts.fallback.mode` check now goes through `_require_enum` at `Fallback` construction instead of a separate post-construction check); `docs/adr/0011-registry-kind-vocabulary-and-layout.md` (Status section records this pass).
  - Validation: `pytest backend/tests` -> 436 passed; `pytest backend/tests/unit/test_baseline_mcp_server.py backend/tests/unit/test_phase12_voice_profile.py -v` -> 17 passed; manually confirmed the resulting message text - `voice_profile.py` kept its prior wording (`tts.fallback.mode: 'bogus' not in ('none', 'ordered')`), `mcp_server.py` gained one colon (`type: 'bogus' not in ('stdio', 'http')` vs the prior `type 'bogus' not in (...)`).
  - Notes: no test asserts either message's exact text (both only check the exception class via `pytest.raises`); the `mcp_server.py` wording change is a format-consistency fix.

- Timestamp: 2026-08-07 15:48
  - Host class(es): Linux/WSL2, AMD64, NVIDIA GeForce RTX 3060
  - Summary: Implemented ADR-0011's Task B and Task C - centralized registry kind-to-layout knowledge into one new `registry/kinds.py` vocabulary, replaced content-shape dispatch in `op_registry_validate`/`op_registry_publish` with an explicit `kind` argument, consolidated six registry loaders' duplicated `_require`/`_require_enum`/`_split_frontmatter` scaffolding into a new `registry/schema.py`, and closed the two remaining `data/artifacts` path literals.
  - Scope: `backend/src/awf/registry/kinds.py` (new: `RegistryKind`, `by_key`, `object_path`, `version_names`, `UnknownRegistryKindError`); `backend/src/awf/registry/schema.py` (new: shared `require`/`require_enum`/`split_frontmatter`); `backend/src/awf/registry/resolve.py` (repointed at `kinds.py`, `_object_path`/`DATA_ONLY_KINDS` removed); `backend/src/awf/registry/{agent_manifest,skill,mcp_server,voice_profile,model_profile,capability_record}.py` (repointed at `schema.py`; `capability_record.py`'s `RegistryValidationError` renamed to `CapabilityRecordValidationError`, matching its five siblings); `backend/src/awf/cli/core_ops.py` (`op_registry_list` uses `version_names`; `op_registry_validate` takes an optional `kind` with path-position-derived fallback; `op_registry_publish` takes a required `kind`; `_artifacts_root` replaced by `awf.paths.artifacts_dir`); `backend/src/awf/cli/main.py` (`registry publish --kind` required, `registry validate --kind` optional); `backend/src/awf/server/stdio.py` (`awf/registry.publish`/`awf/registry.validate` thread `kind` from `params`; `awf/artifact.read` uses `paths.artifacts_dir` instead of a second inline `data/artifacts` literal the ADR didn't name); `backend/src/awf/paths.py` (new `artifacts_dir`). Test scope: `backend/tests/unit/test_registry_kinds.py` (new); `backend/tests/integration/test_phase10_core_ops.py` (explicit `kind=` added to five publish and one validate call site whose fixtures sit outside any registry root; new kind-mismatch test); `backend/tests/integration/test_phase10_cli_main.py` (`--kind` added to the one registry-validate CLI test); `backend/tests/integration/test_phase1_registry_guard.py` (import/usages updated to `CapabilityRecordValidationError`); `docs/adr/0011-registry-kind-vocabulary-and-layout.md` (Status section records this pass).
  - Validation: `pytest backend/tests` -> 436 passed (up from 423 baseline, same 0 skips); all six `scripts/validate_backend.py` commands returned exit 0; `awf registry validate` on `config/app_registry/mcp/context7/1.0.0.yaml` resolves `kind: McpServer` identically with no `--kind` given (path-derived) and with `--kind mcp` given explicitly; `grep` confirmed no `_object_path`/`DATA_ONLY_KINDS` survive outside `kinds.py`, no `config/app_registry`/`data/registry` string literal survives outside `kinds.py`, and `data/artifacts` is spelled only in `paths.py`.
  - Notes: `core_ops._make_run_map_item`'s `data/awf_db/awf.db` literal, which the ADR's Context section names as one of Task C's two remaining path literals, had already been fixed in the ADR-0008 validation pass; only `_artifacts_root` needed migrating here, plus a second `data/artifacts` literal in `server/stdio.py`'s `awf/artifact.read` handler that the ADR text doesn't name but its acceptance criterion covers. `mcp_server.py`'s and `voice_profile.py`'s inline enum checks stayed outside the shared `require_enum` helper because the shared helper's `"{context}: '{value}' not in {allowed}"` message format does not byte-match their original wording, and the ADR requires existing validation messages to stay stable.

- Timestamp: 2026-08-07 14:29
  - Host class(es): Linux/WSL2, AMD64, NVIDIA GeForce RTX 3060
  - Summary: Validated ADR-0008's "Implemented" status against the current codebase and fixed the four gaps a follow-up pass found - two path-derivation call sites that bypassed `awf/paths.py`, a stale docstring, and a test-coverage gap against the ADR's own stated scope.
  - Scope: `backend/src/awf/adapters/codex_cli.py` (repo root now from `awf.paths.REPO_ROOT` instead of `Path(__file__).resolve().parents[4]`); `backend/src/awf/server/stdio.py` and `backend/src/awf/cli/core_ops.py` (db path now from `awf.paths.db_path()` instead of a hardcoded `"data" / "awf_db" / "awf.db"` join); `backend/src/awf/hardware/profiler.py` (`HardwareInventory` docstring reworded to describe the readiness roll-up instead of the pre-ADR execution-provider-verification design); `backend/tests/unit/test_hardware_readiness.py` (added `arch` parametrization to the directml/qualcomm/no-accelerator readiness cases, matching ADR Scope item 10's literal "both architectures" wording); `docs/adr/0008-profile-provision-preflight-readiness.md` (Status section records this pass).
  - Validation: `pytest backend/tests` -> 423 passed (up from 419, same 0 skips); all six `scripts/validate_backend.py` commands returned exit 0; `grep -rn "parents\[" backend/src/awf/adapters/codex_cli.py` empty; `grep -rn '"data" / "awf_db" / "awf.db"' backend/src/awf` matches only `awf/paths.py`; manually confirmed `awf.paths.db_path()` and `codex_cli.DEFAULT_PROFILE_PATH` resolve to the same values the old inline expressions did.
  - Notes: the core four-stage design (`profiler.py`/`provisioning.py`/`preflight.py`/`readiness.py`) needed no changes - all four modules matched the ADR's described signatures and decision logic exactly. The `codex_cli.py` and `stdio.py`/`core_ops.py` sites predate ADR-0008 and were never named in its own file-scope list; they're real gaps against its "single source of truth" claim in practice, not broken promises of the ADR text itself. The readiness test parametrization is additive only - `readiness.py` never reads `inventory.arch`, so no new logic path was exercised, only literal coverage of the stated scope.

- Timestamp: 2026-08-06 16:20
  - Host class(es): Linux/WSL2, AMD64
  - Summary: Implemented ADR-0010 (setup flag dispatch and repository surface cleanup).
  - Scope: see `docs/adr/0010-setup-flag-repo-surface-cleanup.md` for full detail.
  - Validation: ADR-0010 records the acceptance run: `pytest backend/tests` -> 419 passed, 0 skipped; all six `scripts/validate_backend.py` commands passed; `awf-setup --provision --verify` printed both reports on this host.
  - Notes: corrective documentation entry added after the implementation entry was found missing.

- Timestamp: 2026-08-06 16:10
  - Host class(es): Linux/WSL2, AMD64, NVIDIA GeForce RTX 3060
  - Summary: Implemented ADR-0009's three independent tasks - centralized every repo-relative path segment into `awf/paths.py`, made the default voice resolve from the `narrator` Voice Profile instead of a restated `bf_isabella` literal, and published six Capability Records so `activity` workflow nodes now authorize through the same Capability Guard chokepoint `agent` nodes already use.
  - Scope:
    - Task A: `backend/src/awf/paths.py` (new `env_path`, `config_registry_dir`, `data_registry_dir`, `config_voice_dir`, `sandbox_dir`, `scratch_dir`, `temp_dir`); repointed `registry/resolve.py`, `registry/hardware_voice_manifest.py`, `isolation/scratch.py`, `setup.py`, `engine/agent_step.py`. Also closed two `.env`-assembly sites the ADR's own file list didn't name but its acceptance criterion covers: `cli/core_ops.py` (two call sites) and `secrets/cli.py` (three call sites).
    - Task B: `registry/voice_profile.py` (new `DEFAULT_VOICE_PROFILE_REF`, `resolve_default_voice_id`); `speech/cli.py`'s `--voice-id` now defaults to `None` and resolves from the registry when unset; `frontend/gui/src/main/voicePipeline.ts` omits `--voice-id` entirely when unset instead of hardcoding the fallback.
    - Task C: six new records under `config/app_registry/capabilities/{hardware_probe,gpu_utilization_sample,claude_code_invoke,codex_invoke,antigravity_invoke,copilot_invoke}/1.0.0.yaml`; `workflow/engine.py` gained `_synthesized_capability_for_activity`/`_resolve_activity_capability` and `make_activity_node_executor` now takes an optional `repo_root` and authorizes through the Guard before running the activity function; `cli/core_ops.py` passes `repo_root` at its call site.
    - New/extended tests: `backend/tests/unit/test_paths.py` (new), `backend/tests/unit/test_speech_cli_voice_id.py` (new), `backend/tests/unit/test_phase12_voice_profile.py`, `backend/tests/integration/test_baseline_activity_node.py`, `backend/tests/integration/test_phase1_registry_guard.py`, `frontend/gui/tests/voicePipeline.test.ts`.
  - Validation: `pytest backend/tests` -> 415 passed (up from 394 baseline, same 0 skips); all six `scripts/validate_backend.py` commands (`profile`, `unit`, `integration`, `runtime`, `regression`, `ci`) returned exit 0; `grep` confirmed no repo-relative path segment or `.env` assembly remains outside `awf/paths.py`, and `bf_isabella` appears only in `config/app_registry/voice-profiles/narrator/1.0.0.yaml` and in test files that assert the real shipped value (not a restated default); `frontend/gui` - 29 tests passed, `tsc --strict` clean. Live-verified through the real `awf.speech.cli round-trip` entry point against this host's real models: no `--voice-id` produced 88108 bytes of narrator-voice audio, `--voice-id am_michael` produced a genuinely different 93228-byte file - confirmed byte-different, not a stub.
  - Notes: resolved one inconsistency in the ADR text against the codebase before writing the records - the ADR's example showed `provider: claude_code` (underscore) but the registered adapter/actor key in `core_ops.ADAPTER_REGISTRY` and `mcp/render.RENDERERS` is `"claude-code"` (hyphen). Published `claude_code_invoke/1.0.0.yaml` with `provider: claude-code`, matching the actor string per the ADR's stated rule. `frontend/gui/src/renderer/VoiceActivation.tsx`'s `VOICE_OPTIONS` dropdown enumerates all four registered voices, `bf_isabella` included, and was outside this ADR's file scope.

- Timestamp: 2026-08-06 11:35
  - Host class(es): Linux/WSL2, AMD64, NVIDIA GeForce RTX 3060
  - Summary: Fixed a stale call site in `scripts/validate_backend.py`'s `profile` command that predated ADR-0008's addition of a required `repo_root` parameter to `resolve_hardware_profile_id()`, and confirmed two of ADR-0008's three outstanding acceptance items against this host.
  - Scope: `scripts/validate_backend.py`, `docs/adr/0008-profile-provision-preflight-readiness.md`.
  - Validation: reproduced the `TypeError: resolve_hardware_profile_id() missing 1 required positional argument: 'repo_root'` recorded in `reports/diagnostics/20260806112237-profile.txt`; after passing the script's `REPO_ROOT`, `validate_backend.py profile` resolves `linux-x64-cuda` with inventory/tokens/readiness evidence (`reports/diagnostics/20260806113105-profile.txt`); `pytest backend/tests` → 394 passed; `awf-setup --provision --verify` reports the installed onnxruntime distribution, version, providers, and the documented onnxruntime distribution-name pip-check conflict (expected per `setup.py`'s `_KNOWN_ORT_NAME_CONFLICT`, not a defect).
  - Notes: ADR-0008's voice-round-trip acceptance item remains outstanding.

- Timestamp: 2026-08-05 19:42
  - Host class(es): Linux/WSL2, AMD64, NVIDIA GeForce RTX 3060
  - Summary: Environment finding during ADR-0008 implementation - constructing an ONNX Runtime session with `CUDAExecutionProvider` segfaults the process on this host once `onnxruntime-gpu` is installed, because the venv also carries a CUDA 13.x toolchain (`nvidia-cudnn-cu13`, `cuda-toolkit` 13.0.3) pulled in transitively through `torch`, which arrives via `silero-vad`'s own dependency - a native ABI mismatch a Python `try`/`except` cannot catch. `hardware/preflight.py` no longer constructs any ONNX Runtime session as a result; provider availability (`ep:<provider>`) plus the corresponding hardware fact is what selects a device, and a real backend failure now surfaces at the adapter's own first use instead.
  - Scope: `backend/src/awf/hardware/preflight.py`, `backend/src/awf/hardware/readiness.py`, `docs/adr/0008-profile-provision-preflight-readiness.md`.
  - Validation: reproduced directly (`onnxruntime.InferenceSession(..., providers=["CUDAExecutionProvider"])` segfaults the interpreter on this host); `awf-setup --verify` is where this state is visible going forward - it reports the installed distribution, version, and available providers without ever attempting session construction.
  - Notes: `kokoro-onnx`, `openwakeword`, and `faster-whisper` each hard-pin the base `onnxruntime` distribution name regardless of which accelerator extra is selected, so `awf-setup --install` uninstalls the non-selected distribution and force-reinstalls the selected one after the main install, keeping pip's own bookkeeping accurate rather than leaving both distributions listed.

- Timestamp: 2026-08-05 10:18
  - Host class(es): Linux/WSL2, AMD64
  - Summary: ADR-0006 follow-up - fixed `validate_backend.py`'s `runtime` command reporting PASS when every `live` test skips, wired pytest's own cache into `cache/validate_backend/`, and marked three host-probing tests in `test_phase12_hardware_profiler.py` `live` so `ci` no longer runs them.
  - Scope: `scripts/validate_backend.py`, `backend/tests/integration/test_phase12_hardware_profiler.py`, `docs/adr/0006-hardware-profiler-and-update-tests-harness.md`.
  - Validation: `pytest backend/tests` → 364 passed; `-m "not live"` selects 345, `-m live` selects 19.
  - Notes: none.

- Timestamp: 2026-08-05 09:39
  - Host class(es): Linux/WSL2, AMD64
  - Summary: Implemented ADR-0006 (canonical Hardware Profiler module, single project file, tiered test suite, and validation harness).
  - Scope: see `docs/adr/0006-hardware-profiler-and-update-tests-harness.md` for full detail.
  - Validation: `pytest backend/tests` → 364 passed (up from 341 baseline); `-m "not live"` selects 348, `-m live` selects 16, matching the full count; `pip install -e .[dev]` verified from a clean venv; all six `scripts/validate_backend.py` commands returned a code from the documented exit-code contract.
  - Notes: none.

- Timestamp: 2026-08-04 10:24
  - Host class(es): Linux/WSL2, AMD64
  - Summary: Implemented ADR-0005 (AgentManifest.model_profile wiring) - a manifest's `modelProfile` field now resolves to a real Model Profile, picks its winning enabled candidate, and threads the candidate's model name into the adapter's own real `--model`/`-m` flag; Codex additionally gets `--oss --local-provider ollama` when the winning candidate's provider is `ollama`.
  - Scope: see `docs/adr/0005-agent-manifest-model-profile-wiring.md` for full detail.
  - Validation: `pytest backend/tests/` → 341 passed (up from 331 baseline); live-verified through the real `run_agent_step` → `codex_cli.invoke` path - a real Model Profile drove a real `codex exec` subprocess with `-m gpt-5.5`, which genuinely responded with a probe token.
  - Notes: the `ollama`-provider branch's command construction is verified by mocked-subprocess unit tests only, not a live run - this host's real Ollama server listens on the WSL host-gateway IP, not `localhost`, and Codex's `--local-provider ollama` hardcodes `localhost:11434`. A real, named environment/network constraint, not a defect in the implementation.

- Timestamp: 2026-08-04 09:23
  - Host class(es): Linux/WSL2, AMD64
  - Summary: Implemented ADR-0004 (Skills registry schema) - `skills` is a real registry kind now, Agent Manifests gain a `skills` list with a per-reference `share` opt-in, and the default injection tier folds resolved SKILL.md bodies into the objective while the shared tier materializes a skill directory for Claude Code/Copilot CLI/Antigravity/Codex.
  - Scope: see `docs/adr/0004-skills-registry-schema.md` for full detail.
  - Validation: `pytest backend/tests/` → 331 passed (up from 309 baseline); live-verified the Codex shared-tier path through the real `run_agent_step` → `codex_cli.invoke` code path (not a mock) - a real `codex exec` subprocess, under its default safe sandbox flags, read a shared SKILL.md via a scratch `$CODEX_HOME` and echoed back a probe token.
  - Notes: Scope item 7 (AWF's `/skills` CLI-frontend invocation surface) is explicitly out of scope for this ADR, per the ADR's own text.

- Timestamp: 2026-08-04 06:58
  - Summary: Closed three Phase 12 GUI gaps (dead `runList`/`approvalList` IPC channels, a hardcoded single voice, an unreachable R2-voice-refusal UI) and the underlying `approvals.risk_class` schema gap required for accurate approval-risk handling.
  - Scope:
    - `db/schema.py`/`db/bootstrap.py` (new `approvals.risk_class` column + a real, idempotent `ALTER TABLE` migration for pre-existing databases - a plain `CREATE TABLE IF NOT EXISTS` never adds a column to one that already exists; applied to this project's own real local `data/awf_db/awf.db` too)
    - `workflow/approval.py` (a node MAY declare `riskClass`, stored on the approval row at insert time)
    - `cli/core_ops.py` (`op_approval_approve`: an unsupplied `risk_class` now defaults to the real stored value instead of raising - and defaults to `R2`, never R0/R1, when neither exists; a caller-supplied value that contradicts the real stored one is now rejected - closes a real gap where any caller could previously claim any risk class it wanted for the voice-refusal check, with nothing to check it against)
    - `frontend/gui/src/renderer/{App,Dashboard,VoiceActivation,index}.tsx` (`Dashboard.tsx` new - real `runList`/`approvalList` rendering with a refresh button; `App.tsx` fetches both on mount and derives a real `pendingApproval` from the live approvals list instead of requiring one be handed in; `VoiceActivation.tsx` gained a real voice selector over the four shipped Voice Profiles, `onVoiceRoundTrip` now takes the operator's chosen `voiceId` instead of always `bf_isabella`)
  - Validation: 309 backend tests pass (4 new - the migration, the `riskClass` storage, the safe-default, and the stored-vs-claimed mismatch rejection); 66 frontend tests pass across all three workspace packages (8 new GUI tests - dashboard rendering, on-mount fetch, a real pending approval reaching the on-screen `ApprovalConfirmation` dialog, a null risk_class rendering as R2 not silently R0/R1, voice selection actually changing what's passed to the round trip). `tsc --strict` clean. Live-relaunched the real Electron app: React rendered correctly and the `runList`/`approvalList` IPC handlers fired on mount; the backend call failed because the sandbox's GPU/display limitation killed the process mid-request. Applied the DB migration to the project local database and test fixtures.
  - Notes: closed the tracked GUI items after the prior `inputSchema`/`outputSchema`, `payloadSchema`, Adversary Gateway review path, `map` concurrency, and hardware-profile manifest fixes.

- Timestamp: 2026-08-04 06:42
  - Corrects: item (2) in the immediately preceding entry's Notes.
  - Summary: Verified the `*-cuda` STT revision pin using an operator-supplied HuggingFace read token (`awf secret set huggingface-token`, resolved through the secrets store). Authenticated HF API search returned zero results for `Systran/faster-whisper-large-v3-turbo`; the valid repo is `deepdml/faster-whisper-large-v3-turbo-ct2` (MIT-licensed CTranslate2 file set, sha `4df90f75321148c3a29a9e2351b7ddf8f5b115a8`). Both `config/voice/stt/{windows-x64-cuda,linux-x64-cuda}.yaml` now pin this revision instead of the moving `main` branch.
  - Validation: 305 backend tests pass; the "all 48 shipped manifests parse cleanly" test covers these two manifests.
  - Notes: a second real, viable alternative was found and rejected in favor of the one shipped: `mobiuslabsgmbh/faster-whisper-large-v3-turbo` (sha `0a363e9161cbc7ed1431c9597a8ceaf0c4f78fcf`, far more downloads but thinner repo metadata) - noted in the manifest's own `notes` field as a legitimate substitute if `deepdml`'s repo is ever deprecated, not silently discarded.

- Timestamp: 2026-08-04 06:29
  - Host class(es): Linux/WSL2, AMD64
  - Summary: Implemented ADR-0007 (one voice manifest per function, with model selection keyed to the hardware profile).
  - Scope: see `docs/adr/0007-cohesive-voice-config-paths.md` for full detail.
  - Validation: ADR-0007 records the implemented manifest shape and acceptance criteria; neighboring changelog entries record the voice manifest implementation and follow-up model-pin correction.
  - Notes: corrective documentation entry added after the implementation entry was found missing.

- Timestamp: 2026-08-04 06:28
  - Summary: Closed the sixth caveat - all 48 hardware-profile-pinned-artifact manifests (12 profile IDs x 4 functions) now exist under `config/voice/`, and the voice pipeline actually reads them. Two real spec/reality mismatches were found and pinned to reality, not the spec's literal wording: STT's cpu/gpu-class table entry says "sherpa-onnx ONNX export," but the real, installed adapter uses faster-whisper's HuggingFace-hosted model instead; VAD's entry says "sherpa-onnx-packaged," but the real installed copy came from the `silero-vad` PyPI package. Both manifests pin what is actually running, with the mismatch stated in the manifest's own `notes` field, not silently "corrected" to match the spec or silently left wrong.
  - Scope: `registry/hardware_voice_manifest.py` (new - schema, `verify_pinned_files`, `verify_profile_models` with one-hop fallback resolution), `config/voice/{stt,tts,vad,wake}/<profile-id>.yaml` x48 (new), `speech/pipeline.py` (`run_voice_round_trip` gains optional `repo_root` - when given, verifies the resolved profile's pinned models against what's actually on disk and logs the result to `events`, closing "the manifests are pinned but nothing reads them").
  - Validation: 305 backend tests pass (12 new, including a real check that all 48 shipped manifests parse cleanly). Independently re-verified every sha256 myself via a direct `sha256sum` of the real local files before trusting a research pass's transcription of the same values - all matched. Live-verified through the real production path: a real `run_voice_round_trip(..., repo_root=REPO_ROOT)` against the real fixtures checked the real `linux-x64-cpu` manifests (wake/vad/tts/stt, all four) against the real already-downloaded models on this host - every pinned hash matched (`status: OK`), and the verification event is real and queryable.
  - Notes: two things could not be pinned with the same confidence as the rest. (1) STT's `*-qnn` profiles (windows-arm64-qnn, linux-arm64-qnn): no sherpa-onnx Whisper QNN build was available in the checked sherpa-onnx GitHub releases; those releases only published QNN assets for a different model family. These two manifests declare `fallback_to` their arch's `*-cpu` profile, per Section 16.4's fallback rule. (2) STT's `*-cuda` profiles: the HuggingFace repo (`Systran/faster-whisper-large-v3-turbo`) was confirmed to exist, but direct HF API access returned 401 during revision verification; pinned to `revision: main`.

- Timestamp: 2026-08-04 05:48
  - Summary: Closed the fifth caveat - `map`'s `maxConcurrency` now bounds a real thread pool, not just a declared number. Real concurrency needed more than a per-thread DB connection: two items committing into the same shared worktree concurrently would race, so each item now gets its own isolated worktree (branched from the parent's current HEAD) too. Every successful item's commits are merged back into the parent worktree afterward, in item order (`git merge --no-ff`) - a design fork the user picked explicitly (isolated-worktree-plus-merge-back, over a no-merge or leave-sequential alternative) - so later nodes still see a map item's file changes exactly as they could when this ran sequentially in the shared worktree. A merge conflict between two items now fails cleanly (`INTEGRITY_FAILURE`, merge aborted) instead of being possible to hit silently.
  - Scope: `workflow/map_node.py` (rewritten), `isolation/worktree.py` (new `current_head`/`merge_branch`), `cli/core_ops.py` (new `_make_run_map_item`, isolated worktree + own connection per item), `db/connection.py` (new `busy_timeout=5000` PRAGMA - real concurrent writers to the same db file now exist and need to wait for each other rather than fail immediately).
  - Validation: 293 backend tests pass (4 new, real git repos - one exercises an actual merge conflict end to end and confirms the abort leaves the parent worktree clean). Live-verified twice: the tracked 3-item `fan-out-demo` still passes through `op_run_start`; a timing check (3 items each sleeping 2s) showed overlapping `steps.started_at`/`ended_at` windows (19:47:19-21 overlapping 19:47:20-22). Total wall time was 5.68s because per-item worktree creation adds isolation overhead.
  - Next: the original Phase 12 note that the hardware-profile-pinned-artifact manifests (`config/voice/{stt,tts,vad,wake}/<profile-id>.yaml`, Section 16.4) were never built - each speech adapter still uses its own pip-package acquisition path instead. That's next up the same list.

- Timestamp: 2026-08-04 05:33
  - Summary: Closed the fourth buried caveat (found while closing the third) - `run_llm_review`/`run_llm_adversary_review` only ever saw a gate node's short `check` label, never the real candidate content. Now both are shown the real diff the most recent commit introduced (`isolation.worktree.last_commit_diff`, new), alongside the label, since a gate always runs immediately after the agent step whose work it's reviewing.
  - Scope: `isolation/worktree.py` (new `last_commit_diff`), `gates/gate_node.py` (new `worktree_path` param, builds `candidate_content` once and passes it to both review calls), `cli/core_ops.py` (threads `worktree_path=worktree` through).
  - Validation: 292 backend tests pass (3 new). Live-reran the real `high-risk-review-demo` end to end (GPU confirmed idle beforehand) - review quality changed from garbled/hallucinated responses to real, substantive ones: judge → "PASS: Correct implementation returns the sum of a and b per requirement"; adversary → "FAIL: No error handling for non-numeric inputs", "FAIL: The function name 'add' is not descriptive". `check_resource_safety()` tripped again (85-95%, started from idle) - expected and self-consistent, not a new bug: this specific demo routes the judge review through the same GPU-hosted `llama-server` the check is watching, so exercising the review necessarily moves the metric it polices. A real config tension in this one demo workflow, not something to fix by weakening the check.
  - Next: `map`'s `maxConcurrency` is declared and validated but execution is still sequential (disclosed at build time, `sqlite3.Connection` isn't thread-safe, no per-thread connection plumbing exists) - that's next up the same list.

- Timestamp: 2026-08-04 05:20
  - Summary: Closed the third buried caveat - the Adversary role had no Model Gateway-routed review path (only the Verifier's did), and `reviewProfile` had never actually been exercised by any published workflow. Both fixed: a new `run_llm_adversary_review` (`gates/adversary.py`) mirrors the Verifier's LLM review but with an adversarial system prompt and `role="adversary"`, wired into the high-risk tier via a new `adversaryReviewProfile: name@version` gate-node field (`purpose: adversary` Model Profile, Section 11's model-family-diversity rule). Published two real local profiles (`judge-local`, `adversary-local`) and a real workflow (`high-risk-review-demo`) that sets both fields, then ran it live.
  - Scope: `gates/adversary.py`, `gates/gate_node.py`, `cli/core_ops.py`, `data/registry/model-profiles/{judge-local,adversary-local}/1.0.0.yaml` (new), `data/registry/workflows/high-risk-review-demo/1.0.0.yaml` (new).
  - Validation: 289 backend tests pass (4 new). Live-verified both new review functions individually against real local models first (`judge-local` → Qwen3-8B via `llama-server`, `adversary-local` → `phi4-mini` via Ollama, both real PASS Findings). Then ran the real published `high-risk-review-demo` end to end via `op_run_start` - `reviewProfile`/`adversaryReviewProfile` were both genuinely exercised for the first time ever, real Finding artifacts confirm real LLM calls happened.
  - Notes: the real run FAILED (budget-exhausted), and it's informative, not a defect in this fix. Two real things surfaced by actually running this for the first time: (1) `check_resource_safety()` genuinely tripped - real GPU utilization at 95-96%, correctly over its 55% ceiling, most likely because `judge-local` shares the same GPU-hosted `llama-server` the demo's own adapters were also contending for; the safety check did its job. (2) A deeper, pre-existing gap this exposed: both `run_llm_review` and `run_llm_adversary_review` are only ever given a gate node's short `check`/id label (e.g. `"calc_add_returns_sum"`) as `candidate_summary` - never the actual code/diff. The small local models produced visibly low-quality, sometimes hallucinated responses reviewing a bare identifier string with no real content. This predates today's fix (the Verifier's own review path had the exact same gap, just never run for real before) and is the natural next item on the list: the gate executor has no candidate-diff plumbing to give reviewers anything real to look at.

- Timestamp: 2026-08-04 05:02
  - Summary: Closed the second buried caveat - Phase 9's Handoff `payloadSchema` was required and parsed since day one but never validated against a hop's real `handoff_status.json`. Now enforced: a hop whose status file doesn't conform to the node's own declared schema fails the Step with `INVALID_INPUT` instead of silently trusting whatever the agent wrote.
  - Scope: `workflow/handoff.py` only (`jsonschema.validate` on the parsed status dict, right after the existing "did the agent even write the file" check; same `HandoffError` path already used for that sibling failure).
  - Validation: 285 backend tests pass (2 new: a strict schema rejecting a status file missing a required field, and the same schema accepting a conforming one); live-reran the real tracked `producer-reviewer-handoff-demo` end to end against real Claude Code/Codex adapters - `SUCCEEDED`, `outputs: {hops_used: 1}`, unaffected by the new check since its own `payloadSchema` only requires `summary: string`, which the agents already write correctly.
  - Next: the Phase 8-era caveat that the Adversary role still doesn't use the Model Gateway review path, and `reviewProfile` remains unexercised by any published workflow - that's next up the same list.

- Timestamp: 2026-08-04 04:56
  - Summary: Closed the earliest buried caveat found by the full-log re-verification audit - Phase 7's `inputSchema`/`outputSchema` were required and parsed since day one but never actually validated against real values. Now enforced: bad input is refused before a Run is even created; `outputs` templates (`{{ engine.repairs_used }}`, `.hops_used`, `.verdict_artifact_id`) are rendered for real and validated against `outputSchema` at completion, failing the Run cleanly if they don't conform.
  - Scope: `workflow/io_schema.py` (new), `workflow/engine.py`, `cli/core_ops.py` (`op_run_start`), `cli/main.py` (adjacent regression found and fixed: any `CoreOpError` crashed the raw CLI with a traceback - now a clean message + exit 1, matching the JSON-RPC surface's existing safety net), `data/registry/workflows/research-build-review/1.0.0.yaml` (its own `outputSchema` referenced a value the engine never tracked - fixed).
  - Validation: 283 backend tests pass; live-reran both tracked demo workflows and my own - `produce-gate-repair-demo` → `outputs: {repairs_used: 1}`, `producer-reviewer-handoff-demo` → `outputs: {hops_used: 1}`, both real Guard/adapter/gate/handoff runs, correctly rendered and validated.
  - Next: Phase 9's `payloadSchema` (Handoff) has the identical gap - parsed, never enforced against a real hop payload. That's next up the same list.

- Timestamp: 2026-08-04 01:48
  - Corrects: the 2026-08-03 14:49 entry's implicit assumption that Antigravity was covered - it shipped supported behind the scene, but the underlying mechanism (`render_antigravity`) actually raised on any non-empty server list, since Antigravity has no per-invocation MCP flag. Fixed, not worked around.
  - Host class(es): Linux/WSL2, AMD64
  - Summary: Antigravity now gets a real MCP handoff too - all four implemented adapters are supported. Mechanism, tradeoff, and the accepted exception (below) are written into `docs/adr/0003-mcp-server-registry-schema.md` (Mechanism, Scope item 8, Acceptance).
  - Scope:
    - `backend/src/awf/mcp/render.py` (`render_antigravity` renders a fresh `.gemini/config/mcp_config.json` + `.gemini/antigravity-cli/settings.json` instead of raising; new `RenderedMcpConfig.home_relative_files`/`home_copy_paths` fields)
    - `backend/src/awf/engine/agent_step.py` (`_apply_mcp` materializes a scratch `$HOME` under `cache/sandbox/<run_id>/scratch_home/<actor>/`, copies in the real `antigravity-oauth-token`, and injects `HOME` via `mcp_env_overlay`)
    - `backend/tests/test_baseline_mcp_render.py`, `test_baseline_agent_step_mcp.py`
    - `docs/adr/0003-mcp-server-registry-schema.md`
  - Validation:
    - `pytest backend/tests/` → 271 passed
    - Real, non-mocked run through the actual `run_agent_step` → `antigravity_cli.invoke` path: a real `context7@1.0.0` ref produced a real `resolve-library-id` tool call (`react`→`/reactjs/react.dev`, `vue`→`/vuejs/vue`, `svelte`→`/sveltejs/svelte` across separate runs), with the API key resolved via `${VAR}` substitution and injected only into the subprocess env - never written to any file. Demo run/step/event rows and scratch dirs removed afterward.
  - Notes:
    - The real mechanism (confirmed by asking `agy` itself, then live-testing): Antigravity only reads MCP servers from `~/.gemini/config/mcp_config.json` - its actual home directory, with no per-invocation override flag. The fix redirects the subprocess's own `$HOME` env var to a scratch directory instead of touching the operator's real one.
    - Named, accepted exception: the copied `antigravity-oauth-token` is real session-credential material, at rest in `cache/sandbox/<run_id>/` for the Run's duration (longer if the Run fails, per the existing worktree/scratch retention policy) - a real increase in exposure over the other three adapters, where no secret ever touches disk at all.
    - Separately observed, not fixed here (out of scope - unrelated to MCP): in headless print mode, Antigravity sometimes wants to run an arbitrary shell command mid-turn and gets auto-denied (a `command(*)` permission gap, same class as Copilot CLI's still-unbuilt `preToolUse` hook) - nondeterministic, didn't block any run above, flagged for later.

- Timestamp: 2026-08-03 14:49
  - Host class(es): Linux/WSL2, AMD64
  - Summary: ADR-0003 implemented - MCP servers are rendered into each adapter's own config format at Run time and connected by the adapter itself; AWF still has no MCP client. Details, mechanism, and schema: `docs/adr/0003-mcp-server-registry-schema.md`.
  - Scope:
    - `backend/src/awf/registry/mcp_server.py` (new), `backend/src/awf/mcp/render.py` (new)
    - `backend/src/awf/engine/agent_step.py`, `backend/src/awf/workflow/engine.py` (resolve/trust-gate/render/event wiring)
    - `backend/src/awf/adapters/{claude_code,codex_cli,antigravity_cli,copilot_cli}.py` (consume rendered extra args + env overlay)
    - `backend/src/awf/cli/core_ops.py` (`mcp` publish/validate branch)
    - `config/app_registry/mcp/context7/1.0.0.yaml` (shipped default)
    - `backend/tests/test_baseline_mcp_{server,render}.py`, `test_baseline_agent_step_mcp.py`, plus additions to `test_baseline_agent_manifest_wiring.py` and `test_phase10_core_ops.py`
  - Validation:
    - `pytest backend/tests/` → 268 passed
    - Real, non-mocked run: a real `context7@1.0.0` manifest ref drove the actual Claude Code adapter through the real `run_agent_step` path - rendered `mcp/claude-code.mcp.json`, a real `mcp_rendered` event, and a genuine `resolve-library-id("react")` tool call returning `/reactjs/react.dev`, with the API key never touching any file. Demo run/step/event rows and worktree removed afterward.
  - Notes:
    - The `fetch` default drafted during design used a nonexistent npm package (`@modelcontextprotocol/server-fetch` 404s - the real reference server is the Python package `mcp-server-fetch` via `uvx`). Dropped rather than shipped, to avoid adding a second per-invocation runtime; only `context7` ships this pass.

- Timestamp: 2026-08-03 09:10
  - Host class(es): Linux/WSL2, AMD64
  - Summary: Implemented ADR-0002 (Agent Manifest schema and wiring) - `agents` is a real registry kind now, workflow `agent` nodes gain an `agentRef` field, and the Capability Guard's allowlist check is real for the first time.
  - Scope: see `docs/adr/0002-agent-manifest-schema.md` for full detail.
  - Validation: `pytest backend/tests/` → 247 passed; live-verified over the real JSON-RPC transport and a real `awf run` against the actual repo.

- Timestamp: 2026-08-03 08:40
  - Host class(es): Linux/WSL2, AMD64
  - Summary: Aligned `backend/tests/fixtures/` naming to the test that owns each fixture (`test_phaseN/test_phaseN_<name>`), establishing a consistent pattern for future fixture placement.
  - Scope: `backend/tests/fixtures/capabilities/*.yaml` renamed and relocated under `backend/tests/fixtures/test_phase1/`; the three test files referencing them updated to match.
  - Validation: `pytest backend/tests/` → 228 passed, no change in count.
  - Notes: Scoped to the capability-record fixtures only; audio fixtures under `test_phase12` and their tests were outside scope.

- Timestamp: 2026-08-03 08:15
  - Host class(es): Linux/WSL2, AMD64
  - Summary: Added ADR-0001, relocating example Model Profiles off `backend/tests/fixtures/` and onto `config/app_registry/model-profiles/` as clearly-labeled, non-operational references spanning all five `purpose` values and both local and cloud providers; fixed a related `op_registry_list` gap that would have listed them as real.
  - Scope:
    - `docs/adr/0001-example-model-profiles-location.md` (new)
    - `config/app_registry/model-profiles/example-{ollama-general,llamacpp-coding,lmstudio-embedding,anthropic-judge,openai-adversary}/1.0.0.yaml` (new)
    - `backend/tests/fixtures/model_profiles/local_ollama_r0.yaml` (removed, superseded)
    - `backend/tests/test_phase3_model_gateway.py` (retargeted at the new location; tests labeled `test_*_example_*`)
    - `backend/src/awf/cli/core_ops.py` (`op_registry_list` now honors `registry.resolve.DATA_ONLY_KINDS`, matching `resolve_registry_object`/`op_registry_get`)
    - `backend/tests/test_phase10_core_ops.py` (+1 regression test)
  - Validation:
    - `pytest backend/tests/` → 228 passed (227 prior + 1 net new)
    - Real, non-mocked checks: `resolve_registry_object` confirmed to still refuse these files for a real Run; `example-ollama-general` and `example-llamacpp-coding` each completed a genuine round trip through the Model Gateway against real local Ollama/llama-server instances; the two cloud examples' model ids confirmed present in LiteLLM's bundled model registry and reachable (real `AuthenticationError`, not "model not found") against the live OpenAI/Anthropic APIs without credentials for completion calls
  - Notes:
    - `registry/resolve.py::DATA_ONLY_KINDS` still prevents these examples from being resolvable by a real Run; they are listable and loadable directly by path in tests.
    - `example-lmstudio-embedding`'s model name remains a placeholder label - no LM Studio instance was available to verify against.

- Timestamp: 2026-08-03 07:05
  - Corrects: the note in the 2026-08-03 06:10 entry flagging "`activity` is the one Section 12.2 node type still with no executor anywhere."
  - Host class(es): Linux/WSL2, AMD64
  - Summary: `activity` now has a real executor - all eight Section 12.2 node types have working execution semantics for the first time in the build.
  - What was wrong: `activity` was listed in `workflow/engine.py::EXECUTABLE_NODE_TYPES` since the original Phase 7 build (a pre-existing mis-categorization, not introduced by any prior fix in this series), but `cli/core_ops.py` never registered an executor for it - a real workflow reaching an `activity` node failed with "no executor registered," caught cleanly by the existing safety net but never actually running anything.
  - Scope of the fix:
    - `backend/src/awf/workflow/nodes.py` (`activity` now requires a `function` field)
    - `backend/src/awf/workflow/activities.py` (new - `ACTIVITY_REGISTRY`: `hardware_probe` wraps `run_hardware_profiler` - the R0 hardware-probe activity Section 12.3's Adversary resource-safety obligation describes, now invocable mid-Run, not just at voice setup; `gpu_utilization_sample` wraps `sample_gpu_utilization`)
    - `backend/src/awf/workflow/engine.py` (new `make_activity_node_executor`: looks up `node["function"]` in the registry and runs it through the normal `run_step` durability path inside the Step's own `fn`, so an unregistered name is recorded as a real `FAILED`/`INVALID_INPUT` Step, not raised before any Step exists to record it)
    - `backend/src/awf/cli/core_ops.py` (`_build_node_executors` registers `"activity"` unconditionally, same as `agent`)
    - `backend/tests/test_baseline_activity_node.py` (new, 3 tests: a real hardware-probe run persists correctly, an unregistered name fails the Step cleanly, and a replay after `SUCCEEDED` returns the cached output without re-probing)
    - `backend/tests/test_phase7_workflow_nodes.py`, `test_phase10_core_ops.py` (updated for the new required field; the pre-existing "unbuilt node type" test switched to a real runtime error - an unregistered activity name - since no node type is unbuilt anymore)
    - `backend/tests/test_phase7_workflow_definition.py` (fixture regression caught and fixed: two tests used a bare `{"type": "activity"}` node with no `function`, which no longer parses now that the field is required)
  - Validation:
    - `pytest backend/tests/` → 223 passed (219 prior + 4 net new)
    - Real, non-mocked run against the actual repo: published a real `activity` workflow calling `hardware_probe`, ran it via `awf run`, confirmed `SUCCEEDED`, and - by querying the real `data/awf_db/awf.db` directly - the Step's `output_json` contained a genuine `"profile_id": "linux-x64-cpu"` from the real Hardware Profiler, not a stub. Demo workflow file and DB rows removed afterward; `git status` shows no residue.
  - Notes:
    - **All eight Section 12.2 node types now have real execution semantics.** This closes the entire deferred-items list first flagged in the 2026-08-03 03:15 entry (Model Gateway, Hardware Profiler, node executors x5, voice_approval.py).
    - `gpu_utilization_sample` is registered but has no workflow currently calling it - available, not yet exercised end to end.

- Timestamp: 2026-08-03 06:45
  - Corrects: the note in the 2026-08-03 03:15 entry flagging "the Python-side `gates/voice_approval.py` still has zero real callers."
  - Host class(es): Linux/WSL2, AMD64
  - Summary: `gates/voice_approval.py::attempt_voice_approval` now has a real caller - `op_approval_approve` itself enforces the Section 16.4 rule that an R2+ approval MUST NOT be granted from voice input alone, reachable over the real `awf/approval.approve` JSON-RPC method. This enforcement now lives in the core, not only in the GUI's separate TypeScript copy of the same rule - no frontend can bypass it by skipping its own check.
  - What was wrong: `attempt_voice_approval`/`decide_voice_acknowledgement` existed, were correctly implemented, and were fully unit-tested, but nothing in the real approval path ever called them - the only enforcement of the R2+ voice-refusal rule was the GUI's independent client-side TypeScript logic.
  - Scope of the fix:
    - `backend/src/awf/cli/core_ops.py` (`op_approval_approve` takes optional `channel` (default `"manual"`) and `risk_class`; `channel="voice"` delegates to `attempt_voice_approval` via a deferred import to avoid a circular import with `gates/voice_approval.py`; raises `CoreOpError` if `channel="voice"` is given without a `risk_class`)
    - `backend/src/awf/server/stdio.py` (`awf/approval.approve` now passes through optional `channel`/`riskClass` params to `op_approval_approve`)
    - `backend/tests/test_phase12_voice_approval.py` (+4 tests: voice-channel R2 stays pending, voice-channel R0 actually approves, missing `risk_class` raises, default `channel="manual"` behavior is unchanged)
    - `backend/tests/test_phase10_server_stdio.py` (+1 test: a real R2 approval sent over JSON-RPC with `channel: "voice"` correctly stays pending)
  - Validation:
    - `pytest backend/tests/` → 219 passed (214 prior + 5 net new)
    - Real, non-mocked proof over the actual JSON-RPC transport: seeded a genuine pending approval in the real `data/awf_db/awf.db`, piped a real `awf/approval.approve` request with `channel: "voice", riskClass: "R2"` into `awf serve --stdio` - stayed `pending` with `requires_on_screen_confirmation: true`; a second request without the voice channel against the same approval genuinely returned `approved`. Demo rows removed afterward; `git status` shows no residue.
  - Notes:
    - This closes the last item from the original deferred-items list (Model Gateway, Hardware Profiler, node executors, voice_approval.py) - all four have now been given real callers and live-verified, except `activity`, which remains explicitly unbuilt and flagged (2026-08-03 06:10 entry).
    - The GUI's TypeScript enforcement (`frontend/gui/src/renderer/ApprovalConfirmation.tsx`) remains independently correct; this fix adds a second, authoritative enforcement point in the core.

- Timestamp: 2026-08-03 06:10
  - Corrects: the note in the 2026-08-03 03:15 entry flagging "`approval`/`subworkflow`/`map`/`loop` node executors still don't exist."
  - Host class(es): Linux/WSL2, AMD64
  - Summary: `approval`, `subworkflow`, `map`, and `loop` now have real execution semantics in the workflow engine - four of the five previously-unbuilt Section 12.2 node types (`activity` remains explicitly out of this fix's scope). `activity` is still unbuilt and is flagged, not silently left implied-done.
  - What was wrong: `workflow/nodes.py`/`workflow/engine.py` validated these four node shapes but raised `WorkflowEngineError` (or "no executor registered") the moment a real workflow reached one - none had a working executor anywhere in the codebase.
  - Scope of the fix:
    - `backend/src/awf/workflow/nodes.py` (`subworkflow` now requires `workflowRef`; `map` additionally requires `workflowRef`/`items`; `loop` additionally requires `workflowRef`)
    - `backend/src/awf/workflow/approval.py` (new - `make_approval_node_executor`: computes a real action digest, inserts a real `approvals` row, and holds the Step in `WAITING_APPROVAL` - deliberately bypassing `run_step`'s automatic SUCCEEDED-caching while still pending, since that would have permanently frozen the "still waiting" result across a resume; a rejected decision fails the Step with `APPROVAL_REJECTED`)
    - `backend/src/awf/workflow/subworkflow.py` (new - `make_subworkflow_node_executor`: starts a version-pinned child Workflow as a real, independent `runs` row and runs it to completion through the same durable engine before the parent Step is considered done)
    - `backend/src/awf/workflow/map_node.py` (new - `make_map_node_executor`: bounded fan-out over a literal `items` list embedded in the node - `maxItems` is enforced; `maxConcurrency` is validated as a declared bound but execution is sequential, since the shared `sqlite3.Connection` isn't thread-safe and no per-thread connection plumbing exists - documented as a real limitation, not claimed as true parallelism)
    - `backend/src/awf/workflow/loop_node.py` (new - `make_loop_node_executor`: repeats a child Workflow while a named boolean field in the child's own last-Step output holds true, feeding that output forward as the next iteration's input; self-stepping like Handoff, so reaching `maxIterations` while still true moves the Run to `WAITING_INPUT` rather than getting cached as a false terminal success)
    - `backend/src/awf/workflow/engine.py` (`EXECUTABLE_NODE_TYPES` gains all four; `SELF_STEPPING_NODE_TYPES` gains `loop`, alongside `handoff`)
    - `backend/src/awf/cli/core_ops.py` (new `_make_run_child`: the shared "resolve + build executors + run to completion + clean up scratch dir" callback used by `subworkflow`/`map`/`loop`; `_build_node_executors` registers all four unconditionally, same as `agent`)
    - `backend/tests/test_baseline_{approval,subworkflow,map,loop}_node.py` (new, 21 tests against each executor directly)
    - `backend/tests/test_phase10_core_ops.py` (+3 real end-to-end tests through `op_run_start` with genuinely published parent+child workflows; the pre-existing "unbuilt node type" test switched from `subworkflow` - now built - to `activity`, which still has no executor)
    - `backend/tests/test_phase7_workflow_nodes.py` (fixture updated for the new required fields)
  - Validation:
    - `pytest backend/tests/` → 214 passed (198 prior + 16 net new)
    - Real, non-mocked run against the actual repo: published a real `map` workflow fanning out to 3 items over a real child gate workflow, ran it via `awf run`, confirmed `SUCCEEDED` and - by querying the real `data/awf_db/awf.db` directly - exactly 3 independent, genuinely `SUCCEEDED` child `runs` rows, plus normal worktree cleanup (`git worktree list` empty afterward). Demo workflow files and DB rows removed afterward; `git status` shows no residue.
  - Notes:
    - **`activity` is the one Section 12.2 node type still with no executor anywhere** - it remains in `EXECUTABLE_NODE_TYPES` (a pre-existing, unrelated mis-categorization from the original Phase 7 build, not introduced here) but `core_ops.py` never registers one; a real workflow reaching an `activity` node still fails cleanly via the existing `_run_workflow_safely` boundary, it just doesn't run anything. Not fixed in this pass - out of the requested scope.
    - `map`'s `items` must be a literal list embedded in the node; there is no runtime expression language to pull items from a Run's own input dynamically.
    - `loop`'s condition-field convention (reading the child's last Step output) is this implementation's own choice, not dictated by the spec text, which only says "while a condition holds."

- Timestamp: 2026-08-03 05:05
  - Corrects: the note in the 2026-08-03 03:15 entry flagging "the Hardware Profiler is still never invoked automatically."
  - Host class(es): Linux/WSL2, AMD64
  - Summary: `run_hardware_profiler` is now called automatically at the start of every real voice round trip (Section 16.4: "run ... before any voice model is downloaded or loaded"), and its result is not just logged - it genuinely selects the STT device/compute_type.
  - What was wrong: the Hardware Profiler (Phase 12) had zero callers outside its own unit tests; `speech/pipeline.py::run_voice_round_trip` loaded wake/VAD/TTS models and ran STT unconditionally on a hardcoded `device="cpu"`, regardless of what hardware was actually available.
  - Scope of the fix:
    - `backend/src/awf/speech/stt_whisper.py` (`transcribe` takes a `device` parameter, previously hardcoded to `"cpu"`)
    - `backend/src/awf/speech/pipeline.py` (`run_voice_round_trip` now requires a `conn` and calls `run_hardware_profiler(conn)` first, before any model loads; new `_stt_device_for_profile()` maps a resolved profile ending in `-cuda` to `("cuda", "float16")` and everything else to the safe `("cpu", "int8")` floor; `VoiceRoundTripResult` carries the resolved `hardware_profile_id`)
    - `backend/src/awf/speech/cli.py` (`awf-speech round-trip` now opens the real repo `data/awf_db/awf.db` and passes the connection through, so the resolution event lands in the same audit trail as every other operation; the resolved profile id is included in the printed JSON result)
    - `backend/tests/test_phase12_voice_pipeline.py` (all three existing tests updated for the new required `conn` argument; +2 tests: the profiler event is genuinely written to `events`, and `_stt_device_for_profile`'s selection logic across every canonical profile suffix)
  - Validation:
    - `pytest backend/tests/` → 198 passed (197 prior + 1 net new)
    - Real, non-mocked run: `python -m awf.speech.cli round-trip` against the real committed audio fixtures returned `"hardware_profile_id": "linux-x64-cpu"` - correct for this host, whose `onnxruntime` build has no CUDA execution provider (confirmed by the accompanying provider-unavailable warning); a direct query against the real `data/awf_db/awf.db` afterward confirmed a genuine `hardware_profile_resolved` event was written, not just returned in-memory
  - Notes:
    - Only the STT device/compute_type is driven by the resolved profile; wake-word/VAD/TTS still run through their default ONNX Runtime provider selection because openWakeWord/Kokoro's constructors do not expose an equivalent device override. The Hardware Profiler's accelerator-manifest-pinning mechanism (Section 16.4's `config/voice/*` YAML table) remains open.

- Timestamp: 2026-08-03 04:20
  - Corrects: the note in the 2026-08-03 03:15 entry flagging "the Model Gateway still has no real adapter-path caller."
  - Host class(es): Linux/WSL2, AMD64
  - Summary: The Model Gateway now has a real caller - the Verifier's previously-unbuilt "LLM-driven independent code-review pass" is implemented and routed through `gateway/client.py::complete()` via a `purpose: judge` Model Profile (an enum value that existed since Phase 3 but was never used).
  - What was wrong: `gates/verifier.py` documented the LLM-review half of the Verifier's Section 12.3 obligation as explicitly not built; the Model Gateway (Phase 3) was exercised only by its own validation call, never by anything in the real gate/verification path.
  - Scope of the fix:
    - `backend/src/awf/gates/verifier.py` (new `run_llm_review()`: sends a fixed review prompt plus the candidate summary through `gateway.client.complete()`, parses a `PASS`/`FAIL` response into the same structured `Finding` contract `run_verifier_check` already produces)
    - `backend/src/awf/gates/gate_node.py` (`make_trifecta_gate_executor` takes optional `review_profile`/`review_secret_key`; when a profile is given, its Finding is appended alongside the deterministic check, in both gate tiers)
    - `backend/src/awf/cli/core_ops.py` (new `_resolve_review_profile`: a gate node MAY declare `reviewProfile: name@version`, resolved via the existing registry lookup and threaded into the gate executor; the operator's `.env` secret key is resolved the same way `op_secret_set` already does, tolerating a missing `.env`)
    - `backend/tests/test_phase8_gates_verifier_adversary.py` (+4 tests: PASS/FAIL response mapping, and that the review is genuinely routed through `gateway.client.complete()`)
    - `backend/tests/test_phase8_gate_node.py` (+1 test: a gate node wired with a `review_profile` produces two Finding artifacts, not one)
  - Validation:
    - `pytest backend/tests/` → 197 passed (193 prior + 4 net new)
    - Real, non-mocked proof against the already-published `data/registry/model-profiles/phi4-mini/1.0.0.yaml` and local Ollama: `run_llm_review` given a candidate with `return a - b` (mislabeled as addition) returned a real `FAIL` Finding correctly identifying the subtraction bug; the same call given the corrected `return a + b` returned a real `PASS` Finding - both from genuine model inference, not stubbed responses
  - Notes:
    - The high-risk tier's Adversary role still does not use the Gateway - only the Verifier's new optional review path does. `reviewProfile` is opt-in per gate node; no existing published workflow sets it, so this path is available but not yet exercised by any real workflow run end to end.

- Timestamp: 2026-08-03 03:15
  - Corrects: nothing prior is factually wrong; this closes a gap a report-only Phase 10/11 review found - Section 18 non-negotiable #1 ("No workflow logic may bypass the Capability Guard") was violated by the real execution path, and three durability/cleanup defects were present alongside it.
  - Host class(es): Linux/WSL2, AMD64
  - Summary: A direct codebase-integrity pass (application code first, tests only swept afterward to match) fixed five real defects in the actual execution path: the Capability Guard was never consulted for real agent invocations; an uncaught exception left a Run/Step stuck in `RUNNING` forever with no `failure_class`; worktrees and scratch dirs leaked on every real Run; the high-risk Trifecta tier had no YAML path to reach it; and `/skills` was permanently broken by a registry naming-convention mismatch.
  - What was wrong:
    1. **The Capability Guard had zero real callers.** `workflow/engine.py::make_agent_node_executor` called the adapter directly; `guard/capability_guard.py::authorize()` was exercised only by its own unit tests. Any real workflow's `agent` node ran with no authorization check at all.
    2. **`engine/executor.py::run_step` had no exception handling.** A raised exception during a real Step left `steps.status='RUNNING'` forever, with no `failure_class` and no event recorded - the crash simply propagated to the caller.
    3. **`cli/core_ops.py` never called `remove_worktree`/`remove_scratch_dir`.** Every real `awf run` left its worktree and scratch directory on disk permanently; both functions existed and were unit-tested but had no real caller.
    4. **The high-risk Trifecta tier (`gates/adversary.py`) had no YAML field to select it.** `make_trifecta_gate_executor`'s `tier`/`cache_sandbox_dir` parameters were never threaded from a workflow file, so the Adversary pass was unreachable outside its own unit tests.
    5. **`op_registry_list(kind="skills")` globbed for `<name>/<version>.yaml`**, but skills publish as `<name>/<version>/SKILL.md` (Section 9.3) - the `/skills` command could never find a real published skill.
  - Scope of the fix:
    - `backend/src/awf/engine/executor.py` (new `StepFailure` exception; `run_step` now catches any exception, records `FAILED` + `failure_class` + an event, then re-raises)
    - `backend/src/awf/engine/agent_step.py` (`run_agent_step` is now the single canonical agent-Step path: calls the real Guard's `authorize()` before the adapter runs; `AgentStepError(StepFailure)` maps adapter statuses to failure classes)
    - `backend/src/awf/workflow/engine.py` (removed the dead `make_gate_node_executor`; `make_agent_node_executor` now delegates to `run_agent_step`; added `_synthesized_capability_for_node`/`_resolve_node_capability` so every `agent` node is Guard-checked even without a declared `capability`; `run_workflow_definition` wraps the executor call and marks the Run cleanly `FAILED` instead of propagating)
    - `backend/src/awf/workflow/handoff.py` (`HandoffError` now carries `failure_class`, so `run_step`'s generic handler records it correctly)
    - `backend/src/awf/cli/core_ops.py` (added `_cleanup_run_workspace` - removes the worktree and scratch dir on `SUCCEEDED`; added `_run_workflow_safely` - an outer boundary marking the Run `FAILED` cleanly on any exception, including structural `WorkflowEngineError`s; `_build_node_executors` threads `tier`/`cache_sandbox_dir`/`guardBypassed` from the gate node's YAML into the Trifecta executor; `op_registry_list` special-cases `kind == "skills"` to glob `<name>/<version>/SKILL.md`)
    - `backend/tests/test_phase9_handoff.py`, `test_phase5_agent_step.py`, `test_phase10_core_ops.py` (updated/added to match the corrected behavior: clean `FAILED` results instead of raised exceptions where the Run-level boundary now catches them; two new Guard-integration tests proving an R3 capability is denied before the adapter runs and an R1 capability is allowed through)
    - `data/registry/skills/demo-skill/1.0.0/SKILL.md` (a real published skill, used to verify the `/skills` fix live, not a test fixture)
  - Validation:
    - `pytest backend/tests/` → 191 passed (188 prior + 3 net new)
    - Real, non-mocked run: `awf run produce-gate-repair-demo@1.0.0` succeeded; the real `events` table shows Guard decision events for both `agent_node_produce@0.0.0` and `agent_node_repair@0.0.0` (`reason_code: approval_never`) that did not exist before this fix; `git worktree list`/`ls cache/worktrees/` confirm no leftover worktree after the run, the first time in the whole build this cleanup has been automatic rather than manual
    - Published a real skill under `data/registry/skills/demo-skill/1.0.0/SKILL.md` and confirmed `op_registry_list(kind="skills")` now finds it (previously would have returned empty for any real skill)
  - Notes:
    - Remaining scope: the Model Gateway (`gateway/client.py`) still has no real adapter-path caller; `activity`/`approval`/`subworkflow`/`map`/`loop` node executors still don't exist, so the high-risk tier is reachable via YAML but no workflow currently sets it; the Hardware Profiler is still never invoked automatically; the Python-side `gates/voice_approval.py` still has zero real callers and duplicates the GUI-side TypeScript rule as defense in depth.
    - The Guard's authorization for a node with no declared `capability` uses a conservative synthesized R1/approval-never `CapabilityRecord` rather than a real registered one - this keeps every invocation authorized and logged, but is not equivalent to an operator having actually reviewed and published a Capability Record for that specific action.

- Timestamp: 2026-08-03 02:00
  - Corrects: the Phase 12 entry (2026-08-03 01:23) and the Phase 8 entry's Verifier/Adversary notes.
  - Host class(es): Linux/WSL2, AMD64
  - Summary: An independent audit (four fresh agents, one per phase group, each re-running tests and reading code without trusting this log) found two real gaps behind claims that were either overstated or under-flagged. Both are now fixed.
  - What was wrong:
    1. **Phase 8 claimed Trifecta role separation without enforcing it.** Section 12.3 requires the Capability Guard to deny a `verifier`-scoped invocation any write capability above R0 and an `adversary`-scoped invocation any capability that alters the worktree - enforced by the Guard, never by agent self-assessment. `guard/capability_guard.py::evaluate()` had no `role` parameter at all; this was never built, only implied by the Verifier/Adversary Finding-producing functions existing.
    2. **Phase 12's "full round-trip... was validated" claim was overstated.** The wake→STT→response→TTS chain had not been added to the repository. `frontend/gui/src/` had zero audio/mic/wake-word code - no integrated pipeline existed anywhere in the repository, only four independently-tested adapters.
  - Scope of the fix:
    - `backend/src/awf/guard/capability_guard.py` (`evaluate`/`authorize` take an optional `role` parameter; `verifier` denied any write-type operation above R0, `adversary` denied any write-type operation, both checked before risk-class evaluation)
    - `backend/tests/test_phase1_registry_guard.py` (+8 tests covering both roles, the builder/no-role unrestricted case, an invalid role, and the role recorded in the `events` payload)
    - `backend/src/awf/speech/pipeline.py` (new - `run_voice_round_trip`, chaining wake word -> VAD -> STT -> core -> TTS for real, raising rather than silently proceeding if the wake word doesn't fire or VAD finds no speech)
    - `backend/src/awf/speech/cli.py` (new - `awf-speech round-trip`, a standalone subprocess entry point so a non-Python caller can invoke the pipeline the same way the GUI already spawns `awf serve --stdio`)
    - `backend/pyproject.toml` (registered the `awf-speech` console script)
    - `backend/tests/test_phase12_voice_pipeline.py` (new, 3 tests: the real chained round trip, the wake-word-never-fires error path, and that `core_fn`'s response carries through to TTS input)
    - `frontend/gui/src/main/voicePipeline.ts` (new - `runVoiceRoundTrip`/`registerVoiceIpcHandler`, spawning the real `awf-speech` subprocess from the Electron main process)
    - `frontend/gui/src/renderer/VoiceActivation.tsx` (new - a push-to-talk-by-file control: operator supplies a wake-word file path and a command file path)
    - `frontend/gui/src/renderer/App.tsx`, `index.tsx`, `src/preload/preload.ts` (wired the new IPC channel through; recognized text and response both land in the same visible Transcript as any other command)
    - `frontend/gui/tests/{voicePipeline,App.voiceRoundTrip}.test.tsx` (new, 7 tests)
  - Validation:
    - `pytest backend/tests/` → 188 passed (177 prior + 8 Guard-role tests + 3 pipeline tests)
    - `vitest --root gui` → 20 passed (13 prior + 4 voicePipeline + 3 App-wiring)
    - Real, non-mocked proof: called the compiled `registerVoiceIpcHandler`'s handler directly (the same function `main.ts` registers against Electron's real `ipcMain`), which spawned the real `awf-speech` subprocess, which ran real wake-word/VAD/STT/TTS inference against the real audio fixtures and returned a real transcript, response text, and response WAV file through the same JSON-RPC-shaped path the GUI uses
  - Notes:
    - The Guard's role enforcement covers only the pre-execution, input-side half of Section 12.3's "prompt enforcement" rule. Detecting an agent that claims a different role in its own output is a separate mechanism (inspecting `AgentResult.output` after the fact) and remains open.
    - The voice pipeline is push-to-talk-by-file, not live microphone capture: the operator supplies pre-recorded wake-word and command audio files rather than speaking into a live stream. Live `getUserMedia` capture in the renderer, and a human confirming the four voices sound right, remain open.

- Timestamp: 2026-08-03 01:23
  - Host class(es): Linux/WSL2 (WSLg, PulseAudio-over-RDP virtual audio devices), AMD64
  - Summary: Completed Phase 12 (AWF-GUI voice) of the AWF build sequence, the final phase in the build sequence - the Hardware Profiler, all four Voice Profile registry objects, real STT/TTS/VAD/wake-word adapters, the R2+ voice-approval refusal rule (enforced on both the Python core and the GUI), and the `frontend/gui/` Electron+React desktop shell. A full wake-word -> STT -> response -> TTS round trip was validated for real using the operator-supplied audio fixtures, with two agent roles producing measurably distinct synthesized voices.
  - Scope:
    - `backend/src/awf/hardware/profiler.py` (new - `resolve_hardware_profile_id`, `run_hardware_profiler`)
    - `backend/src/awf/registry/voice_profile.py` (new - Voice Profile schema/parser, mirrors `model_profile.py`'s pattern)
    - `config/app_registry/voice-profiles/{narrator,builder,verifier,adversary}/1.0.0.yaml` (new - the four default profiles, Section 16.5's exact voice_id assignments)
    - `backend/src/awf/speech/{__init__.py,wake_openwakeword.py,vad_silero.py,stt_whisper.py,tts_kokoro.py}` (new - one adapter per selected engine: openWakeWord, Silero VAD, faster-whisper, kokoro-onnx)
    - `backend/src/awf/gates/voice_approval.py` (new - `decide_voice_acknowledgement`/`attempt_voice_approval`: R2+ is never granted from voice alone)
    - `backend/pyproject.toml` (added `onnxruntime`, `onnx`, `openwakeword`, `faster-whisper`, `kokoro-onnx`)
    - `backend/tests/test_phase12_{hardware_profiler,voice_profile,speech_adapters,voice_approval}.py` (new, 39 tests)
    - `frontend/gui/` (new - package `awf-gui`: Electron main process (`main/main.ts`, `main/ipc.ts`), preload (`preload/preload.ts`), React renderer (`renderer/App.tsx`, `Transcript.tsx`, `ApprovalConfirmation.tsx`), `voiceApproval.ts` (the same R2+ refusal rule mirrored client-side), 13 vitest/@testing-library/react tests)
    - `frontend/package.json` (workspaces now includes `gui`)
    - `.gitignore` (added the missing `/models/vad/*` + `!.gitkeep` pair - `models/vad/` was listed in Section 16.4 but never had a matching rule; added `.gitkeep` placeholders for `models/{llm,stt,tts,vad,wake}/`, none of which existed before this phase)
    - `models/{stt,tts,vad,wake}/` (new, gitignored - the operator-downloaded model files themselves; see Notes)
  - Validation:
    - `pytest backend/tests/` → 177 passed (146 prior + 31 new across `test_phase12_{hardware_profiler,voice_profile,speech_adapters,voice_approval}.py`); `vitest` across `shared`/`cli`/`gui` → 7 + 31 + 13 = 51 passed
    - Real Hardware Profiler run on this host: resolved `linux-x64-cpu` (the guaranteed floor) - `onnxruntime`'s installed build only has `CPUExecutionProvider` (no CUDA build installed), so the Profiler correctly refused to claim `linux-x64-cuda` despite a real NVIDIA GPU being present on the host (`nvidia-smi` confirms it) - probe-verification working exactly as specified, not just listing availability
    - Real wake-word detection against the operator-supplied fixtures (`backend/tests/fixtures/*.wav`): `hey_jarvis.wav` scored 0.96, `hey_jarvis_ref.wav` scored 0.99 (both fire), `hello_world.wav` scored 0.0006 (correctly does not fire) - openWakeWord's own bundled `hey_jarvis_v0.1.onnx`, `melspectrogram.onnx`, `embedding_model.onnx`, and (bonus) `silero_vad.onnx` were copied from the installed pip package into `models/wake/`/`models/vad/` rather than fetched from a separate URL, since the package installation already required and performed that download
    - Real Silero VAD segment detection on both fixtures (genuine speech spans with real timestamps, not stubbed)
    - Real STT via faster-whisper (`small`, int8, CPU) on `hello_world.wav` transcribed "Hello world." with 93.7% language-confidence for English - independently verifiable against the filename/content, since I can't listen myself
    - Real TTS via kokoro-onnx (downloaded `kokoro-v1.0.onnx` + `voices-v1.0.bin`, ~354MB total, from the upstream GitHub release) for all four registered voice_ids, then objective acoustic evidence of distinctness since I cannot hear the output: median-F0 pitch estimation via autocorrelation gave narrator/bf_isabella ≈212Hz and verifier/bf_emma ≈198Hz (both in the typical female speaking range) versus builder/am_michael ≈128Hz and adversary/bm_george ≈159Hz (both in the typical male range) - correctly clustering by each voice_id's documented gender, and real playback through the host's actual virtual audio device (`paplay --device=RDPSink`, WSLg's PulseAudio-over-RDP) exited 0
    - Full round-trip demo: wake word (`hey_jarvis.wav`) -> STT (`hello_world.wav`, standing in for the post-wake-word command) -> a trivial core response string -> TTS in two different agent roles' voices (narrator, builder) - all real model inference, no stubs
    - R2+ voice-refusal rule validated on both sides: Python (`attempt_voice_approval` leaves an R2 approval `pending` even with `voice_confirmed=True`, then a separate real `op_approval_approve` call - standing in for on-screen confirmation - succeeds normally) and the GUI's React `ApprovalConfirmation` component (`voiceConfirmed=true` + `riskClass="R2"` never auto-calls `onApprove`; only a real `fireEvent.click` on the Approve button does; `riskClass="R0"` auto-approves from voice alone, since Section 16.4 permits that)
  - Notes:
    - **I cannot hear audio or drive a live microphone, so this phase's validation is necessarily file-based/offline plus objective acoustic measurement, not a live wake-word/mic round trip or a human confirming the voices "sound right."** The user provided real audio fixtures (`backend/tests/fixtures/{hey_jarvis,hey_jarvis_ref,hello_world}.wav`, 16kHz mono PCM) specifically to make this possible; every adapter above was exercised against those real files, not synthetic/mocked ones, and produced results a human can independently check (a real transcript, real detection scores, real playback through a real audio device). Genuine live wake-word capture through a microphone and a human confirming the four voices sound distinct are still open - they need the operator's own ears and hardware.
    - The Electron shell (`frontend/gui/`) was built and compiles clean under `tsc --strict`, but launching a real Electron window and visually confirming its rendering is equally outside what I can verify - rigor was concentrated on the React component layer (`ApprovalConfirmation`, `Transcript`, IPC wiring), which is fully testable via jsdom/@testing-library without launching Electron itself
    - The exact hardware-profile-pinned-artifact mechanism (`config/voice/{stt,tts,vad,wake}/<profile-id>.yaml` manifests pinning URL + SHA-256, Section 16.4's manifest table) was not built - each adapter uses its natural pip-package model-acquisition path instead (faster-whisper's own HF downloader, kokoro-onnx's GitHub release assets, openWakeWord's bundled files) for this validation pass; the pinning/manifest layer remains open
    - `decide_voice_acknowledgement`/`attempt_voice_approval` are not exposed as new `awf serve --stdio` JSON-RPC methods - Section 16.3's method surface is stated as exhaustive, and this rule is a GUI-side behavior constraint per Section 16.4's own wording ("The GUI MUST display..."), not a new core operation; the Python version exists as reusable, tested reference logic (defense in depth) and the GUI enforces the identical rule client-side in TypeScript
    - This was the last phase in the Section 6 build sequence (Phase 12 of 12)

- Timestamp: 2026-08-02 16:23
  - Host class(es): Linux/WSL AMD64
  - Summary: Completed Phase 11 (AWF-CLI TUI) of the AWF build sequence — the `frontend/` npm-workspaces monorepo, `@awf/protocol-client` (the single TS protocol client, Section 16.3), and `awf-cli`, an inline Ink 7 + React 19.2 terminal UI implementing every built-in slash command in Section 16.2. Along the way, found and fixed two real durability bugs in the Python core that only surfaced once multiple real Runs accumulated in the same persistent repo database.
  - Scope:
    - `frontend/{package.json,tsconfig.base.json}` (new - npm workspaces root: `shared`, `cli`)
    - `frontend/shared/` (new - package `@awf/protocol-client`: `client.ts`, `transport.ts` (spawns `awf serve --stdio`), `types.ts`, 7 vitest tests)
    - `frontend/cli/` (new - package `awf-cli`: `commands.ts` (slash-command dispatch, testable independent of Ink), `settings.ts` (Section 16.2 `~/.awf`/`<repo>/.awf` precedence + schema validation), `App.tsx` (Ink component: `<Static>` scrollback, live input line, fuzzy slash-command suggestions), `cli.tsx` (entry point), 31 vitest/ink-testing-library tests)
    - `backend/src/awf/engine/run.py` (bug fix: `create_step` is now `INSERT OR IGNORE` - idempotent - since resuming a crashed Run re-walks the same node sequence and re-requests a `step_id` that already exists; the prior plain `INSERT` raised `UNIQUE constraint failed` on any second resume attempt)
  - Validation:
    - `pytest backend/tests/` → 146 passed (`create_step` fix covered by the live crash-safety demo below); `vitest` → 7 passed (`shared`) + 31 passed (`cli`) = 38 new
    - Both packages built clean under `tsc --strict` with no type errors
    - Real end-to-end validation via a genuine PTY (not ink-testing-library, which couldn't reliably drive Ink 7's keypress internals through a synthetic stdin - see Notes): spawned the compiled `dist/cli.js` under a pseudo-terminal, typed every built-in command from the Section 16.2 table character-by-character, and confirmed each produced correct output against the real repo: `/runs`, `/workflows`, `/capabilities`, `/model`, `/secrets` all showed real prior-phase data; `/agents`/`/skills`/`/mcp`/`/voices`/`/approvals` correctly showed empty (nothing published/pending for those kinds yet); `/settings`/`/theme`/`/keybindings` returned defaults without touching the protocol client
    - Crash-safety (the phase's other named exit condition): typed `/run produce-gate-repair-demo@1.0.0`, waited for the produce Step to genuinely be in flight (`RUNNING` in `steps`, real `claude` subprocess active), then `os.killpg(SIGKILL)` the TUI's entire process group - the Node process, its `awf serve --stdio` child, and that child's own `claude` subprocess all died together (confirmed via `pgrep -g` on the killed group). The Run was left `RUNNING` with `produce#1` still `RUNNING` and the worktree intact. A completely independent `awf resume` (Python CLI, no relation to the dead TUI) then completed the Run to `SUCCEEDED` - `git log` in the worktree showed exactly one `workflow: produce` and one `workflow: repair` commit, confirming no duplicated side effects
  - Notes:
    - **Two real bugs found and fixed while proving the above, both latent since Phase 7/10 and only surfaced now that Phase 11 ran several real Runs back-to-back against the same persistent repo database** (every earlier phase's demo used a throwaway `/tmp` db):
      1. `workflow/engine.py`'s `step_id` scheme (`f"{node_id}#{attempt}"`) was unique only per node, not globally - Section 8's `step_id` is a PRIMARY KEY across the whole table, so a second Run of the same workflow collided with the first. Fixed by scoping it to `f"{run_id}:{node_id}#{attempt}"` (also fixed live, during Phase 10's own JSON-RPC validation - see that entry).
      2. `engine/run.py`'s `create_step` (this phase's fix, above) - resuming re-requests an existing `step_id`.
    - Two runs got orphaned in `RUNNING` mid-debugging (their worktree directories vanished while iterating on the PTY driver script itself, unrelated to the bugs above) and were administratively marked `FAILED`, then `awf resume` confirmed clean (`[]`) before the deliberate crash-safety demo
    - `ink-testing-library`'s fake stdin doesn't reliably drive Ink 7's `internal_eventEmitter`-based keypress pipeline in this dependency combination - a synthetic `stdin.write()` of a full string never reaches `ink-text-input`'s `useInput` handler, whereas a real PTY sending one character at a time (matching real keyboard behavior) works perfectly. `App.test.tsx` therefore only smoke-tests the initial static render; the interactive behavior is validated by the PTY demo instead, not left silently unverified.
    - `npm audit` flags a dev-only `esbuild`/`vite`/`vitest` v2 transitive advisory (dev-server request forgery) - not a runtime risk for local `vitest run` usage; not forced to the breaking `vitest` v4 upgrade this phase
    - `frontend/gui/` is not created yet (Phase 12); the root `package.json` workspaces list only `shared` and `cli` for the same reason Phase 0 created only `db/`/`events/` under `backend/src/awf/` - no empty stubs for a later phase's module

- Timestamp: 2026-08-02 15:58
  - Host class(es): Linux/WSL AMD64
  - Summary: Completed Phase 10 (AWF core CLI + protocol) of the AWF build sequence — the unified `awf` command wrapping every operation built in Phases 0-9, and the `awf serve --stdio` JSON-RPC 2.0 endpoint over the same operations.
  - Scope:
    - `backend/src/awf/cli/{__init__.py,core_ops.py,main.py}` (new - `core_ops` holds every operation; `main.py` is the argparse dispatcher)
    - `backend/src/awf/server/{__init__.py,stdio.py}` (new - JSON-RPC 2.0 over stdio, exhaustive Section 16.3 method surface delegating to `core_ops`)
    - `backend/src/awf/workflow/engine.py` (bug fix: `step_id` is now scoped by `run_id` - `f"{run_id}:{node_id}#{attempt}"` - since `step_id` is a global PRIMARY KEY (Section 8) and the prior per-node scheme collided across separate Runs of the same workflow; every prior phase's demo used a fresh scratch db, so this never surfaced until Phase 10 ran multiple real Runs against the persistent real repo db)
    - `config/app_registry/workflows/produce-gate-repair-demo/1.0.0.yaml` (added `checkCommand` to the gate node so a generic, workflow-agnostic CLI/server can execute the check without hand-wired Python, per Phase 7/8's demo-only `check_fn`)
    - `backend/pyproject.toml` (registered the `awf` console script)
    - `backend/tests/test_phase10_{core_ops,server_stdio,cli_main}.py` (new, 25 tests)
  - Validation:
    - `pytest backend/tests/` → 146 passed (121 prior + 25 new)
    - Real end-to-end run against the actual repo's `data/awf_db/awf.db` via the installed `awf` binary: `awf run produce-gate-repair-demo@1.0.0` (produce → gate fail → repair → gate pass, `SUCCEEDED`), `awf status <run-id>` (all 4 real Steps), `awf artifacts <run-id>` (2 real Verdict + 2 real Finding artifacts), `awf resume` (empty - nothing incomplete), `awf registry validate` (the real workflow file), `awf registry publish` (a capability-record fixture, written to `data/registry/capabilities/read_file/1.0.0.yaml` and indexed in `registry_index` - `registry_index`'s first real row since Phase 0 created the table), `awf secret set`/`list` (real Fernet-encrypted secret), and manually-seeded `approvals` rows exercised via `awf approvals`/`approve`/`reject`
    - `awf serve --stdio` driven by a real scripted client over a genuine subprocess pipe (not in-process): `awf/run.start` (hit one transient "model at capacity" failure from Codex on the first attempt - a real upstream hiccup, not a bug, resolved by retrying), `awf/run.status`, and `awf/approval.approve` (against a freshly-seeded pending approval) all returned correct JSON-RPC results. All demo worktrees/branches removed afterward (`git worktree list`/`git branch --list "awf/*"` show none left); `git status` shows only real source changes, since all demo state (`data/`, `.env`) is gitignored
  - Notes:
    - `awf secret set/list/rotate-key` delegates directly to Phase 2's `awf.secrets.cli.run(argv, repo_root)`, as that phase's own notes anticipated
    - `registry publish` supports only Workflow and Capability Record objects (self-describing `name`/`version` in their own content); Model Profiles and Skills have no such self-description in their file content (identity comes from the file's path, Section 9.3/11) and are out of scope for this generic publish path
    - `awf/events.subscribe` is listed in the method surface but returns a method-not-found-shaped error: it is a server-push stream in the spec, which a line-based request/response transport cannot express. Full ACP shaping (sessions, streamed content blocks, the official SDK) remains later work.
    - The `approval` workflow node type still has no execution semantics (unchanged from Phase 7's scope note) - `awf approvals`/`approve`/`reject` are real, working CRUD over the `approvals` table, validated here against manually-seeded rows rather than ones a real node produced

- Timestamp: 2026-08-02 13:44
  - Host class(es): Linux/WSL AMD64
  - Summary: Completed Phase 9 (Handoff pattern) of the AWF build sequence — the `handoff` node's execution semantics wired into the workflow engine, and a real bounded 2-hop producer↔reviewer loop validated on both the success path and the `maxHops` path.
  - Scope:
    - `backend/src/awf/workflow/handoff.py` (new — `make_handoff_node_executor`)
    - `backend/src/awf/workflow/nodes.py` (`handoff`'s required fields extended from just `maxHops` to Section 13.4's full "MUST declare" list: `initiatingAgent`, `receivingAgent`, `payloadSchema`, `maxHops`)
    - `backend/src/awf/workflow/engine.py` (`handoff` added to `EXECUTABLE_NODE_TYPES`; a new `SELF_STEPPING_NODE_TYPES` concept so the engine doesn't create a redundant outer Step for a node that manages its own per-hop Steps; any node executor can now return `{"waiting_input": True, ...}` to pause a Run without silently continuing)
    - `config/app_registry/workflows/producer-reviewer-handoff-demo/1.0.0.yaml` (new - the example handoff workflow, repo-default per 9.3)
    - `backend/tests/test_phase9_handoff.py` (new, 6 tests)
    - `backend/tests/test_phase7_workflow_{nodes,engine}.py` (updated: the Phase 7 handoff fixture now carries the newly-required fields; the "non-executable node type" test switched from `handoff` - now executable - to `approval`, which still has no execution semantics)
  - Validation:
    - `pytest backend/tests/` → 121 passed (115 prior + 6 new)
    - Real end-to-end success path: the published example workflow ran in a dedicated worktree - Claude Code (initiating) wrote a three-line haiku to `haiku.txt`; Codex (receiving, a different adapter) reviewed it, confirmed the line count, and set `handoff_complete: true` on hop 1. Run reached `SUCCEEDED`; `git log` in the worktree showed the one `handoff: draft_and_review hop 1` commit
    - Real end-to-end `maxHops` path: a second, adversarial workflow (`maxHops: 2`, both roles explicitly instructed to always report incomplete) ran both hops for real against Claude Code and Codex, never set `handoff_complete`, and the Run moved to `WAITING_INPUT` (not `FAILED`, not silently continuing) with `hops_used: 2`; two `handoff: ... hop N` commits confirmed each hop was a real, separate durable Step. Both worktrees/branches removed afterward with no residue
  - Notes:
    - The termination condition and inter-hop payload are structured artifacts, not parsed agent prose: each hop's agent is instructed to write a JSON status file (`handoff_status.json` by default) containing `{"<terminationField>": bool, "summary": str}`; the engine reads that file deterministically. `HandoffError` is raised if an agent completes without writing it.
    - The first live attempt at the `maxHops` demo used a neutral objective ("append one line") and completed in 1 hop instead of exhausting - the agent reasonably judged its trivial task done and set `handoff_complete: true`. This is expected agent behavior, not a bug: the retry made the "always report incomplete" instruction explicit to deterministically exercise the exhaustion path, same as Phase 7/8's approach of using unambiguous objectives for repeatable validation.
    - Handoff is locally-invoked adapters only (Section 13.4); the A2A remote-agent extension point is out of scope
    - `payloadSchema` is parsed and required but not enforced against the actual JSON status file's shape - no JSON Schema validator is wired in yet, consistent with Phase 7's `inputSchema`/`outputSchema` note

- Timestamp: 2026-08-02 13:31
  - Host class(es): Linux/WSL AMD64
  - Summary: Completed Phase 8 (Verification & acceptance gate) of the AWF build sequence — Finding/Verdict schema, deterministic Verdict aggregation, the Verifier and Adversary/Optimizer role obligations, a GPU-utilization sampler, and a Trifecta gate node executor wired into Phase 7's bounded repair loop.
  - Scope:
    - `backend/src/awf/gates/{__init__.py,schema.py,verdict.py,artifacts.py,verifier.py,adversary.py,gate_node.py}` (new)
    - `backend/src/awf/hardware/{__init__.py,gpu_sampler.py}` (new)
    - `backend/src/awf/workflow/engine.py` (gate handling now carries `verdict_artifact_id` through to the final result, and a `terminal_failure` output flag - e.g. a `safety_gate_bypass` Finding - fails the Run immediately without consuming a repair-budget iteration)
    - `backend/tests/test_phase7_workflow_engine.py` (updated 3 assertions for the new `verdict_artifact_id` key in the engine's return value)
    - `backend/tests/test_phase8_{gates_schema,gates_artifacts,gates_verifier_adversary,gpu_sampler,gate_node}.py` (new, 29 tests)
  - Validation:
    - `pytest backend/tests/` → 115 passed (86 prior + 29 new)
    - Real end-to-end run of the Phase 7 example workflow with the placeholder gate replaced by `make_trifecta_gate_executor`, in a dedicated worktree: `produce` (Claude Code) wrote the buggy `calc.py`; `check` ran the Verifier's deterministic regression check, which failed, and persisted a real Verdict artifact (`passed: false`) plus a `high`-severity Finding; `repair` (Codex - a different adapter) fixed the bug; `check` re-ran, passed, and persisted a second Verdict (`passed: true`) with a `low`-severity Finding. Both Verdict/Finding artifacts were read back from their content-addressed files and printed in full. Worktree/branch and scratch db/artifacts root removed afterward with no residue in the repo
    - `nvidia-smi` is present on this host (WSL2/NVIDIA), so `sample_gpu_utilization()` was exercised against a real GPU reading in addition to its unit tests
  - Notes:
    - Findings/Verdicts are persisted as `artifacts` rows (`artifact_type`: `finding`/`verdict`, Section 8's existing enum) at content-addressed paths under an `artifacts_root` - Section 7's `data/artifacts/`. The demo used a scratch root under `/tmp`, matching every prior phase's demo-vs-real-repo-state convention (e.g. Phase 4's crash-recovery db); nothing was written to the real `data/artifacts/`
    - The Verifier role here is deterministic test-execution only ("runs regression tests ... produces structured Finding records"); an LLM-driven independent code-review pass remains later work.
    - Only the default tier (Builder + Verifier) was exercised live, per Section 12.3 ("Default tier ... Adversary/Optimizer pass is omitted") - the high-risk tier's three Adversary obligations (resource safety via the GPU sampler, safety-gate bypass, memory contamination) are implemented and unit-tested, including the `safety_gate_bypass` terminal-failure path (fails immediately, does not consume a repair iteration), but weren't run against a real Trifecta invocation since nothing in the example workflow currently trips the Section 12.2 high-risk trigger list
    - `inputSchema`/`outputSchema` enforcement and the full Section 12.2 high-risk trigger-list wiring (auto-escalating a Run to the high-risk tier) remain open - out of this phase's stated scope

- Timestamp: 2026-08-02 13:10
  - Host class(es): Linux/WSL AMD64
  - Summary: Completed Phase 7 (Workflow engine) of the AWF build sequence — the Workflow Definition contract, all eight Section 12.2 node type shapes, a data-driven engine for `activity`/`agent`/`gate` nodes, and one worked example workflow (produce → gate → repair) run end to end against two different named adapters.
  - Scope:
    - `backend/src/awf/workflow/{__init__.py,nodes.py,definition.py,engine.py}` (new)
    - `backend/src/awf/isolation/worktree.py` (`commit_all_changes` now returns `None` instead of raising when a node made no changes to commit)
    - `config/app_registry/workflows/produce-gate-repair-demo/1.0.0.yaml` (new — the example workflow, repo-default per 9.3)
    - `backend/tests/test_phase7_workflow_{nodes,definition,engine}.py` (new, 19 tests)
  - Validation:
    - `pytest backend/tests/` → 86 passed (67 prior + 19 new)
    - Real end-to-end run of the published example workflow in a dedicated worktree: `produce` (Claude Code adapter) wrote a deliberately buggy `calc.py` (`add` returning `a - b`); `check` (gate) ran a real subprocess assertion and failed; `repair` (Codex adapter - a different adapter from `produce`) fixed the bug; `check` re-ran and passed. Run reached `SUCCEEDED` with `repairs_used: 1`; `git log` in the worktree showed exactly two commits (`workflow: produce`, `workflow: repair` - no commit for the passing gate, which changed nothing); worktree/branch removed afterward with no residue
  - Notes:
    - Branching (`next`, and `onFail` on `gate` nodes) is an engine-specific convention layered on top of the node shape, not part of the Section 12.1 spec fields - documented as such in `workflow/engine.py`'s module docstring, to avoid the fields being mistaken for a spec requirement
    - Only `activity`, `agent`, and `gate` are executable; `approval`, `subworkflow`, `map`, `loop`, and `handoff` validate correctly as node shapes (`workflow/nodes.py`) but raise `WorkflowEngineError` if the engine actually reaches one - `handoff` is Phase 9's job, full Trifecta `gate` tiering (Finding/Verdict, Adversary role) is Phase 8's; this phase's `gate` is a placeholder pass/fail check, not the tiered Eval Suite
    - `inputSchema`/`outputSchema` are parsed and stored but not enforced against actual input/output values - no JSON Schema validator is wired in yet
    - The example workflow's `metadata.digest` was computed manually (sha256 over the file with the digest field blanked) since registry publish/digest tooling doesn't exist yet (flagged since Phase 1); no code depends on or verifies this digest yet

- Timestamp: 2026-08-02 12:47
  - Host class(es): Linux/WSL AMD64
  - Summary: Completed Phase 6 (Remaining named adapters) of the AWF build sequence for 3 of the 4 listed adapters — Codex CLI, Antigravity CLI, and GitHub Copilot CLI, all live-validated. Cline CLI remained blocked by a CLI limitation.
  - Scope:
    - `backend/src/awf/adapters/{codex_cli.py,antigravity_cli.py,copilot_cli.py}` (new)
    - `backend/tests/test_phase6_{codex_adapter,antigravity_adapter,copilot_adapter}.py` (new, 12 tests)
    - `~/.gemini/antigravity-cli/settings.json` (operator-global, outside the repo) - added `permissions.allow: ["write_file(*)"]`, required for `agy` to write non-interactively at all (see Notes)
  - Validation:
    - `pytest backend/tests/` → 67 passed (55 prior + 12 new)
    - Codex CLI: real end-to-end run via `run_agent_step` in a dedicated worktree - `codex exec` (sandbox_mode `workspace-write`, approval_policy `on-request`) created a file, Step reached `SUCCEEDED` before the commit, worktree/branch removed afterward with no residue
    - Antigravity CLI: real end-to-end run via `run_agent_step` in a dedicated worktree - `agy --print` (`--mode accept-edits --sandbox`) created a file, Step reached `SUCCEEDED` before the commit, worktree/branch removed afterward with no residue
    - Copilot CLI: real end-to-end run via `run_agent_step` in a dedicated worktree, once the user completed Copilot login - `copilot -p ... --allow-tool write` (no yolo) created a file, Step reached `SUCCEEDED` before the commit, worktree/branch removed afterward with no residue
  - Notes:
    - **GitHub Copilot CLI** was not installed at session start; installed via `npm install -g @github/copilot` (v1.0.77) with the user's approval. Live validation was initially blocked on a Copilot-licensed token (the environment's `gh` v2.4.0 predates `gh auth token`, and no `COPILOT_GITHUB_TOKEN`/`GH_TOKEN` was set); the user completed `copilot`'s own interactive `/login` device-code flow, after which `--allow-tool` worked non-interactively with no yolo. The adapter's event-schema handling (`_final_assistant_message`) and its docstring were updated to match the real JSONL shape (`session.*`/`assistant.*` events, terminated by one `result` event with `exitCode` and `usage.codeChanges.filesModified`) confirmed against this live session.
    - **Antigravity CLI (`agy`)** has a permission-grant system independent of `--mode`/`--sandbox`/`trustedWorkspaces`: every headless `write_file` call is auto-denied by default (`toolPermission=request-review`), and the top-level JSON still reports `"status":"SUCCESS"` with an empty `response` even when the write was denied - the adapter cannot trust that field alone (documented in the module). Fixed by adding `permissions.allow: ["write_file(*)"]` to the operator's global `~/.gemini/antigravity-cli/settings.json` (the exact literal token `write_file(*)`, confirmed via the CLI binary's own embedded strings; a path-scoped glob like `write_file(<repo>/**)` was tried first and did not match). This is a global, not per-repo, grant - narrower path-scoped matching was not found working and is a follow-up if `agy` sees broader use.
    - **Cline CLI** was not implemented in this phase: `man cline` confirms `-y`/`--no-interactive`/`--yolo` are three aliases for the single fully-autonomous mode in the installed version - there is no CLI-level way to run non-interactively without full yolo, which the spec's Section 10.2 table forbids for AWF's default profile. Cline remained blocked by a vendor-CLI limitation (Section 10.2's caution: flags/config surfaces change per vendor release).
    - Phase 6's exit condition ("each adapter passes the same synthetic task the reference adapter passed in Phase 5") is met for Codex, Antigravity, and Copilot

- Timestamp: 2026-08-01 16:39
  - Host class(es): Linux/WSL AMD64
  - Summary: Completed Phase 5 (Isolation + first reference adapter) of the AWF build sequence — Git worktree manager, `cache/sandbox/<run_id>/` lifecycle, the generic Agent Runtime Adapter contract, and the Claude Code reference adapter.
  - Scope:
    - `backend/src/awf/isolation/{__init__.py,worktree.py,scratch.py}` (new)
    - `backend/src/awf/adapters/{__init__.py,base.py,claude_code.py}` (new)
    - `backend/src/awf/engine/agent_step.py` (new — `run_agent_step`: commits the worktree only after the Step's `SUCCEEDED` status is persisted)
    - `backend/tests/test_phase5_{isolation,claude_code_adapter,agent_step}.py` (new, 12 tests)
  - Validation:
    - `pytest backend/tests/` → 55 passed (43 prior + 12 new)
    - Against the real repo: created a dedicated worktree at `cache/worktrees/phase5-live-demo` on branch `awf/run/phase5-live-demo`, drove the real `claude` CLI (non-interactive, `--permission-mode acceptEdits`, no bypass flag) through `run_agent_step` to create `PHASE5_DEMO.md`, confirmed via a monkeypatch-free live run that the Step reached `SUCCEEDED` before the commit was made (`output.commit_sha` returned, `git log` in the worktree showed the commit), then removed the worktree and branch - `git worktree list`/`git branch --list "awf/*"` confirm no residue in the main repo
    - Unit tests verify the adapter never emits `--dangerously-skip-permissions`/`bypassPermissions`, maps `is_error`→`FAILED`/`COMPLETED` correctly, and that `run_agent_step` raises without committing when the adapter's status isn't `COMPLETED` (a spy on `commit_all_changes` confirms it's never called)
  - Notes:
    - Only Claude Code is implemented per Phase 5's scope ("one fully working named adapter"); Codex CLI, Antigravity CLI, Copilot CLI, and Cline CLI are Phase 6
    - No Workflow Definition contract or Gate node exists yet (Phase 7/8) - `run_agent_step` is invoked directly by the caller with an explicit `AgentInvocation`, not resolved from a workflow YAML's `agent` node
    - The optional Podman container escalation tier (Section 10.4) is out of scope; only the default isolation tier (worktree + scratch dir + adapter's own permission system) is built

- Timestamp: 2026-08-01 16:31
  - Host class(es): Linux/WSL AMD64
  - Summary: Completed Phase 4 (Durable execution core) of the AWF build sequence — Run/Step execution with the Section 13.2 durability rule, and the startup recovery scan.
  - Scope:
    - `backend/src/awf/engine/{__init__.py,run.py,executor.py,recovery.py}` (new)
    - `backend/tests/fixtures/engine/crash_runner.py` (new — standalone subprocess script)
    - `backend/tests/test_phase4_durable_execution.py` (new, 4 tests)
  - Validation:
    - `pytest backend/tests/` → 43 passed (39 prior + 4 new)
    - Genuine mid-Run crash test: a real subprocess creates a Run + two Steps, Step 1 succeeds and persists (bumping a counter file), then Step 2 calls `os._exit(137)` - a real, uncatchable process kill, not a simulated exception. A second, separate subprocess then calls `scan_incomplete_runs`, finds the Run, and calls `run_workflow` again with the same ordered Step list: Step 1 is skipped (`run_step` sees `SUCCEEDED` and never re-invokes its function - counter file stays at `1`), Step 2 re-runs and completes, and the Run reaches `SUCCEEDED`
  - Notes:
    - No Workflow Definition contract exists yet (Section 12, Phase 7) - the ordered Step list is supplied directly by the caller for this phase's synthetic two-step case, matching Phase 4's stated dependency (Phase 0 only, not Phase 7)
    - `scan_incomplete_runs` only lists Run IDs; actually resuming still requires the caller to supply the same deterministic Step list, per the durability rule's premise that node-selection logic is deterministic given inputs and completed Steps - a real resume-and-replay-from-definition path is Phase 7+ work
    - Retry/backoff for `TRANSIENT`/`TIMEOUT` failure classes (Section 13.3) remains open; `run_step` currently has no failure-class handling because the exit condition only requires surviving a hard kill, not a soft retryable failure.

- Timestamp: 2026-08-01 16:08
  - Host class(es): Linux/WSL AMD64
  - Summary: Completed Phase 3 (Model Gateway) of the AWF build sequence — LiteLLM in-process integration, the Model Profile contract, and one working profile validated end-to-end against a local Ollama endpoint.
  - Scope:
    - `backend/src/awf/registry/model_profile.py` (new — `ModelProfile`/`Candidate`/`Privacy`/`Fallback`/`Limits`, `parse_model_profile`, `load_model_profile`)
    - `backend/src/awf/gateway/{__init__.py,client.py}` (new — `complete()`: priority-ordered candidates, secrets-store API-key resolution by name, ordered/none fallback)
    - `backend/tests/fixtures/model_profiles/local_ollama_r0.yaml`
    - `backend/tests/test_phase3_model_gateway.py` (new, 8 tests)
    - `data/registry/model-profiles/phi4-mini/1.0.0.yaml` (first real, published Model Profile)
    - `backend/pyproject.toml` (added `litellm`)
  - Validation:
    - `pytest backend/tests/` → 39 passed (31 prior + 8 new)
    - Against the real repo: `resolve_registry_object(repo_root, "model-profiles", "phi4-mini", "1.0.0")` located the published profile under `data/registry/`, `load_model_profile` parsed it, and `gateway.client.complete()` returned `"pong"` from a real completion call to `ollama/phi4-mini:latest` at `http://172.31.96.1:11434` (Ollama on the WSL host)
    - Fallback (`ordered` continues to the next candidate, `none` raises immediately) and secrets-store API-key resolution (candidate declares `api_key_secret_name`, value never in the profile file) verified with a monkeypatched `litellm.completion`
  - Notes:
    - The published `phi4-mini` profile requires no `api_key_secret_name` since Ollama needs no auth; the secrets-resolution path is proven by a dedicated test with a real Fernet-encrypted secret, not by the live call
    - Token/cost `limits` are wired only as far as `max_output_tokens_per_call` → LiteLLM's `max_tokens`; input-token and cost-ceiling enforcement are not implemented and remain open for a later pass

- Timestamp: 2026-08-01 15:57
  - Host class(es): Linux/WSL AMD64
  - Summary: Re-aligned Phases 0–1 with the Architect-updated spec's two-root registry model (`config/app_registry/` repo defaults + `data/registry/` operator additions, Section 9.3) — added the `config/app_registry/` layout, updated `registry_index`'s schema, and implemented the dual-root resolution lookup.
  - Scope:
    - `config/app_registry/{agents,capabilities,MCP,skills,voice-profiles,workflows}/.gitkeep` (new repo layout, Phase 0)
    - `backend/src/awf/db/schema.py` (`registry_index`: added `source` enum column `config`|`data`; `trust_status` now nullable, null when `source='config'`)
    - `backend/src/awf/registry/resolve.py` (new — `resolve_registry_object(repo_root, kind, name, version)`, Phase 1)
    - `backend/tests/test_phase1_registry_resolve.py` (new, 6 tests)
  - Validation:
    - `pytest backend/tests/` → 31 passed (25 prior + 6 new)
    - Fresh `backend/.venv` rebuilt from the `python3.12` altinstall; `backend/.venv/bin/awf-setup` re-run against the real repo produced a new `.env` (fresh `AWF_SECRET_KEY`) and `data/awf_db/awf.db` with the updated `registry_index` shape, confirmed via `PRAGMA table_info`
  - Notes:
    - `capability_record.load_capability_record` still takes an explicit `Path` — not yet wired to call `resolve_registry_object`; that integration and populating `registry_index`'s `source`/`trust_status` from a real publish step remain open
    - `.gitignore` required no change: it already fully gitignores `data/registry/*` except `.gitkeep`, matching the updated spec's "operator-personal, untracked" model for `data/`

- Timestamp: 2026-08-01 07:19
  - Host class(es): Linux/WSL AMD64
  - Summary: Completed Phase 2 (Secrets) of the AWF build sequence — Fernet-backed `secrets` table access, key rotation, and the `awf secret set/list/rotate-key` entrypoints.
  - Scope:
    - `backend/src/awf/envfile.py`
    - `backend/src/awf/secrets/{__init__.py,store.py,cli.py}`
    - `backend/tests/test_phase2_secrets.py`
    - `backend/pyproject.toml` (added `cryptography`; registered `awf-secret` console script)
  - Validation:
    - `pytest backend/tests/` → 25 passed (17 prior + 8 new)
    - Against the real repo, across five genuinely separate process invocations of `backend/.venv/bin/awf-secret`/`python -c`: set `demo-key` → list showed only the name → fresh-process read via the secrets-access function returned the original plaintext → `rotate-key` changed `AWF_SECRET_KEY` in `.env` → post-rotation the new key decrypted `demo-key` correctly and the old key raised `cryptography.fernet.InvalidToken`
  - Notes:
    - `awf secret set` prompts via `getpass` rather than taking the value as an argv token, so it never appears in shell history or `ps`
    - No `awf secret get` — Section 16.1 lists only `set`/`list`/`rotate-key`; reads happen through the in-process secrets-access function (`awf.secrets.store.get_secret`), never over a CLI surface
    - `secrets/cli.py` is a standalone console script for this phase, not a stub under `backend/src/awf/cli/` (that module is Section-7-tagged for Phase 10); its `run(argv, repo_root)` is what Phase 10 will wire directly into the unified `awf` command's subparser tree, so this is not throwaway code

- Timestamp: 2026-08-01 07:13
  - Host class(es): Linux/WSL AMD64
  - Summary: Completed Phase 1 (Registry + Capability Guard) of the AWF build sequence — Capability Record load/validate and the Capability Guard authorization function.
  - Scope:
    - `backend/src/awf/registry/{__init__.py,capability_record.py}`
    - `backend/src/awf/guard/{__init__.py,capability_guard.py}`
    - `backend/tests/fixtures/capabilities/{read_file_r0,write_scratch_file_r1,git_push_r2,modify_capability_registry_r3}.yaml`
    - `backend/tests/test_phase1_registry_guard.py`
    - `data/registry/voice-profiles/.gitkeep` (missing Section 7 registry directory added)
    - `.gitignore` (re-include + per-directory ignore rules for `data/registry/voice-profiles/`)
    - `backend/pyproject.toml` (added `PyYAML` — registry files are YAML per Section 9.1/9.3)
  - Validation:
    - `pytest backend/tests/` → 17 passed (7 from Phase 0 + 10 new)
    - Four hand-written Capability Records (one per risk class R0–R3) load, validate, and `evaluate()` returns the correct decision for each: R0 → ALLOW (autoallow), R1 → ALLOW (approval: never), R2 → APPROVAL_REQUIRED, R3 → DENY (prohibited); a not-in-allowlist case also returns DENY
    - `authorize()` confirmed to write a decision row to the `events` table (reason_code `approval_per_invocation`) before the caller would proceed
  - Notes:
    - Scoped to the Section 6 exit condition (Capability Record load/validate + per-risk-class Guard decision); full registry publish/index/digest machinery deferred until a real caller exists (Phase 10 CLI), per Section 6's "complete means the stated exit condition, not every future feature"
    - Hand-written records are test fixtures, not published registry objects — no real Capability Records exist yet because no activities/adapters are implemented (Phase 4+)
    - Flag: the existing `.gitignore` pattern `/data/registry/<kind>/*` + `!.../.gitkeep` will also block real registry YAML files from being tracked once phases start publishing them (e.g. Phase 8's hardware sampler, Phase 5's first adapter) — not fixed here since it affects all registry kinds uniformly and is out of Phase 1's scope; needs a per-kind allowlist rule (e.g. `!/data/registry/capabilities/**/*.yaml`) before Phase 5+ publishes real objects

- Timestamp: 2026-08-01 07:08
  - Host class(es): Linux/WSL AMD64
  - Summary: Completed Phase 0 (Bootstrap) of the AWF build sequence — repo layout, SQLite schema, and `.env` generation for a fresh checkout.
  - Scope:
    - `backend/pyproject.toml`
    - `backend/src/awf/{__init__.py,ids.py,clock.py,setup.py}`
    - `backend/src/awf/db/{__init__.py,schema.py,connection.py,bootstrap.py}`
    - `backend/src/awf/events/{__init__.py,writer.py}`
    - `backend/tests/test_phase0_bootstrap.py`
  - Validation:
    - `python3.12 -m venv backend/.venv` then `pip install -e backend[dev]`; `pytest backend/tests/` → 7 passed
    - `backend/.venv/bin/awf-setup` run against the real repo produced `.env` with a generated `AWF_SECRET_KEY` (no placeholder left) and `data/awf_db/awf.db` containing all 7 Section 8 tables (`runs, steps, events, artifacts, approvals, secrets, registry_index`), confirmed via `sqlite_master` query
  - Notes:
    - Only `backend/src/awf/db/` and `backend/src/awf/events/` created under `src/awf/` per Section 7 — no other module directories added
    - `.env`, `backend/.venv/`, and `data/awf_db/awf.db` are gitignored and untracked, per repo `.gitignore`

- Timestamp: 2026-08-01 06:45
  - Host class(es): Linux/WSL AMD64
  - Summary: Established the project changelog.
  - Scope: project changelog.
  - Validation: changelog file was present with the expected title.
