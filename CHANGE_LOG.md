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
