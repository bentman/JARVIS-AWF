# ADR-0003: mcp server registry schema and default servers

## Status

Proposed — scope/tracking only. Not implemented.

## Naming

`mcp` (lowercase) is the registry kind designator throughout, consistent
with every other kind's directory name (`agents`, `capabilities`,
`skills`, `voice-profiles`, `workflows`, `model-profiles`). Section 7's own
tree diagram shows `MCP/<name>/<version>.yaml`; this ADR normalizes that to
lowercase.

## Context

Section 9.3 already specifies more about the `mcp` registry kind than it
did for Agent Manifests before ADR-0002: each `mcp/<name>/<version>.yaml`
"declares how AWF starts or connects to that server (transport,
command/args or URL, required environment references), the
tools/resources/prompts it exposes (by name, for cross-referencing with
Capability Records), and — in `data/registry/` — its trust status." Section
5 pins the protocol itself: MCP spec 2026-07-28 (final) - a stateless core
(the old initialize/notifications handshake is gone; every request now
carries its own protocol version and capabilities), a versioned Extensions
framework (Tasks, MCP Apps), and an explicit deprecation note: Roots,
Sampling, and Logging "do not build against them."

`config/app_registry/mcp/` and `data/registry/mcp/` are empty placeholders
(`.gitkeep` only). No schema module exists. The only reference to MCP
anywhere in `backend/src` is `capability_record.py`'s `IDENTITY_TYPES` enum
including `"mcp-tool"` - parsed, never connected to anything.
`awf/registry.list` for this kind is wired end-to-end (the generic `.yaml`
listing path already works, no special-casing needed) but returns `[]`.
`AgentManifest.mcp` (ADR-0002) is parsed and stored but has no refs to
resolve against and no consumer.

Claude Code (`.mcp.json`), Codex CLI (`~/.codex/config.toml`
`[mcp_servers.*]`), GitHub Copilot CLI (`mcp-config.json`), and Antigravity
(`mcp_config.json`) converge on a per-server entry keyed by name, with
`command`+`args`+`env` for local/stdio servers or `url`(+`headers`) for
remote/HTTP servers, and secrets always referenced by name, never
embedded. Codex CLI draws the sharpest version of that reference
distinction: `env` is `map<string,string>` of literal values; `env_vars`
is a separate array of by-name references resolved from the environment
at connect time; `bearer_token_env_var` is a single named reference for
the HTTP bearer token, never a literal - a stronger, more structurally
explicit precedent than Claude Code's `${VAR}` string substitution.

## Decision

`mcp/<name>/<version>.yaml` (plain YAML, no Markdown body - there is no
system-prompt concept for a server definition) at `config/app_registry/mcp/`
(and `data/registry/mcp/` for operator additions - not in
`DATA_ONLY_KINDS`, same two-root resolution as Capability Records). Field
names use `snake_case`, matching Capability Record and Model Profile.
(ADR-0002's Agent Manifest used `camelCase` for `agentRef`/`modelProfile`;
that inconsistency is not fixed retroactively here.)

| Field | Required | Shape | Notes |
|---|---|---|---|
| `name`, `version` | yes | string | self-describing, matches Capability Record's pattern |
| `type` | yes | `stdio` \| `http` | matches Claude Code / GitHub Copilot CLI's field name; `sse`/`ws` deferred - no client exists yet to need them |
| `command`, `args` | required if `stdio` | string, list of strings | matches the converged shape exactly |
| `url` | required if `http` | string | matches the converged shape exactly |
| `env` | no, default `{}` | map of literal string→string | literal, non-secret config only (e.g. `NODE_ENV`) |
| `env_secrets` | no, default `{}` | map of env-var-name → secret name | resolved through the secrets table (Section 9.4) at launch, never a literal value in the file - adapted from Codex's `env`/`env_vars`/`bearer_token_env_var` split |
| `headers` | no, default `{}` | map of literal string→string | literal, non-secret headers only - expected to be rare |
| `header_secrets` | no, default `{}` | map of header-name → secret name | same reference mechanism as `env_secrets`, for HTTP auth headers |
| `startup_timeout_sec` | no, default `10` | int | connect/handshake timeout - matches Codex's default |
| `tool_timeout_sec` | no, default `60` | int | per-tool-call timeout - matches Codex's default |
| `tools`, `resources`, `prompts` | no, default `[]` | list of strings | documentation/cross-reference only - names this server exposes, for a Capability Record's `provider` field to point at (Section 9.1). Not an enforcement allowlist: unlike GitHub Copilot CLI, where its own `tools` field gates what's callable, AWF's enforcement is the Capability Guard + an Agent Manifest's `capabilities` allowlist (ADR-0002), a separate mechanism |

Trust status is not a file field, same reasoning as every other
config-root kind (Section 9.3): it lives in the `registry_index` DB
column; config-root objects carry none.

OAuth is out of scope. Live OAuth 2.0 (interactive sign-in, token storage,
automatic refresh) requires client-side infrastructure AWF doesn't have.
This schema expresses only static, secrets-table-backed credentials
(`env_secrets`/`header_secrets`). A server that requires live OAuth (e.g.
Sentry's remote server) cannot be configured through this schema until a
real client with token-refresh support exists.

`kind` is always the hardcoded literal `"mcp"` wherever it's referenced in
code - the same pattern every other self-describing kind already uses
(`"workflows"`, `"capabilities"`, `"agents"` are none of them derived from
file content or user input). No dynamic case-normalization is needed
anywhere, since the string is never derived, only ever a literal.

Two default servers ship under `config/app_registry/mcp/`:

- **`fetch`** - stdio, the official MCP reference server, no secret
  needed. Its own README documents that it can reach local/internal IP
  addresses; that risk is accepted as-is, not mitigated, since AWF's
  container-escalation isolation tier for untrusted content (Section 10.4)
  doesn't exist regardless of which server ships first.
- **`context7`** - http, `https://mcp.context7.com/mcp`, API key via
  `header_secrets`. Context7's stdio mode only takes its API key as a
  `--api-key` CLI argument, not an environment variable, in every
  documented client; the http mode is used instead so the key resolves
  through the schema's existing `header_secrets` mechanism rather than a
  third, arg-specific one.

`github` (remote hosted endpoint `https://api.githubcopilot.com/mcp/`,
works with a plain PAT, no Copilot subscription required, no Docker or
local process needed) and `playwright` (`npx @playwright/mcp@latest` -
Microsoft's official package; distinct from the similarly-named
third-party `@executeautomation/playwright-mcp-server`) are real,
documented options for a later pass, not shipped here. If `playwright` is
added later, its version stays unpinned, matching the upstream package's
own documented convention - this repo digest-pins its other published
objects, but upstream provides no better pin target for this one.

## Scope for implementation (future work, not started)

1. `registry/mcp_server.py` - parser/dataclass module, mirroring
   `capability_record.py`.
2. Ship the `fetch` and `context7` default definitions above.
3. `cli/core_ops.py` - `op_registry_publish`/`op_registry_validate` gain an
   `mcp` branch (`op_registry_list` already works generically for this
   kind).
4. No MCP client is built here - same boundary ADR-0002 drew around
   `AgentManifest.mcp`/`modelProfile`. Nothing in `backend/src` starts an
   MCP server process, speaks the 2026-07-28 wire protocol to it, or
   invokes one of its tools. A real client (likely via the official
   MCP Python SDK) is materially larger than "give this registry kind a
   schema" and is not part of this ADR.

## Consequences

- `/mcp` returns real content for the first time, once implemented -
  mirrors ADR-0002's `/agents` fix.
- An Agent Manifest's `mcp` field (ADR-0002) gains real registry objects to
  reference, but still has no consumer - resolving `mcp` refs into an
  actual live connection remains blocked on scope item 4, not on this ADR.
- The Capability Record identity type `mcp-tool` (Section 9.1) still has no
  real capability published against either shipped server's tools - a
  separate, later step, not part of this ADR.
