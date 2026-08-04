# ADR-0003: mcp server registry schema — servers run through the adapters, not through AWF

## Status

Accepted.

## Context

Section 9.3 specifies the `mcp` registry kind: each `mcp/<name>/<version>.yaml`
"declares how AWF starts or connects to that server (transport,
command/args or URL, required environment references), the
tools/resources/prompts it exposes (by name, for cross-referencing with
Capability Records), and — in `data/registry/` — its trust status." Section
5 pins the protocol itself: MCP spec 2026-07-28 (final) - a stateless core,
a versioned Extensions framework (Tasks, MCP Apps), and an explicit
deprecation note: Roots, Sampling, and Logging "do not build against
them."

`config/app_registry/mcp/` and `data/registry/mcp/` are empty placeholders
(`.gitkeep` only). No schema module exists. `awf/registry.list` for this
kind is wired end-to-end but returns `[]`. `AgentManifest.mcp` (ADR-0002)
is parsed and stored but has no refs to resolve against and no consumer.

## Decision

AWF does not implement an MCP client. All five named adapters (Claude
Code, Codex CLI, Antigravity, GitHub Copilot CLI, Cline) already have one.
AWF renders registry `mcp` definitions into whatever config file each
adapter reads, at Run time, and the adapter does the connecting.

## Rationale

Section 2 defines AWF as the durable layer above the CLI agents: "it
invokes them, records what they did, verifies the result, and remembers
it" - never itself the thing holding a live tool connection. Writing a
second MCP client next to four working ones duplicates what DRY and YAGNI
are pointed at. There is also no place to put one: Section 12.2 fixes
eight node types and none is `mcp` - a client would need a spec revision
before it had a caller.

## Mechanism

At each `agent` node, before the adapter runs:

1. Resolve the manifest's `mcp` list (ADR-0002). No `agentRef`, or an empty
   list, renders nothing - the adapter runs exactly as it would have.
2. Skip any ref that is `quarantined` or `blocked` in `registry_index`.
3. Render each remaining server into the adapter's own config format,
   written into the Run's worktree or `cache/sandbox/<run_id>/` - never
   the operator's home directory, never anything that outlives the Run.
   Antigravity has no per-invocation config flag and reads MCP servers
   only from `~/.gemini/config/mcp_config.json` - its own real home
   directory. For this one adapter, step 3 means giving the subprocess a
   throwaway `$HOME` instead: `cache/sandbox/<run_id>/agy_home/<actor>/`
   gets a fresh `.gemini/config/mcp_config.json` and
   `.gemini/antigravity-cli/settings.json` (with the `mcp(*)` allow rule
   headless mode requires - no narrower per-server syntax was found to
   work), plus a read-only copy of
   `.gemini/antigravity-cli/antigravity-oauth-token` from the operator's
   real home, since that is where session auth lives and nowhere else.
   The operator's real `~/.gemini/` is only ever read from, never written
   to; the copy is scoped to the Run's own `cache/sandbox/` tree and goes
   with it.
4. Write one `events` row carrying the `name@version` refs and digests
   rendered - the audit record of what tool surface the agent was given.

Secrets never land in the rendered file. `env_secrets`/`header_secrets`
resolve to an environment-variable reference in the rendered file (`${VAR}`
substitution, or Codex's `env_vars`/`bearer_token_env_var` fields), and
`run_agent_step` injects the plaintext into the adapter subprocess's
environment directly. The value dies with the process and never touches
disk - non-negotiable #3 ("No secret may appear in plaintext in
`config/app_registry/`, `data/registry/`, the `events` table, or any
artifact," Section 18) holds without a special case.

Antigravity's copied `antigravity-oauth-token` is the one exception: it is
real session-credential material, at rest in `cache/sandbox/<run_id>/` for
the Run's duration (and, for a `FAILED` run kept for post-mortem per the
existing worktree/scratch retention policy, until that Run is cleaned up).
This is a real, named increase in exposure over the other three adapters,
where nothing secret ever touches disk at all - accepted because no
narrower mechanism exists for this adapter, not because the risk is the
same size.

## Registry object schema

`mcp/<name>/<version>.yaml` (plain YAML, no Markdown body - there is no
system-prompt concept for a server definition), at `config/app_registry/mcp/`
and `data/registry/mcp/` (not in `DATA_ONLY_KINDS`, same two-root
resolution as Capability Records). Field names use `snake_case`, matching
Capability Record and Model Profile.

| Field | Required | Shape | Notes |
|---|---|---|---|
| `name`, `version` | yes | string | self-describing, matches Capability Record's pattern |
| `type` | yes | `stdio` \| `http` | matches Claude Code / GitHub Copilot CLI's field name |
| `command`, `args` | required if `stdio` | string, list of strings | passed through to the rendered adapter config unchanged |
| `url` | required if `http` | string | passed through unchanged |
| `env` | no, default `{}` | map of literal string→string | literal, non-secret config only (e.g. `NODE_ENV`) |
| `env_secrets` | no, default `{}` | map of env-var-name → secret name | resolved through the secrets table (Section 9.4) and injected into the adapter subprocess's environment at Run time - never rendered into the file |
| `headers` | no, default `{}` | map of literal string→string | literal, non-secret headers only |
| `header_secrets` | no, default `{}` | map of header-name → secret name | same mechanism as `env_secrets`, for HTTP auth headers |
| `startup_timeout_sec` | no, default `10` | int | connect/handshake timeout, passed through where the target adapter supports it |
| `tool_timeout_sec` | no, default `60` | int | per-tool-call timeout, passed through where supported |
| `tools`, `resources`, `prompts` | no, default `[]` | list of strings | documentation/cross-reference only - names this server exposes, for a Capability Record's `provider` field to point at (Section 9.1). Not an enforcement allowlist. |

Trust status is not a file field: it lives in the `registry_index` DB
column: config-root objects carry none (inclusion in the repository is the
review, Section 9.3); `data/registry/` objects carry `local`/`trusted`/
`quarantined`/`blocked`, and step 2 above is what actually acts on it.

One default server ships under `config/app_registry/mcp/`: `context7`
(http, `https://mcp.context7.com/mcp`, API key via `header_secrets`). The
official MCP reference `fetch` server (`mcp-server-fetch`, run via `uvx`)
is Python-tooling-only - no npm package exists for it - and is not shipped
this pass, to avoid introducing a second per-invocation runtime (`uvx`
alongside `npx`) for one example server; nothing prevents a `data/registry/`
entry for it later using the real command. `github` (remote hosted
endpoint, plain PAT, no Docker or local process) and `playwright` (`npx
@playwright/mcp@latest`, Microsoft's official package - distinct from the
similarly-named third-party `@executeautomation/playwright-mcp-server`)
remain real, documented options for a later addition.

## The tradeoff accepted

Tool calls happen inside the adapter, so the Capability Guard does not see
them. The manifest's `mcp` list is the allowlist instead - deterministic,
enforced in control code, testable, the same shape as the `capabilities`
allowlist (ADR-0002) - plus the trust gate and the `events` record above.
This is accepted. If per-tool authorization is needed later, GitHub
Copilot CLI's `preToolUse` hook (Section 10.2, still unbuilt) is the seam
- for that one adapter, not a general solution.

## Scope for implementation

1. `backend/src/awf/mcp/render.py` - one renderer per adapter family,
   `list[McpServer] → (path, contents, env_overlay)`. Pure: no subprocess,
   no filesystem access inside the function itself.
2. `engine/agent_step.py` - resolve the manifest's `mcp` list, apply the
   trust gate, render, write the `events` row, merge `env_overlay` into
   the adapter subprocess's environment.
3. `workflow/engine.py` - thread the manifest's `mcp` list through
   alongside `capabilities`.
4. `registry/mcp_server.py` - parser/dataclass module for the schema
   above, mirroring `capability_record.py`.
5. `cli/core_ops.py` - `op_registry_publish`/`op_registry_validate` gain
   an `mcp` branch (`op_registry_list` already works generically for this
   kind).
6. Ship the `context7` default definition.
7. Check each adapter's current config target against its own docs before
   writing that adapter's renderer - Section 10.2 already warns these
   move. Codex is the awkward one: it reads `~/.codex/config.toml` by
   default, so whether a Run-scoped file arrives via `CODEX_HOME`,
   `--config`, or by extending `config/codex/awf-default.toml` needs
   testing against the installed version, not assuming.
8. Any adapter that cannot be driven per-invocation is unsupported this
   pass - not worked around. Antigravity was live-tested against this
   rule, not assumed: it has no per-invocation flag, but redirecting the
   subprocess's own `$HOME` env var to a scratch directory is a real,
   working per-invocation mechanism (confirmed live, including that the
   copied `antigravity-oauth-token` is required - a scratch `$HOME`
   without it fails auth) - so it is driven, not excluded, per the
   Mechanism section above. Of the four adapters actually implemented in
   `ADAPTER_REGISTRY` (`claude-code`, `codex`, `antigravity`, `copilot` -
   Cline, named in Context/Decision above, has no adapter module in this
   codebase and is out of scope for this rule entirely), none is excluded
   by it.

## Acceptance

A manifest with `mcp: [context7@1.0.0]` drives a real Run where the adapter
actually calls a tool from it - verified against all four implemented
adapters, including Antigravity via its scratch-`$HOME` mechanism. The same workflow
with the field omitted renders nothing. A quarantined ref is refused
before the adapter starts. `events` shows the rendered set. No secret
exists on disk anywhere, except Antigravity's copied session-auth token,
named as an accepted exception in the Mechanism section above.

## Consequences

- `AgentManifest.mcp` gets its first consumer; these registry objects
  become live config instead of schema with no caller.
- An agent's tool surface becomes versioned and auditable instead of
  ambient state on the operator's machine.
- The Capability Record identity type `mcp-tool` (Section 9.1) stays
  dormant - only needed if AWF ever builds a client after all. Nothing
  here blocks that.
- OAuth-only servers remain unconfigurable through this mechanism. An
  operator can still wire one directly into an adapter's own config, but
  that connection then exists outside AWF's record - a real gap, named
  here rather than left implicit.
