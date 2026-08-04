# ADR-0005 (draft): give AgentManifest.model_profile a real consumer

## Status

Proposed. Not implemented. Captured for later - do not build against this
until it is revisited and moved to Accepted.

## Context

`AgentManifest` (ADR-0002) already has a `model_profile` field, parsed from
a manifest's `modelProfile` frontmatter key
(`backend/src/awf/registry/agent_manifest.py:39,85`). Nothing resolves it
and nothing consumes it - the same "schema with no caller" state `mcp` and
`skills` were both in before their own ADRs.

Two mechanisms already exist and already work, independently of each
other:

- The **Model Gateway** (Section 11, `gateway/client.py::complete()`) -
  AWF's own direct LLM calls, purpose-scoped (`general-reasoning`/`coding`/
  `judge`/`adversary`/`embedding`) Model Profiles, LiteLLM underneath. Real
  local candidates are wired and live-verified: `qwen3-8b-local@1.0.0`
  (`data/registry/model-profiles/qwen3-8b-local/1.0.0.yaml`, GPU
  `llama-server` at `127.0.0.1:8080`, `phi4-mini` via Ollama as an ordered
  fallback) and the pre-existing `phi4-mini@1.0.0`. Only one real caller
  exists today: the Verifier's optional LLM-review pass via a gate node's
  `reviewProfile: name@version` field.
- **Each adapter's own model flag** - confirmed real and live-tested, not
  assumed: `claude --model`, `codex exec -m/--model` (plus `--oss
  --local-provider ollama` for routing Codex's own reasoning through a
  fully local backend), `copilot --model`, `agy --model`. This is a
  completely separate path from the Model Gateway - it picks what model
  the *adapter's own agentic loop* runs as, not what AWF itself calls
  directly.

`model_profile` is positioned to be the second path's manifest-level
switch: a manifest names a Model Profile, and the node's adapter gets
launched with that profile's winning candidate's model name.

Separately, the Trifecta's three shipped manifests already diversify
across adapters at the role level - `builder → claude-code`, `verifier →
codex`, `adversary → antigravity` (`config/app_registry/agents/`) - so
role-level flexibility already exists. `model_profile` would add a second,
finer axis: which *model* a given adapter invocation runs as, independent
of which adapter it is.

This draft is intentionally narrow. A broader question was raised and left
open during the same conversation this draft came out of: whether AWF
itself, or any of the four adapters, can act as the "entry point"
orchestrator for an ad hoc (e.g. voice-composed) chain of roles, and how
that would stay inside AWF's durable/replayable model. That question is
NOT addressed here - this draft only covers wiring an existing, narrow,
already-scaffolded field. See project memory/prior discussion before
picking that back up.

## Decision (proposed)

At each `agent` node, resolve `manifest.model_profile` (if set) to a real
Model Profile object, pick its winning candidate (same
`enabled_candidates_by_priority()` + fallback logic the Gateway already
uses), and pass the candidate's `model` name into the adapter's own
`constraints` under a new key (e.g. `model_override`), the same shape
`mcp_extra_args`/`mcp_env_overlay` already use. Each adapter appends its
own real flag (`--model <value>` for three of four; Codex additionally
needs a decision on whether a `local_only` profile should also imply
`--oss --local-provider ollama` rather than plain `--model`).

An unset `model_profile` changes nothing - the adapter runs with whatever
model it would have used by default, exactly like an unset `mcp`/`skills`
list today.

## Open questions for whoever picks this back up

- Does a Model Profile's `privacy.local_only: true` need to force Codex's
  `--oss --local-provider` path specifically, or is passing the resolved
  model name to plain `--model` sufficient (i.e. does Codex's own default
  provider routing already do the right thing if the model name alone
  identifies a local model)? Not verified.
- The Model Gateway's `purpose` enum and this per-adapter `model_profile`
  reference the same registry kind (`model-profiles`) but are consumed by
  two unrelated code paths. Is that a permanent, acceptable split, or does
  it want unifying later? Left open on purpose.
- Should `model_profile` support the same explicit-opt-in-only posture
  `skills`' `share` flag uses, or is naming a profile inherently
  low-risk enough to apply unconditionally? Not decided.

## Scope for implementation (when revisited)

1. `engine/agent_step.py` - resolve `model_profile`, select a candidate,
   merge `model_override` into `constraints`.
2. `workflow/engine.py` - thread `manifest.model_profile` through, next to
   `capabilities`/`mcp`/`skills`.
3. `adapters/{claude_code,codex_cli,antigravity_cli,copilot_cli}.py` -
   consume `constraints["model_override"]`, append the adapter's own real
   flag.
4. Decide the Codex `--oss --local-provider` question above before
   writing that adapter's branch, not after.

## Acceptance (proposed)

A manifest with `modelProfile: qwen3-8b-local@1.0.0` drives a real Run
where the adapter's own subprocess command includes the resolved model
name via its real flag. An unset field changes nothing. A profile with no
enabled candidates fails the Step before the adapter runs, same posture as
an empty Capability Guard allowlist.
