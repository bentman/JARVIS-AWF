# ADR-0002: Agent Manifest schema and wiring

## Status

Proposed — scope/tracking only. Not implemented.

## Context

Section 9.2 and Section 16.2/16.5 of the spec establish that an "Agent
Manifest" exists, is one of the registry kinds with a real `config/app_registry/`
counterpart (Section 9.3), and carries at least `adapter`, `capabilities`
(a capability allowlist), and optionally `voice`. No section of the spec
defines the manifest's actual field shape the way Section 9.1 defines a
Capability Record or Section 11 defines a Model Profile.

Inspecting the codebase found the gap is real, not just undocumented:

- `config/app_registry/agents/` and `data/registry/agents/` are empty
  placeholder directories (`.gitkeep` only) — no schema module exists
  (`registry/agent_manifest.py` doesn't exist, unlike its siblings).
- `engine/agent_step.py::run_agent_step` calls the Capability Guard with
  `agent_allowlist=[capability.ref]` — a singleton containing only the
  capability being checked. `evaluate()`'s allowlist check
  (`if capability.ref not in agent_allowlist: DENY`) can therefore never
  fail. The Guard has a real caller and writes real decision events, but
  the allowlist half of its job is currently unfalsifiable.
- `/agents` (TUI) and `awf/registry.list` for kind `agents` are wired
  end-to-end but permanently return `[]` — nothing can populate the
  directory without a schema and a publish path.
- Voice Profile resolution (`voice_profile.py`, four real profiles shipped
  in Phase 12) has zero production callers anywhere. The real voice round
  trip (`frontend/gui/src/main/voicePipeline.ts`) falls back to a bare
  literal (`"bf_isabella"`) rather than resolving anything through the
  registry.

A survey of the CLI tools AWF already wraps (Claude Code, GitHub Copilot
CLI, Antigravity/`agy`) found all three independently converged on the same
local subagent shape: a Markdown file with YAML frontmatter — `name`,
`description` (both required), an explicit tool/capability allowlist
(`tools`), a model choice, MCP server access, and a Markdown body used as
the system prompt. Codex CLI's custom agents use TOML instead of
Markdown+YAML but keep the same core fields (name, model, instructions).
This is the closest thing to a real, sharable, cross-vendor convention for
"what an agent is," short of A2A's `AgentCard` (which is shaped for remote
agent discovery over the wire, not local config, and is a poorer fit here).

## Decision

Adopt the converged shape: a Markdown file with YAML frontmatter at
`config/app_registry/agents/<name>/<version>.md` (and
`data/registry/agents/` for operator overrides, per Section 9.3's normal
two-root resolution — `agents` is NOT in `DATA_ONLY_KINDS`). Frontmatter
fields:

| Field | Required | Shape | Notes |
|---|---|---|---|
| `name` | yes | string | matches the industry-universal field |
| `description` | yes | string | matches the industry-universal field |
| `adapter` | yes | string | must resolve to a real `ADAPTER_REGISTRY` key |
| `capabilities` | no, default `[]` | list of `name@version` | the allowlist Section 9.2 already describes; equivalent to every surveyed tool's `tools` field |
| `role` | no | `builder`\|`verifier`\|`adversary` | matches `guard/capability_guard.py::ROLES`, AWF-specific (Trifecta) |
| `mcp` | no, default `[]` | list of `name@version` | refs into the existing `config/app_registry/MCP/` registry kind — equivalent to every surveyed tool's `mcpServers` field, never wired to anything today |
| `voice` | no | `name@version` | resolves against `config/app_registry/voice-profiles/`, closing the gap above |
| `modelProfile` | no | `name@version` | resolves against a Model Profile; only meaningful for Gateway-routed roles (e.g. a `judge`/`adversary` review pass), not the wrapped-CLI adapters themselves |
| body (Markdown) | no | text | default system-prompt/instructions, distinct from a workflow node's per-invocation `objective` |

`workflow` `agent` nodes gain an `agentRef: name@version` field. The node
resolves the manifest and uses its `adapter`/`capabilities`/`role`/`voice`
as defaults; the node's own `objective` remains the per-invocation task,
layered on top of (not replacing) the manifest's default instructions body.
Existing node-level `adapter`/`role`/`capability` fields stay valid for a
node with no `agentRef` — this is additive, not a breaking change to
`workflow/nodes.py`'s `agent` shape.

## Scope for implementation (future work, not started)

1. `registry/agent_manifest.py` — parser/dataclass module, mirroring
   `capability_record.py`/`model_profile.py`/`voice_profile.py`.
2. `engine/agent_step.py` — resolve the invoking Agent Manifest's real
   `capabilities` list and pass it as `agent_allowlist`, replacing the
   current `[capability.ref]` singleton.
3. `cli/core_ops.py` — `op_registry_publish`/`op_registry_validate` gain an
   Agent Manifest branch; `_build_node_executors` resolves `agentRef` on an
   `agent` node into adapter/capability/role/voice defaults.
4. `workflow/nodes.py` — `agent` node shape gains optional `agentRef`.
5. Ship real default manifests — `builder`, `verifier`, `adversary`,
   `narrator` — under `config/app_registry/agents/`, mirroring the four
   Voice Profiles already shipped in Phase 12. This is what gives `/agents`
   non-empty content and gives the `voice` field something real to resolve
   against for the first time.

## Consequences

- Closing this gap makes the Capability Guard's allowlist check real for
  the first time since it was introduced — a Section 18 non-negotiable
  ("No workflow logic may bypass the Capability Guard") is currently only
  half-enforced by the allowlist path specifically.
- `agentRef` is additive to the `agent` node shape — no existing published
  workflow YAML needs to change.
- `modelProfile` on a manifest and `reviewProfile` on a gate node (ADR
  predates this one — see the Model Gateway fix in `CHANGE_LOG.md`,
  2026-08-03 04:20) overlap in purpose; whether to unify them under one
  resolution path is an open question for whoever implements this, not
  decided here.
