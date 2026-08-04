# ADR-0004: skills registry schema — AWF is the primary consumer, adapters are a selective, explicit exception

## Status

Accepted.

## Context

Section 9.3 specifies the `skills` registry kind at `skills/<name>/<version>/SKILL.md` (+ optional `scripts/`, `references/`, `assets/`), one of the two kinds shaped as a directory rather than a single file (`skills` shares this with the earlier-established pattern for Markdown-bodied objects). Section 5 pins the format: the Agent Skills open standard (`agentskills.io`, Apache-2.0, stewarded via the Agentic AI Foundation) - `SKILL.md` YAML frontmatter (`name`, `description` required; `license`, `compatibility`, `metadata`, `allowed-tools` optional) followed by a Markdown body, with progressive disclosure into `scripts/`/`references/`/`assets/` only as needed. Section 12.2's citation of `/skills` states each registry Skill "is also directly invocable as `/<skill-name>`" in AWF's own CLI, and that this is the single source of truth for custom commands - there is no second, AWF-specific command file format.

`registry/resolve.py` and `cli/core_ops.py` already special-case `kind == "skills"` as a directory (`<name>/<version>/SKILL.md`, not `<version>.yaml`), `op_registry_list`/`op_registry_get` work end-to-end, and a real `data/registry/skills/demo-skill/1.0.0/SKILL.md` exists. But no `registry/skill.py` loader exists (unlike `capability_record.py`, `agent_manifest.py`, `mcp_server.py`), `AgentManifest` has no `skills` field, and `adapters/base.py`'s `AgentInvocation.skills: tuple[str, ...] = ()` - present in the envelope since Section 12.2 requires it ("available skills") - has no resolver populating it and no consumer reading it. This is the same "schema with no caller" state `mcp` was in before ADR-0003.

Unlike `mcp`, the registry format here is not something AWF has to translate per adapter - `SKILL.md` is already the literal shared interchange format. Verified live against the same four installed CLIs used in ADR-0003:

| Adapter | Real mechanism | Confirmed via |
|---|---|---|
| Claude Code | reads worktree-relative `.claude/skills/<name>/SKILL.md` automatically at session start, no flag | `code.claude.com/docs/en/skills`: "Project \| `.claude/skills/<skill-name>/SKILL.md` \| This project only" |
| GitHub Copilot CLI | reads `.github/skills/`, `.agents/skills/`, **or `.claude/skills/`** (project-level), no flag | `copilot skill --help`: "Project .github/skills/, .agents/skills/, or .claude/skills/" |
| Codex CLI | `skills.config.<n>.path` - a real config field, settable via the same `-c` dotted-path override ADR-0003's renderer already uses for `mcp_servers.*` | `learn.chatgpt.com/docs/config-file/config-reference`: `skills.config.<index>.path` - "Path to a skill folder containing `SKILL.md`" |
| Antigravity (`agy`) | `--disable-slash-commands` help text confirms a "skill expansion" concept exists in print mode, but no directory convention is documented or discoverable from the installed CLI's own `--help`; `agy plugin import [gemini\|claude]` exists but is a persistent, explicit mutation, not a per-invocation mechanism - the same category ADR-0003 ruled out for `codex mcp add`/`copilot skill add` | `agy --help`, `agy plugin --help` |

Separately: AWF has no authority model beyond the operator. `registry_index.trust_status` (Section 9.3: `local`/`trusted`/`quarantined`/`blocked`) is the only scoping surface that exists anywhere in the system - there is no notion of per-agent, per-workflow, or delegated authority sitting above or beside it. Any decision here about what an agent gets to run has to live inside that single surface; inventing a second one is out of scope.

## Decision

A Skill is, by default, content AWF itself consumes - not a file placed where an adapter's own runtime autonomously decides to invoke it. An Agent Manifest's `skills` list (new field, ADR-0002) is resolved and trust-gated exactly like `mcp`, and each surviving Skill's `SKILL.md` body is folded directly into the objective text AWF sends to the adapter - the same additive-injection `workflow/engine.py` already does for `manifest.instructions`. AWF is the one reading and applying the procedure; the adapter never sees a discoverable skill directory, never decides on its own whether the skill is relevant, and needs no adapter-specific mechanism at all for this tier.

Sharing a Skill with an agent - letting the adapter's own engine discover and autonomously invoke it - is a second, explicit, per-reference opt-in, never the default. A manifest marks a skill shared (`skills: [{ref: name@version, share: true}]`, or an equivalent explicit marker distinguishing it from a plain `name@version` string); only shared skills get materialized into the adapter's own read path. `scripts/` inside a Skill is executable code, not declarative config like an MCP server's JSON/TOML - sharing one hands an adapter something that runs, so leaving it opt-out by default understates the risk; ADR-0003's MCP tool surface was config an adapter connects through, this is code an adapter can execute directly.

## Rationale

Section 2's framing - AWF invokes, records, verifies, remembers - applies here the same way it did to ADR-0003's MCP decision, but the conclusion differs because the object differs. An MCP server is infrastructure a working adapter already knows how to connect to; a Skill is a procedure, and AWF already has a place that consumes procedures: the objective/instructions text it constructs for every agent node. Injecting a Skill there is not a new capability, it is the existing `manifest.instructions` mechanism applied to one more source of text. Building adapter-side skill placement as the default would mean handing autonomous invocation authority to four different runtimes for a resource whose primary described use (Section 12.2, `/skills` and `/<skill-name>`) is already AWF's own CLI surface, not the adapters'.

The explicit-opt-in tier for sharing exists because the underlying mechanism is real and, for two of the four adapters, requires no per-invocation work at all - refusing to ever use it would be leaving a working, documented integration point unused for no reason tied to the spec. Making it opt-in rather than automatic is the direct consequence of there being no authority model above the operator: the operator authors the manifest, and the manifest's own explicit marker is the only "grant" the system is capable of expressing. Nothing here proposes fixing that gap - it is named so the choice to keep sharing manual is legible as a choice, not an oversight.

## Mechanism

At each `agent` node, before the adapter runs:

1. Resolve the manifest's `skills` list. No `agentRef`, or an empty list, changes nothing.
2. Skip any ref that is `quarantined` or `blocked` in `registry_index` - same gate as `mcp` and `capabilities`.
3. For each surviving ref, read `SKILL.md`'s body (frontmatter stripped) and append it to the objective text, in list order, after `manifest.instructions` and before the node's own per-invocation `objective` - same layering `manifest.instructions` already uses, one step further down.
4. For refs explicitly marked `share: true`, additionally copy the skill's full directory (`SKILL.md` + `scripts/`/`references/`/`assets/`, unmodified - no reformatting, the format is already universal) into the worktree at `.claude/skills/<name>/`. This one path is already read by both Claude Code and GitHub Copilot CLI with no adapter-specific flag. For Codex, also emit `-c skills.config.<n>.path=.claude/skills/<name>` overrides, appended alongside ADR-0003's `mcp_servers.*` ones. Antigravity is unsupported for this tier until its real discovery path is verified against the installed CLI, not assumed - the same standard ADR-0003 held itself to.
5. Write one `events` row per node carrying the full `name@version` refs and digests resolved (both tiers), and which refs were shared - the audit record of what procedural content and what executable surface the agent was given.

`AgentInvocation.skills` carries the resolved ref list (both tiers) into the envelope, satisfying Section 12.2's "available skills" - informational for the adapter and for downstream artifacts, not itself the delivery mechanism.

## Registry object schema

`skills/<name>/<version>/SKILL.md` (+ optional `scripts/`, `references/`, `assets/`), at `config/app_registry/skills/` and `data/registry/skills/` (not in `DATA_ONLY_KINDS`). The frontmatter shape is not AWF's to define - it is the Agent Skills standard's, unmodified:

| Field | Required | Shape | Notes |
|---|---|---|---|
| `name` | yes | string, ≤64 chars, lowercase/digits/hyphens, no leading/trailing/doubled hyphen | must match the parent directory name (standard's own rule) |
| `description` | yes | string, ≤1024 chars | what the skill does and when to use it - this is also what AWF's `/skills` listing and autocomplete show |
| `license` | no | string | passed through unread |
| `compatibility` | no | string, ≤500 chars | passed through unread; not used for AWF-side gating |
| `metadata` | no | map of string→string | passed through unread |
| `allowed-tools` | no | space-separated string | the standard's own experimental tool-preapproval field - AWF neither reads nor enforces it. It is a second allowlist concept sitting next to AWF's Capability Guard and the `mcp` list's own allowlist; for the AWF-injected tier this field is inert (there are no adapter-native tool calls to pre-approve, the text is just objective content), and for the shared tier it governs the adapter's own runtime exactly as it does for a skill an operator installed by hand - AWF's Guard does not see inside it, same tradeoff ADR-0003 accepted for MCP tool calls. |

AWF's own added identity is the directory itself: `name`/`version` are read from the frontmatter and the publish path, matching the pattern every other self-describing registry kind uses. A directory's digest is `sha256` over its sorted `relative_path:sha256(file_bytes)\n` lines, one hash per file, concatenated in path order and hashed once more - deterministic regardless of filesystem iteration order, and what the `events` row in step 5 above actually records.

Trust status is not a file field: it lives in `registry_index`, same as every other kind (Section 9.3).

No default Skill ships this pass. `demo-skill` (`data/registry/skills/demo-skill/1.0.0/`) exists only to prove `op_registry_list` enumerates the kind and predates this ADR; it is not a template for a real one.

## The tradeoff accepted

For the AWF-injected tier, there is no tradeoff to name: the content becomes plain objective text, already inside every enforcement AWF applies to any other instruction it constructs. For the shared tier, the same gap ADR-0003 accepted applies again and is larger: a shared Skill's `scripts/` runs as adapter-invoked code, and AWF's Capability Guard does not see inside an adapter's own decision to run it, only the fact that the skill was made available. This is accepted for the same reason ADR-0003 accepted it for MCP tool calls - the manifest's explicit `share: true` marker is the allowlist, enforced in control code, auditable via the `events` row - but it is named here as a materially bigger exposure than a shared MCP server, not a repeat of the same-size risk.

## Scope for implementation

1. `backend/src/awf/registry/skill.py` - loader/validator for the frontmatter table above, plus the directory-digest function. Mirrors `capability_record.py`'s shape, not `mcp_server.py`'s (this kind's content is a directory, not a single YAML mapping).
2. `engine/agent_step.py` - resolve the manifest's `skills` list, apply the trust gate, append surviving `SKILL.md` bodies to the objective, copy `share: true` directories into the worktree, emit Codex's `-c skills.config.*` overrides, write the `events` row.
3. `workflow/engine.py` - thread the manifest's `skills` list through, alongside `capabilities` and `mcp`.
4. `registry/agent_manifest.py` - add the `skills` field (list of `{ref, share}` or equivalent), parsed the same way `mcp` is today.
5. `cli/core_ops.py` - `op_registry_publish`/`op_registry_validate` gain a `skills` branch (`op_registry_list` already works generically for this kind, per Context above).
6. Verify Antigravity's real skill-discovery path against the installed CLI before deciding supported/unsupported for the shared tier - do not carry over the MCP finding by assumption; it may differ.
7. AWF's own `/skills` → `/<skill-name>` direct-invocation surface (Section 12.2's `/skills` line) is a CLI-frontend concern, not this ADR's registry/mechanism scope - `frontend/cli` currently only lists the kind generically (`commands.ts`), and wiring real per-skill invocation is a separate, later piece of work.

## Acceptance

A manifest with `skills: [demo-skill@1.0.0]` (no `share`) drives a real Run where the resolved `SKILL.md` body is present in the objective the adapter receives, and no `.claude/skills/` directory is written. The same ref with `share: true` additionally produces a real `.claude/skills/demo-skill/` in the worktree, and a real Claude Code invocation against it can invoke the skill by name. A quarantined ref is refused before either tier applies. `events` shows the resolved set and which refs were shared. A skill's `scripts/` file is never executed by AWF itself under any tier.

## Consequences

- `AgentManifest.skills` and `AgentInvocation.skills` get their first real consumer; `skills` stops being schema with no caller.
- Section 12.2's `/skills` → `/<skill-name>` CLI surface remains open work, not closed by this ADR - named in Scope item 7 rather than left implicit.
- The Agent Skills standard's `allowed-tools` field stays unread by AWF for both tiers - a second, adapter-native allowlist concept coexisting with, not merged into, the Capability Guard. Same shape of gap ADR-0003 named for MCP, not resolved here either.
- The explicit `share` marker is the only "grant" the system can express, because no authority model exists above the operator who authors the manifest. If a future revision adds real multi-operator or delegated authority, this is the mechanism that would need to change first.
