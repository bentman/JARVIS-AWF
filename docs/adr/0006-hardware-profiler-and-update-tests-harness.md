# ADR-0006: canonical Hardware Profiler module, single project file, tiered test suite, and validation harness

## Status

Implemented.

## Context

Two Hardware Profiler modules exist under `backend/src/awf/hardware/`.

`profiler.py` resolves the host to one canonical profile ID from ONNX Runtime
execution-provider probes and writes one `hardware_profile_resolved` event.
It has callers: `speech/pipeline.py` and `workflow/activities.py`.

`hw_profiler.py` exposes the same public names with the same arity —
`CANONICAL_PROFILES`, `SYSTEM_RUN_ID`, `SYSTEM_WORKFLOW_REF`, `_detect_os`,
`_detect_arch`, `_probe_evidence(arch)`, `resolve_hardware_profile_id`,
`run_hardware_profiler` — and adds: per-concern host detectors (OS/device
class, CPU, memory, GPU vendor and VRAM, CUDA driver, NPU vendor) merged into
a fault-isolated inventory under a content-addressed `inventory_id`; QNN
execution-provider registration ahead of the QNN probe; per-platform GPU
execution-provider candidates; an OpenCL platform probe for the arm64 Adreno
path; timeouts on every external command; and a process-lifetime inventory
cache. It has no importer and no test.

Both modules define `CANONICAL_PROFILES`, `SYSTEM_RUN_ID`, and
`SYSTEM_WORKFLOW_REF` independently, so the two copies can diverge.

The behavioral difference that decides the direction: `QNNExecutionProvider`
is absent from `get_available_providers()` until its provider library is
registered and its DLL directory added. A probe reading availability alone
resolves a QNN-capable host to its `*-cpu` floor and records that floor as
the host's verified capability. AGENTS.md's Platform Contract requires every
hardware claim to come from a capability probe or operator-provided command
output.

Project and test configuration state:

- `backend/pyproject.toml` carries packaging metadata: `name = "awf"`,
  dependencies, a `dev` extra, four console scripts (`awf`, `awf-setup`,
  `awf-secret`, `awf-speech`), and `[tool.setuptools.packages.find]
  where = ["src"]`. No `[tool.pytest.ini_options]` block exists anywhere in
  the repository, so there is no marker vocabulary, `--strict-markers` is
  off, and no marker expression can separate deterministic checks from
  host-dependent ones.
- 43 flat `test_*.py` modules under `backend/tests/`; one `conftest.py` whose
  content is a session-wide SQLite `synchronous=OFF` speedup; a `fixtures/`
  tree; a `tests/scripts/` subprocess helper.
- Availability checks are written per module: a module-level
  `pytest.mark.skipif` over four `models/` paths in
  `test_phase12_speech_adapters.py`, an inline `pytest.skip` in
  `test_phase8_gpu_sampler.py`.
- Test modules derive repo-relative paths from their own depth
  (`Path(__file__).resolve().parents[2]`, `parent / "fixtures"`).
- No `scripts/` or `reports/` tree exists. `.gitignore` already carries rules
  for `/reports/{benchmarks,diagnostics,tests,validation}` and `/cache/*`.
- No tracked file names a project-file path or an install command: the
  repository layout names no project file at any level, AGENTS.md specifies
  venv creation only, and `awf/setup.py` derives the repository root from its
  own module path.

AGENTS.md's Validation section requires focused harness targets plus a
cumulative smoke target, `SKIP` with a reason when a provider is unavailable,
and command evidence for any runtime-support claim.

## Decision

`hw_profiler.py` takes the canonical filename. `profiler.py` holds the
evidence-rich implementation; the duplicated constants resolve to one copy;
call sites are unchanged because the contract is unchanged.

One `pyproject.toml` at the repository root carries packaging and pytest
configuration for the whole repository. Packaging content moves unchanged
except for the source root, which becomes `backend/src`.

`backend/tests/` gains three tiers — `unit/`, `integration/`, `runtime/` —
and a marker set in which `live` is an excludable property of a test.
`conftest.py` owns environment and resource availability checks; test modules
consume them as fixtures.

`scripts/validate_backend.py` is the entry point for running checks and for
producing durable evidence. Durable evidence lives under `reports/`; scratch
files live under `cache/validate_backend/`.

The marker set is `live`, `slow`, `runtime`. A capability-specific marker is
added when a test requires it.

## Rationale

The added probe behavior is, by construction, unobservable on a host that has
none of the relevant accelerators — the QNN registration path, the Adreno
OpenCL enumeration, and the per-platform GPU candidates each produce their
distinguishing result only on hardware absent from most development hosts.
The `runtime/` tier and the `live` marker are what let those checks exist in
the tree while every other host skips them with a stated reason, and the
`reports/` artifact is the command evidence AGENTS.md requires, held in a
form a later reader can inspect without having run it.

pytest's rootdir is the directory of its configuration file, and both
`testpaths = ["backend/tests"]` and the repo-relative paths that tests and
helpers resolve require that rootdir to be the repository root. Placing
packaging in the same file keeps the repository at one project file, one
install command, and one home for any later tooling configuration.

The build sequence ends at Phase 12 and these changes sit after it, so the
decision is recorded here rather than against a phase.

## Deviation recorded

The repository layout is definitive and does not list three of the paths this
ADR introduces:

| Path | Nature | Basis |
|---|---|---|
| `scripts/validate_backend.py` | new repo-root directory, one file | AGENTS.md's Validation section requires a harness with focused and cumulative targets; the layout names no home for one |
| `reports/{diagnostics,validation,benchmarks}/` | new repo-root directory | durable command evidence; `.gitignore` already carries rules for these paths |
| root `pyproject.toml` | one project file, replacing `backend/pyproject.toml` | the layout names no project file at any level; consolidating leaves the repository with one unlisted project file rather than two, and puts pytest's rootdir at the repository root |

`backend/tests/{unit,integration,runtime}/` is within the existing layout,
which prescribes no substructure under `backend/tests/`.
`cache/validate_backend/` is ephemeral scratch, which is what `cache/` holds;
`/cache/*` already covers it.

Section 16.4's canonical profile enum, resolution order (QNN/CUDA → GPU →
CPU), `*64-cpu` floor, and probe-verification requirement are carried
unchanged by the module taking the canonical filename.

## Mechanism

### Part A — profiler module

1. **Baseline.** With a clean working tree, record the current suite result:
   `python -m pytest -q backend/tests`. Pass and skip counts are the
   comparison point for every later step.
2. **Back up.**
   `cp backend/src/awf/hardware/profiler.py backend/src/awf/hardware/profiler.py.bak`
   (pwsh: `Copy-Item`). The backup stays untracked: add `*.bak` to
   `.gitignore` in the same change.
3. **Rename.**
   `git mv -f backend/src/awf/hardware/hw_profiler.py backend/src/awf/hardware/profiler.py`.
4. **Verify call sites.** `speech/pipeline.py` and `workflow/activities.py`
   import `from awf.hardware.profiler import ...` and use names the renamed
   module exports. Confirm by inspection, and confirm no module imports
   `hw_profiler` by name.
5. **Reconcile the profiler test module.**
   `backend/tests/test_phase12_hardware_profiler.py` imports
   `CANONICAL_PROFILES`, `SYSTEM_RUN_ID`, `_detect_arch`, `_detect_os`,
   `resolve_hardware_profile_id`, `run_hardware_profiler` and monkeypatches
   `profiler._probe_evidence` and `profiler._detect_arch`. All six names and
   both patch targets exist with matching arity. Add a fixture calling
   `reset_inventory_cache()` around any test that patches a detector, since
   the inventory is cached for the process lifetime.
6. **Cover the added behavior deterministically:** `_normalize_arch` mapping
   across accepted spellings; `_inventory_id` stability for identical input
   and sensitivity to a changed field; a raising detector landing in
   `detector_errors` while the profiler still returns; `collect_inventory`
   caching and `reset_inventory_cache`; `_probe_evidence` carrying
   `available_providers`, `cuda_verified`, `gpu_verified`, `qnn_verified`;
   the resolution ladder over synthesized evidence for every suffix outcome
   on both architectures. Assertions requiring a real accelerator belong in
   `runtime/` under the `live` marker.
7. **Remove the backup** once the suite matches or exceeds the step-1
   baseline and the acceptance evidence exists.

### Part B — single project file

`git mv backend/pyproject.toml pyproject.toml`, then one edit to the
packaging block:

```toml
[tool.setuptools.packages.find]
where = ["backend/src"]
```

`[project]`, `dependencies`, `[project.optional-dependencies]`, and
`[project.scripts]` carry over byte-for-byte; console-script entry points
(`awf.cli.main:main`, `awf.setup:main`, `awf.secrets.cli:main`,
`awf.speech.cli:main`) are module paths and resolve unchanged. The pytest
block below is appended to the same file.

The editable install becomes `pip install -e .[dev]`, run from the repository
root with the venv Python. The venv stays at `backend/.venv` per AGENTS.md.

### Part C — test tiers

| Directory | Holds | Bounded by |
|---|---|---|
| `backend/tests/unit/` | fast, deterministic, single-module tests | passes or fails from repository contents alone |
| `backend/tests/integration/` | multi-module tests over fakes, `tmp_path` state, and in-process SQLite | no live hardware, no external service |
| `backend/tests/runtime/` | checks requiring real services, hardware, devices, credentials, or operator-downloaded models | marked `live`; excluded from the default and CI runs |
| `backend/tests/fixtures/` | shared test data | data only |

`conftest.py` keeps the SQLite speedup and gains the shared fixtures every
tier draws on: `repo_root`, `fixtures_dir`, a models-present check, and an
`nvidia-smi`-present check. A test asks the fixture for an availability
answer.

Path resolution is the constraint governing the move. A module that computes
`parents[2]` resolves to the repository root at `backend/tests/` and to
`backend/` one level deeper; `parent / "fixtures"` resolves only at the
current depth. Every moved module takes `repo_root` and `fixtures_dir` from
`conftest.py`. Fixtures stay at `backend/tests/fixtures/` under the existing
`fixtures/test_phaseN/test_phaseN_<name>` naming, and module filenames are
preserved across the move (`git mv`, no renames).

### Part D — validation harness

`scripts/validate_backend.py`, standard library only (`argparse`,
`datetime`, `pathlib`, `platform`, `subprocess`, `sys`):

| Command | Runs | Writes |
|---|---|---|
| `profile` | environment fingerprint, no tests | `reports/diagnostics/<ts>-profile.txt` |
| `unit` | `python -m pytest -q backend/tests/unit` | — |
| `integration` | `python -m pytest -q backend/tests/integration` | — |
| `runtime` | `python -m pytest -q -m live backend/tests` | — |
| `regression` | the always-safe minimal set, starting at `backend/tests/unit` | `reports/validation/<ts>-regression.txt` |
| `ci` | `python -m pytest -q -m "not live" backend/tests` | — |

Exit codes, shared by every command:

```text
0 = PASS
1 = FAIL
2 = SKIPPED                  (pytest return code 5, no tests collected, maps here)
3 = ENVIRONMENT_UNSATISFIED  (pytest not importable)
```

Timestamps are UTC: `2026-08-04T19:13:00Z` in report content,
`YYYYMMDDHHMMSS-<stem>.txt` for filenames, e.g.
`reports/validation/20260804191300-regression.txt`.

The `regression` report carries, in order: `started_at`, `command`,
`pytest_return_code`, `validator_return_code`, `summary`
(`PASS|FAIL|SKIPPED|ENVIRONMENT_UNSATISFIED`), then verbatim `stdout:` and
`stderr:` blocks.

`profile` writes `os=<...> arch=<...> python=<...>` from `platform` alone, and
adds the canonical profile ID with its probe evidence when
`awf.hardware.profiler` imports successfully. That import happens inside the
command body, so a host without an installed environment still receives the
stdlib fingerprint and exit code `0`; an unimportable `awf` reduces the
fingerprint rather than failing the command.

Pytest configuration, appended to the root `pyproject.toml`:

```toml
[tool.pytest.ini_options]
testpaths = ["backend/tests"]
addopts = ["-ra", "--strict-markers", "--strict-config"]
markers = [
  "live: requires live external resources",
  "slow: longer-running test",
  "runtime: runtime or environment validation",
]
```

## Layout delta

```text
JARVIS-AWF/
  pyproject.toml                          (new - packaging + pytest, replaces backend/pyproject.toml)
  backend/
    src/awf/hardware/
      profiler.py                         (canonical module after the rename)
      gpu_sampler.py
    tests/
      conftest.py                         (SQLite speedup + shared fixtures)
      fixtures/
      unit/                               (new)
      integration/                        (new)
      runtime/                            (new)
      scripts/
  cache/
    validate_backend/                     (new, untracked scratch)
  reports/
    diagnostics/.gitkeep                  (new)
    validation/.gitkeep                   (new)
    benchmarks/.gitkeep                   (new)
  scripts/
    validate_backend.py                   (new)
```

`.gitignore` gains one rule, `*.bak`. The existing `/reports/tests/` rule
stays; that directory is not part of this layout.

## The tradeoffs accepted

- Tier assignment for the existing 43 modules is a judgment applied per
  module under one rule: a test that can fail because of something outside
  this repository belongs in `integration/` or `runtime/`, not `unit/`. A
  module placed in the wrong tier still runs and still reports correctly;
  correcting it is a move.
- `runtime/` checks skip on hosts lacking the resource, so a green `ci` run
  states that the deterministic surface holds and states nothing about the
  QNN, CUDA, or Adreno paths. The `profile` report is what distinguishes a
  skip caused by host capability from an absent check, by recording what the
  host could verify at the time.
- The project file sits one level above the source tree it packages, declared
  by `where = ["backend/src"]`. That placement is what puts pytest's rootdir
  at the repository root, which `testpaths` and repo-relative resolution in
  tests and helpers both depend on.
- The `live` marker makes host-dependent checks excludable, which also makes
  a failing check easy to park behind the marker. `runtime` is run and its
  exit code recorded on hosts that satisfy its resources.

## Scope for implementation

1. Clean working tree; record `python -m pytest -q backend/tests` counts.
2. Back up and rename (Part A, steps 2–3); add `*.bak` to `.gitignore`.
3. Verify call sites and confirm no remaining `hw_profiler` reference.
4. Update `test_phase12_hardware_profiler.py` for the inventory cache; add the
   deterministic coverage in Part A, step 6.
5. `git mv backend/pyproject.toml pyproject.toml`; set
   `where = ["backend/src"]`; append the pytest block; reinstall with
   `pip install -e .[dev]` and confirm the four console scripts resolve.
6. Create `backend/tests/{unit,integration,runtime}/`; extend `conftest.py`
   with `repo_root`, `fixtures_dir`, and the availability helpers.
7. `git mv` each module into its tier; replace every depth-derived path with
   the conftest fixtures.
8. Mark host-dependent tests `live`, move them to `runtime/`, and route their
   skip conditions through the conftest helpers.
9. `scripts/validate_backend.py`: six commands, the exit-code contract, the
   two report writers, `cache/validate_backend/` for scratch.
10. `reports/{diagnostics,validation,benchmarks}/.gitkeep`; remove the backup.
11. Run all six commands and retain their output.

## Acceptance

- `pip install -e .[dev]` from the repository root into a clean venv makes
  `import awf` work and puts `awf`, `awf-setup`, `awf-secret`, and
  `awf-speech` on PATH; `backend/pyproject.toml` no longer exists.
- `python -m pytest -q backend/tests` reports rootdir as the repository root
  and matches or exceeds the step-1 baseline pass count with the same or
  fewer skips.
- `backend/src/awf/hardware/profiler.py` holds the evidence-rich
  implementation, `hw_profiler.py` is gone, no `.bak` file remains, and
  `git status` is clean.
- All six commands run and return a code from the contract.
- `profile` writes one timestamped file under `reports/diagnostics/`
  containing at minimum `os=`, `arch=`, and `python=`.
- `regression` writes one timestamped file under `reports/validation/`
  containing every field listed in Part D.
- `ci` collects zero `live` tests, shown by its own deselection count.
- `runtime` on a host lacking the required resources returns `2`, and every
  skip states a reason.
- With pytest unimportable, a command returns `3` and still writes the report
  its definition names.
- The profile ID in the `profile` report matches the `profile_id` written to
  the `events` table by a real `run_hardware_profiler` call on the same host.

## Consequences

- `CANONICAL_PROFILES`, `SYSTEM_RUN_ID`, and `SYSTEM_WORKFLOW_REF` resolve to
  one definition. `registry/hardware_voice_manifest.py` names
  `hardware/profiler.py::CANONICAL_PROFILES` as the authority and stays
  correct.
- `run_hardware_profiler` carries a keyword-only `refresh` parameter defaulting
  to `False`, and the host inventory is cached per process. Existing
  positional call sites are unaffected; a caller needing a fresh probe
  mid-process passes `refresh=True`.
- `hardware_profile_resolved` payloads carry an `inventory` block and an
  expanded `evidence` block alongside the existing `profile_id` key, which
  keeps existing queries and consumers working.
- The repository has one project file, one install command
  (`pip install -e .[dev]`), and one place for packaging, pytest, and any
  later tooling configuration.
- Validation claims resolve to a `reports/validation/` artifact produced by a
  named command with a recorded exit code.
- Host-dependent tests are excluded from `ci` by marker, so adding one leaves
  every other host's result unchanged.

## Decisions resolved

- **Backup location.** `backend/src/awf/hardware/profiler.py.bak`, with a
  `*.bak` ignore rule; removed once the migrated suite matched the baseline.
- **Migration batching.** All 42 test modules moved into their tier in one
  change.
- **`regression` target set.** `backend/tests/unit` as written.
- **Tier assignment is per module, not per directory.** A module whose tests
  are otherwise deterministic keeps its one environment-gated test marked
  `live` in place, in whichever tier fits the module's dominant subject,
  rather than the whole module moving to `runtime/` for one test. Three
  modules land this way: `test_baseline_hardware_voice_manifest.py`,
  `test_baseline_skill.py` (`unit/`), and `test_phase8_gpu_sampler.py`
  (`unit/`, three of its four tests are fully mocked). `scripts/validate_backend.py`'s
  `runtime` command therefore runs `pytest -q -m live backend/tests` (the
  whole tree, filtered by marker) rather than restricting the path to
  `backend/tests/runtime/`, so it still selects every host-dependent check
  regardless of which tier directory the module sits in.
