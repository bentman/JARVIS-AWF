# ADR-0002: Agent Manifest schema and wiring

## Status

Implemented.

## Context

Section 9.2 and Section 16.2/16.5 of the spec establish that an "Agent
Manifest" exists, is one of the registry kinds with a real `config/app_registry/`
counterpart (Section 9.3), and carries at least `adapter`, `capabilities`
(a capability allowlist), and optionally `voice`. No section of the spec
defines the manifest's actual field shape the way Section 9.1 defines a
Capability Record or Section 11 defines a Model Profile.

The gap is real, not just undocumented:

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

The CLI tools AWF already wraps (Claude Code, GitHub Copilot CLI,
Antigravity/`agy`) converge on the same local subagent shape: a Markdown file with YAML frontmatter — `name`,
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
| `version` | yes | string | self-describing, like a Capability Record's `identity.version` - needed so `op_registry_publish` can derive a target path from content alone |
| `description` | yes | string | matches the industry-universal field |
| `adapter` | yes | string | must resolve to a real `ADAPTER_REGISTRY` key |
| `capabilities` | no, default `[]` | list of `name@version` | the allowlist Section 9.2 already describes; equivalent to every surveyed tool's `tools` field. An empty/undeclared list is treated as "no allowlist scoped yet" (falls back to the pre-ADR-0002 self-permitting default), not "allow nothing" - Section 9.2's "a maximum, never a grant" only constrains once a list is actually populated |
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

## Implementation

1. `registry/agent_manifest.py` — parser/dataclass module: splits YAML
   frontmatter from the Markdown body, mirroring
   `capability_record.py`/`model_profile.py`/`voice_profile.py`'s pattern
   for everything past that split.
2. `registry/resolve.py` — `agents` resolves to `<name>/<version>.md`
   (a third shape alongside plain `.yaml` and Skills' nested `SKILL.md`).
3. `engine/agent_step.py` — `run_agent_step` takes real `agent_allowlist`
   and `voice` parameters. `agent_allowlist=None` (no manifest resolved)
   keeps the pre-ADR-0002 self-permitting singleton exactly as before -
   additive, not breaking. `voice`, when given, is folded into the Step's
   own persisted `output_json` (not just the in-memory return value), so a
   later `awf status`/`op_run_status` query can actually see it.
4. `workflow/engine.py` — `make_agent_node_executor` resolves an `agentRef`
   node field into a real `AgentManifest`, sourcing `adapter`/`role` as
   defaults (the node's own fields still win if present), prepending the
   manifest's `instructions` body ahead of the node's `objective`, and
   passing its `capabilities` as the real Guard allowlist.
5. `cli/core_ops.py` — `op_registry_publish`/`op_registry_validate` branch
   on `path.suffix == ".md"` for Agent Manifests, ahead of the YAML-based
   kinds; `op_registry_list` globs `*.md` for kind `agents`, same shape as
   every non-Skill kind otherwise.
6. Shipped real default manifests: `builder` (adapter `claude-code`),
   `verifier` (adapter `codex`), `adversary` (adapter `antigravity`), each
   with `role` set and `voice: <same-name>@1.0.0`. `narrator` has no Agent
   Manifest: it doesn't invoke any adapter - it's Section 16.5's fallback
   identity for voice output with no assigned role, not an agent that runs
   anything, so an `adapter` field on it would misrepresent it. It remains
   exactly what it already was: a real Voice Profile with no corresponding
   Agent Manifest.

## Consequences

- The Capability Guard's allowlist check is real for the first time since
  it was introduced - a Section 18 non-negotiable ("No workflow logic may
  bypass the Capability Guard") was previously only half-enforced by the
  allowlist path specifically. Verified live: a real `agentRef`-driven
  workflow run produced a genuine Guard decision event carrying the
  manifest's `role`, and a dedicated test proves a populated `capabilities`
  list can actually deny.
- `agentRef` is additive to the `agent` node shape - no existing published
  workflow YAML needs to change, confirmed by a passing test with a node
  that declares neither `agentRef` nor a manifest.
- `/agents` (`awf/registry.list` with kind `agents`) returns real content
  for the first time - verified live over the actual JSON-RPC transport.
- `modelProfile` on a manifest and `reviewProfile` on a gate node overlap in
  purpose and are not unified: `modelProfile` is parsed and stored on
  `AgentManifest` but has no consumer, same as `mcp` (AWF has no MCP
  client implementation anywhere in `backend/src`). Whether to unify
  `modelProfile`/`reviewProfile` is open for whoever wires the Model
  Gateway into the Guard/Gate-adjacent roles next.
- `mcp` is likewise parsed but unconsumed - there's nothing to wire it to.
