# ADR-0009: one path vocabulary, registry-sourced voice default, published Capability Records

## Status

Implemented. All three tasks landed together (each still stands alone;
none depended on another for its own correctness).

Acceptance evidence: `pytest backend/tests` -> 415 passed (up from the 394
baseline, same 0 skips); all six `scripts/validate_backend.py` commands
returned exit 0; a repo-wide grep confirms no module under
`backend/src/awf/` assembles `config/app_registry`, `data/registry`,
`config/voice`, `cache/sandbox`, `cache/temp`, or `.env` from path segments
except `awf/paths.py` (this closed two `.env`-assembly sites in
`cli/core_ops.py` and `secrets/cli.py` that this ADR's own file list didn't
name but its acceptance criterion covers); `bf_isabella` appears only in
`config/app_registry/voice-profiles/narrator/1.0.0.yaml` (plus test files
asserting the real shipped value, and the renderer's own
`VoiceActivation.tsx` voice-selector dropdown, which enumerates all four
registered voices rather than restating a default); a live
`awf-speech round-trip` run with no `--voice-id` produced narrator-voice
audio and a run with `--voice-id am_michael` produced genuinely
byte-different audio; `config/app_registry/capabilities/` now holds the six
records, each loading through `load_capability_record`; an `activity` node
run with `repo_root` set records an `ALLOW` Guard decision referencing the
published `hardware_probe@1.0.0` record, and an `activity` node whose
record is forced to `R3` fails the Step with `failure_class ==
POLICY_DENIED`; `frontend/gui` - 29 tests passed, `tsc --strict` clean.

One inconsistency between this ADR's text and the codebase was resolved
before implementation: the `provider` field on `claude_code_invoke`'s
Mechanism example originally read `claude_code` (underscore), but the real
registered adapter/actor key in `core_ops.ADAPTER_REGISTRY` and
`mcp/render.RENDERERS` is `"claude-code"` (hyphen). Confirmed with the
operator; both the example below and the shipped record use `provider:
claude-code`, matching the real actor string per this ADR's own stated rule
("provider matching the adapter key used as actor"). `identity.name`/the
record's file path stay `claude_code_invoke` as originally specified - that
is the registry object's own name, not the actor string, and the two are
allowed to differ.

## Context

**Repo-relative locations are spelled in five modules.** `awf/paths.py` owns
`REPO_ROOT`, `db_path`, and `models_dir`. The remaining locations are built
where they are used: `registry/resolve.py` holds `CONFIG_ROOT =
"config/app_registry"` and `DATA_ROOT = "data/registry"` as strings;
`registry/hardware_voice_manifest.py` builds `repo_root / "config" /
"voice"`; `isolation/scratch.py` builds `repo_root / "cache" / "sandbox"`;
`setup.py` builds `cache/sandbox`, `cache/temp`, and `.env`;
`engine/agent_step.py` builds `repo_root / ".env"`.

**The default voice is a literal in two places.**
`config/app_registry/voice-profiles/narrator/1.0.0.yaml` declares
`voice_id: bf_isabella` and is the registry authority. `speech/cli.py`
declares `--voice-id default="bf_isabella"`;
`frontend/gui/src/main/voicePipeline.ts` declares `options.voiceId ??
"bf_isabella"`. `registry/voice_profile.py` can load and rank the profile's
candidates; nothing calls it to obtain the default.

**Capability Records: none published, and one node type skips the Guard.**
`config/app_registry/capabilities/` contains only `.gitkeep`.

- `agent` nodes always reach the Guard. A node that declares `capability:
  {name, version}` resolves a published record; one that doesn't gets
  `_synthesized_capability_for_node` — a conservative R1 / `update` /
  `approval: never` record — so the decision is still evaluated and written
  to `events`.
- `activity` nodes do not reach the Guard.
  `make_activity_node_executor` looks the function up in
  `ACTIVITY_REGISTRY` and calls it. The registry holds two entries,
  `hardware_probe` and `gpu_utilization_sample`, both read-only probes.
- MCP tools are never invoked by AWF. `engine/agent_step._apply_mcp`
  renders server definitions into the adapter's own config format; the
  adapter connects and calls the tools.

Section 9.1 requires a Capability Record for every callable capability of
type `mcp-tool`, `activity`, or `cli-adapter-action`.

## Decision

**Task A — one path vocabulary.** `awf/paths.py` holds every repo-relative
location the package uses. Modules import from it rather than assembling
path segments.

**Task B — the default voice comes from the registry.** `bf_isabella`
remains the default and every other voice remains selectable. The value is
read from the `narrator` Voice Profile's winning candidate instead of being
restated in Python and TypeScript.

**Task C — published Capability Records, and `activity` nodes through the
Guard.** Records ship for the capabilities AWF can enumerate: the two
registered activities and the four named CLI adapter actions. `activity`
nodes authorize through the same chokepoint `agent` nodes already use, with
the same synthesized-record fallback when no record is published.

## Rationale

Each task removes a second place where one fact is written. The path
literals and the voice default are duplicates kept in agreement by
attention. The Capability Records are the inverse: a fact the spec requires
that no file states, and a node type that reaches its function without the
decision being recorded.

Section 9.1's requirement is met for the capabilities AWF actually invokes.
MCP tools are called by the adapter, not by AWF, so the authorization AWF
can perform is over the adapter action that renders and launches them —
which is where the record sits.

## Deviation recorded

| Requirement | Deviation | Compensating control |
|---|---|---|
| Section 9.1: every callable capability of type `mcp-tool`, `activity`, or `cli-adapter-action` MUST have a Capability Record | records ship for the two registered activities and the four named adapter actions; no record is published per MCP tool | AWF invokes no MCP tool directly — the adapter connects, and the adapter action that renders the server config carries the record. Every authorized invocation writes its decision to `events` regardless of which record applied |
| Section 9.1, read as requiring a published record before any invocation | a node that declares no capability is authorized against a deterministic synthesized R1 / `approval: never` record | the synthesized record is evaluated by the same `evaluate` function and its decision is written to `events` with the same payload shape, so no invocation proceeds unauthorized or unlogged |

## Mechanism

### Task A — `awf/paths.py`

```python
REPO_ROOT: Path

CONFIG_REGISTRY_RELATIVE = "config/app_registry"
DATA_REGISTRY_RELATIVE = "data/registry"

env_path(repo_root) -> Path                  # .env
db_path(repo_root) -> Path                   # data/awf_db/awf.db
models_dir(repo_root, function) -> Path      # models/<function>
config_registry_dir(repo_root) -> Path       # config/app_registry
data_registry_dir(repo_root) -> Path         # data/registry
config_voice_dir(repo_root) -> Path          # config/voice
scratch_dir(repo_root, run_id) -> Path       # cache/sandbox/<run_id>
temp_dir(repo_root) -> Path                  # cache/temp
```

The two relative strings stay strings because `registry/resolve.py` uses
them in its error messages; the two directory functions derive from them, so
each location is written once.

Callers: `registry/resolve.py` imports the relative constants;
`registry/hardware_voice_manifest.resolve_hardware_voice_manifest_path` uses
`config_voice_dir`; `isolation/scratch.scratch_path` uses `scratch_dir`;
`setup.bootstrap_repo` uses `scratch_dir`, `temp_dir`, and `env_path`;
`engine/agent_step._resolve_secrets` uses `env_path`.

`scripts/validate_backend.py` and `backend/tests/conftest.py` keep deriving
their own root: both must work before the package is importable.

### Task B — voice default from the narrator profile

`registry/voice_profile.py`:

```python
DEFAULT_VOICE_PROFILE_REF = "narrator@1.0.0"

resolve_default_voice_id(repo_root: Path) -> str
```

`resolve_default_voice_id` resolves the ref through `resolve_registry_object`
and returns the first entry of `enabled_candidates_by_priority()`. Because
resolution checks `data/registry/` first, an operator override of `narrator`
changes the default without a code change.

`speech/cli.py` declares `--voice-id` with no default and calls
`resolve_default_voice_id` when the flag is absent, so any `voice_id` the
operator passes is still used unchanged.

`frontend/gui/src/main/voicePipeline.ts` omits `--voice-id` entirely when
`options.voiceId` is unset, letting the Python side supply it. The parameter
stays on `RunVoiceRoundTripOptions` and the IPC handler, so a caller
selecting `am_michael`, `bf_emma`, `bm_george`, or any other Kokoro voice is
unaffected.

Bumping the narrator profile to a new version updates
`DEFAULT_VOICE_PROFILE_REF`.

### Task C — Capability Records and activity authorization

Two activity records under
`config/app_registry/capabilities/<name>/1.0.0.yaml`, matching the registered
function names:

```yaml
identity: {type: activity, provider: awf, name: hardware_probe, version: 1.0.0}
schema: {input: "", output: ""}
effects: {operation: read, reversible: true, idempotent: true, external_side_effect: false}
risk_class: R0
approval: never
```

`gpu_utilization_sample` takes the same shape. Both are read-only probes, so
both are R0 and auto-allow.

Four adapter-action records, one per named adapter present in
`awf/adapters/`, with `provider` matching the adapter key used as `actor`:

```yaml
identity: {type: cli-adapter-action, provider: claude-code, name: claude_code_invoke, version: 1.0.0}
schema: {input: "", output: ""}
effects: {operation: update, reversible: true, idempotent: false, external_side_effect: true}
risk_class: R1
approval: never
```

`codex`, `antigravity`, and `copilot` take the same shape with their own
provider and name. These match what `_synthesized_capability_for_node`
already produces, so publishing them changes no decision — it moves the
record from code into the registry, where a workflow can reference it and an
operator can tighten it.

`make_activity_node_executor` gains repo-root awareness and authorizes before
calling the function:

- resolve `capabilities/<node["function"]>/1.0.0` through
  `resolve_registry_object`;
- when no record is published, synthesize one with `identity.type=activity`,
  `provider="awf"`, `operation="execute"`, `risk_class="R1"`,
  `approval="never"` — the activity counterpart of the existing agent-node
  fallback;
- call `authorize` with `agent_allowlist=[record.ref]`, since an activity
  node has no Agent Manifest. The allowlist check is satisfied by
  construction; the risk-class and approval evaluation and the `events` row
  are what the call produces.
- a decision other than `ALLOW` fails the Step with `POLICY_DENIED`, the same
  posture `run_agent_step` takes.

## Layout delta

```text
config/app_registry/capabilities/
  hardware_probe/1.0.0.yaml            (new)
  gpu_utilization_sample/1.0.0.yaml    (new)
  claude_code_invoke/1.0.0.yaml        (new)
  codex_invoke/1.0.0.yaml              (new)
  antigravity_invoke/1.0.0.yaml        (new)
  copilot_invoke/1.0.0.yaml            (new)

backend/src/awf/
  paths.py                             (Task A: full location set)
  registry/resolve.py                  (Task A: relative constants imported)
  registry/hardware_voice_manifest.py  (Task A: config_voice_dir)
  registry/voice_profile.py            (Task B: resolve_default_voice_id)
  isolation/scratch.py                 (Task A: scratch_dir)
  setup.py                             (Task A: scratch_dir, temp_dir, env_path)
  engine/agent_step.py                 (Task A: env_path)
  speech/cli.py                        (Tasks A, B)
  workflow/engine.py                   (Task C: activity node authorization)

frontend/gui/src/main/voicePipeline.ts (Task B: omit --voice-id when unset)
```

## The tradeoffs accepted

- `paths.py` becomes the module nearly every other module imports. It has no
  imports of its own beyond `pathlib`, so it adds no cycle risk.
- Reading the default voice from the registry means a missing or malformed
  `narrator` profile fails the round trip where a literal would have
  succeeded. The profile is a shipped repository default, and a failure names
  the file.
- Authorizing activity nodes adds an `events` row per activity invocation.
  Both current activities are R0 auto-allow, so the added cost is one insert
  and the added value is a record that the probe ran under authorization.
- Publishing adapter-action records that match the synthesized ones changes
  no current decision. The value is that a workflow can now name one, and an
  operator can raise a risk class without editing Python.

## Scope for implementation

1. Extend `awf/paths.py` with the full location set.
2. Repoint `registry/resolve.py`, `registry/hardware_voice_manifest.py`,
   `isolation/scratch.py`, `setup.py`, `engine/agent_step.py`, and
   `speech/cli.py` at it; remove the assembled path segments.
3. Add `DEFAULT_VOICE_PROFILE_REF` and `resolve_default_voice_id` to
   `registry/voice_profile.py`.
4. Drop the `--voice-id` default in `speech/cli.py`; resolve it when absent.
5. Drop the `?? "bf_isabella"` fallback in `voicePipeline.ts`; omit the flag
   when `voiceId` is unset.
6. Write the six Capability Records.
7. Authorize `activity` nodes in `workflow/engine.make_activity_node_executor`.
8. Tests: path helpers return the expected locations; `resolve_default_voice_id`
   returns `bf_isabella` from the shipped profile and follows a
   `data/registry/` override; an explicit `--voice-id` is passed through
   unchanged; each of the six records loads and validates; an activity node
   writes a Guard decision event before its function runs; an activity whose
   record is R3 fails the Step with `POLICY_DENIED`.
9. Run all six `scripts/validate_backend.py` commands.

## Acceptance

- No module under `backend/src/awf/` assembles `config/app_registry`,
  `data/registry`, `config/voice`, `cache/sandbox`, `cache/temp`, or `.env`
  from path segments except `awf/paths.py`.
- `bf_isabella` appears in `config/app_registry/voice-profiles/narrator/1.0.0.yaml`
  and nowhere else in the repository.
- A voice round trip with no `--voice-id` speaks in the narrator voice; one
  with `--voice-id am_michael` speaks in that voice.
- An operator `narrator` profile under `data/registry/voice-profiles/`
  changes the default with no code change.
- `config/app_registry/capabilities/` holds six records, each loading through
  `load_capability_record`.
- Running the example workflow produces one Guard decision event per
  `activity` node execution, and `hardware_probe` resolves to its published
  R0 record rather than a synthesized one.
- `pytest backend/tests` matches or exceeds the pre-change pass count with
  the same or fewer skips.

## Consequences

- One module answers where anything lives in the repository.
- The narrator Voice Profile is the only place the default voice is stated,
  and an operator override reaches both frontends.
- Every node type that invokes something passes the Capability Guard, so
  the `events` table records an authorization decision for each.
- `config/app_registry/capabilities/` stops being an empty directory and
  becomes the place a risk class is raised.