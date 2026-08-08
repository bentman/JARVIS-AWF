# ADR-0013: add the Cline CLI adapter

## Status

Proposed. Adds the fifth of the five named CLI adapters called out in
`README.md` §Status ("one of the five named CLI adapters … is
outstanding"). The adapter contract (Section 10.1) and its single
wiring point `ADAPTER_REGISTRY` (`cli/core_ops.py`) already exist and are
adapter-agnostic; this record proposes a Cline adapter that mirrors the
other four in shape, pattern, and functionality. No source-of-truth
conflict. No code is implemented by this record.

## Context

Section 10 names five CLI coding agents "driven through one adapter
contract." Four are implemented and registered:

```python
ADAPTER_REGISTRY = {                      # cli/core_ops.py:57
    "claude-code": claude_code_invoke,     # adapters/claude_code.py
    "codex":       codex_invoke,           # adapters/codex_cli.py
    "antigravity": antigravity_invoke,     # adapters/antigravity_cli.py
    "copilot":     copilot_invoke,         # adapters/copilot_cli.py
}
```

The fifth — **Cline** (npm package `@cline/cli`, command `cline`) — is the
outstanding one. Cline is a first-class, widely-used autonomous coding
agent with a non-interactive CLI and JSON streaming, so it fills the
same slot the other four occupy; it is not a new capability class.
Cline's presence on a host is a runtime/install fact (`awf-setup` /
operator install), never an import-time assumption: the adapter must not
import or probe Cline at module load.

The contract needs no new shapes. `AgentInvocation.constraints` already
carries the three degrees of freedom every adapter consumes —
`model_override`, `timeout_seconds`, `mcp_extra_args`/`mcp_env_overlay`/
`skill_env_overlay` — plus the per-adapter approval/sandbox knobs. Cline
maps onto these identically. The four adapters also share one discipline
each adapters must mirror:

  - **model provider**: three of the four (`claude_code`, `copilot_cli`,
    `antigravity_cli`) ignore `model_override_provider` and pass only
    `model_override` as their model flag; only `codex_cli` special-cases
    `ollama`. Cline's `-m/--model` likewise takes the model id, so the
    Cline adapter passes `-m <model>` and does not invent a provider
    mapping (ADR-0005's provider-id reconciliation is a separate,
    cross-cutting concern, out of scope here).
  - **model override flag**: `constraints["model_override"]`, when set,
    is appended as the provider's model flag (`-m` for Cline, same as the
    `-m` the model-profile path sets in `agent_step._apply_model_profile`).
  - **timeout**: enforced by `subprocess.run(timeout=...)`; no adapter
    passes a CLI timeout flag.
  - **danger flags**: each adapter refuses its most-permissive mode
    unless an explicit container/VM escalation is present — codex refuses
    `sandbox_mode="danger-full-access"`, claude refuses
    `permission_mode="bypassPermissions"`, copilot refuses
    `allow_all`/`yolo`, antigravity refuses
    `dangerously_skip_permissions`.

## Mechanism

Cline's non-interactive, machine-readable invocation (verified against
upstream `apps/cli/src/commands/program.ts` + `apps/cli/README.md`):

```
cline "<objective>" --json --auto-approve true --cwd <workspace>
        [-m <model>]
```

Flag mapping (authoritative, from `apps/cli/src/commands/program.ts`):

  - `<objective>` — a **positional** argument (`.argument("[prompt]")`),
    joined with spaces; passed as a single argv element, so newlines and
    spaces in the objective survive without shell quoting.
  - `--json` — sets `outputMode: "json"`; Cline then streams **NDJSON**
    events ("`cline --json \"...\"` streams NDJSON events for piping into
    other tools"). Mirrors codex `--json` / copilot `--output-format json`.
  - `--auto-approve true` — tool calls are auto-approved by default; AWF
    passes it explicitly so a non-TTY subprocess never blocks on an
    approval prompt. `--auto-approve false` would make required-approval
    calls **denied** in a non-TTY subprocess (verbatim from the upstream
    Tool Approval docs: "If stdin/stdout is not a TTY, required-approval
    calls are denied in terminal mode") — i.e. `--yolo` is *not* the
    safety surface here, explicit auto-approve is.
  - `--cwd <path>` — binds the task to the Run's worktree
    (`invocation.workspace_root`), matching every adapter's `cwd=`.
  - `-m, --model <model-id>` — receives `model_override`.
  - Cline reads MCP config from `~/.cline/mcp.json` (default `--config`
    dir, under `$HOME`) and state from `~/.cline/data` (default
    `--data-dir`). With the `HOME` throwaway override that
    `engine.agent_step._apply_mcp` already sets for Antigravity
    (`scratch_path(repo_root, run_id)/"agy_home"/actor`), `--config` is
    not needed: Cline's `~/.cline` resolves under the isolated scratch
    `HOME`, exactly as Antigravity reads `~/.gemini/...` under the same
    scratch `HOME`.

So the adapter reuses the existing isolation machinery verbatim
(`render_*` -> `home_relative_files` + `env_overlay["HOME"]`) instead of
adding per-adapter CLI flags — same shape as `render_antigravity`.

JSON parsing contract: Cline's `--json` NDJSON event surface (verified
against `sdk/packages/core/src/services/agent-events.ts`) carries event
`type`s such as `content_start` (`contentType: "tool"`), `content_end`
(`error` when a tool fails), `usage` (`inputTokens`/`outputTokens`/
`cacheWriteTokens`/`cacheReadTokens`/`cost`), and `iteration_end`. The
adapter mirrors `copilot_cli`'s exit-code-primary posture verbatim —
"Success/failure is determined primarily by the process exit code, not
event contents" — so a non-zero `returncode` is `AgentStatus.FAILED`
(`termination_reason=f"exit code {returncode}"`), zero is
`AgentStatus.COMPLETED`, `TimeoutExpired` is `LIMIT_EXCEEDED`, and the
NDJSON stream is parsed for a best-effort final assistant message and
`usage` and carried through in the `AgentResult` envelope. The exact
event-type strings are pinned against observed `cline --json` output at
implementation; the adapter never fabricates a schema it cannot parse.

Command built by `invoke`:

```python
command = [
    "cline", invocation.objective,
    "--json",
    "--auto-approve", "true",
    "--cwd", str(invocation.workspace_root),
]
if invocation.constraints.get("model_override"):
    command += ["-m", invocation.constraints["model_override"]]
command += list(invocation.constraints.get("mcp_extra_args", []))
```

`subprocess.run(command, cwd=invocation.workspace_root,
capture_output=True, text=True, timeout=timeout_seconds,
stdin=subprocess.DEVNULL,
env={**os.environ, **mcp_env_overlay})` — identical to `copilot_cli`/`antigravity_cli`.

## Scope for implementation

1. `backend/src/awf/adapters/cline_cli.py` — new module, mirror
   `copilot_cli.py`'s shape: `ClineAdapterError(RuntimeError)`,
   `DEFAULT_TIMEOUT_SECONDS = 300`,
   `FORBIDDEN_CONSTRAINT_KEYS = ("yolo", "dangerously_skip_permissions")`,
   `def invoke(invocation) -> AgentResult`. No committed profile file
   (unlike Codex). Reuses `awf.adapters.base` envelopes only.
2. `backend/src/awf/cli/core_ops.py` — two lines:
   `from awf.adapters.cline_cli import invoke as cline_invoke` and add
   `"cline": cline_invoke` to `ADAPTER_REGISTRY`. This is the single
   wiring point for both `make_agent_node_executor` and
   `make_handoff_node_executor`.
3. `backend/src/awf/mcp/render.py` — add `render_cline`
   (writes `.cline/mcp.json` as `{"mcpServers": ...}`, secrets referenced
   as `${AWF_MCP_<NAME>_<KEY>}` and resolved via `_env_overlay_for`, same
   as `render_copilot`/`render_antigravity`) and add
   `"cline": render_cline` to `RENDERERS`. No per-invocation config flag
   is needed — Cline follows the throwaway `HOME` that `_apply_mcp`
   already injects.
4. `config/app_registry/capabilities/cline_invoke/1.0.0.yaml` — mirror
   `codex_invoke/1.0.0.yaml` with `provider: cline`,
   `name: cline_invoke` (same R1 / `approval: never`).

No new agent manifest is required: a manifest opts in later by setting
`adapter: cline` and `capabilities: [cline_invoke@1.0.0]`. Manifests are
out of scope here until a workflow node actually drives Cline (YAGNI).

## Acceptance (to be met when implemented)

- `python -m pytest -q backend/tests/unit/test_phase6_cline_adapter.py`
  passes, mirroring `test_phase6_copilot_adapter.py`:
    builds the non-interactive one-shot command (`cline`, positional
    objective, `--json`, `--auto-approve true`, `--cwd`,
    `--config`-free — isolation via `HOME`); asserts `--yolo` /
    `--dangerously-skip-permissions` are never emitted;
    appends `--model` from `model_override`; maps non-zero exit
    -> `FAILED` (`"exit code N"`); maps successful run -> `COMPLETED`
    with parsed events/usage; maps `TimeoutExpired` ->
    `LIMIT_EXCEEDED`; maps non-JSON stdout -> `FAILED`.
- `python -m pytest -q backend/tests/unit` and
  `python scripts/validate_backend.py ci` remain green (same or higher
  pass count, same or fewer skips) — no four-adapter assumption is
  hard-coded anywhere.
- `ADAPTER_REGISTRY` and `RENDERERS` each have five entries.
- `awf registry validate
  config/app_registry/capabilities/cline_invoke` resolves with no
  `--kind` and reports `provider: cline`.
- A manifest declaring `adapter: cline` is accepted by
  `registry/agent_manifest.parse_agent_manifest` and the engine resolves
  it to the registered `invoke` (verified by the unit test's captured
  command, not by a live Cline install — Cline availability is a runtime
  fact and any live test must `SKIP` when `cline` is absent from `PATH`).

## Consequences

- Any workflow node (and any handoff hop) can target Cline by setting
  `adapter: cline`, identical to opting into codex/claude-code/antigravity/
  copilot. The other four adapters are unchanged.
- A Cline-driven Run never reads or writes the operator's real
  `~/.cline`: `_apply_mcp` sets `HOME` to the run-scoped scratch dir and
  `render_cline` writes `mcp.json` there, mirroring Antigravity.
- The Capability Guard (pre-run) + Git worktree + Gate (post-run)
  remain the authorization, isolation, and verification boundaries;
  Cline's `--auto-approve true` is a per-Run convenience, not a bypass
  of AWF's trust model.
- Risk class R1 + `approval: never`, identical to the other four
  adapters, so the existing guard posture applies unchanged.

## Open decisions

- **Cline API-key / provider auth for headless runs.** AWF's model
  profile wiring (`agent_step._apply_model_profile`) sets
  `model_override`/`model_override_provider` but does not currently
  inject a `api_key_secret_name` into the adapter subprocess env. For a
  Cline-backed manifest that needs a key, `-k <key>` should be sourced
  from the encrypted secret store (ADR-0005) and passed as a
  `constraints["api_key"]` consumed by the adapter — same surface the
  `api_key_secret_name` candidate field already names. Deferred until a
  Cline-backed workflow actually needs headless auth.
- **Provider-id reconciliation.** Cline's `-P` ids
  (`cline`, `openai`, `anthropic`, `openai-codex`, `openrouter`, `google`,
  …) differ from AWF's LiteLLM-style profile `provider` values
  (`llamafile`, `ollama`, `openai`, …). This record deliberately follows
  the three ignore-provider adapters and does not map them; a future ADR
  (ADR-0005 follow-up) can decide whether Cline gets a `provider` flag.
- **Cline's non-interceptable network tools.** Per the spec's Section 10.3
  caveat ("A CLI adapter that cannot intercept its agent's built-in
  network tools ... must run with sandbox network egress disabled and is
  ineligible for … credentialed/external-network workflows"), Cline is
  added to that same rule — a Cline-driven node is ineligible for
  credentialed or external-network workflows until a declared sandbox
  profile disables its network egress. No change to that rule here.
