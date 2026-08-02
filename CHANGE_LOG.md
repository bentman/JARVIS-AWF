# CHANGE_LOG.md
> No edits/reorders/deletes of past entries.
> If an entry is wrong, append a corrective entry in `## Change Appendix`.

## Rules
- Write an entry for codebase change only after objective is complete and supported by evidence.
- Ordering: Entries are maintained in descending chronological order (newest first, oldest last).
- Append location: New entries must be added at the top directly under `## Change Entries`.
- Corrections or clarifications go only below the `## Change Appendix` section.
- Each entry must include:

- Timestamp: `YYYY-MM-DD HH:MM`
  - Host class(es): validated on
  - Summary: description of capability added, 1–2 lines, past tense
  - Scope: exact folders, files, tests, or areas
  - Validation: reproducible evidence
  - Notes: optional constraints or exclusions

---

## Change Entries

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
  - Summary: Completed Phase 6 (Remaining named adapters) of the AWF build sequence for 3 of the 4 listed adapters — Codex CLI, Antigravity CLI, and GitHub Copilot CLI, all live-validated. Cline CLI is not implemented - blocked by a real CLI limitation, not a decision to skip it.
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
    - **Cline CLI** was not implemented at all this phase: `man cline` confirms `-y`/`--no-interactive`/`--yolo` are three aliases for the single fully-autonomous mode in the installed version - there is no CLI-level way to run non-interactively without full yolo, which the spec's Section 10.2 table forbids for AWF's default profile. Per the user's decision, Cline is left unbuilt and flagged here as blocked by a real vendor-CLI limitation (Section 10.2's own caution: flags/config surfaces change per vendor release), not skipped by choice.
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
    - Retry/backoff for `TRANSIENT`/`TIMEOUT` failure classes (Section 13.3) is not implemented - `run_step` currently has no failure-class handling at all, since the exit condition only requires surviving a hard kill, not a soft retryable failure

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
  - Summary: "changelog" established at `CHANGE_LOG.md`
  - Scope:
    - `CHANGE_LOG.md`
  - Validation:
    - `cat CHANGE_LOG.md` output `# CHANGE_LOG.md`...

---

## Change Appendix
