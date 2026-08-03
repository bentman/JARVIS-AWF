# ADR-0003: MCP server registry schema and default servers

## Status

Proposed — scope/tracking only. Not implemented.

## Context

Section 9.3 already specifies more about the `MCP` registry kind than it
did for Agent Manifests before ADR-0002: each `MCP/<name>/<version>.yaml`
"declares how AWF starts or connects to that server (transport,
command/args or URL, required environment references), the
tools/resources/prompts it exposes (by name, for cross-referencing with
Capability Records), and — in `data/registry/` — its trust status." Section
3 pins the protocol itself: **MCP spec 2026-07-28** - a stateless core (the
old initialize/notifications handshake is gone; every request now carries
its own protocol version and capabilities), a versioned Extensions
framework (Tasks, MCP Apps), and an explicit deprecation note: Roots,
Sampling, and Logging "do not build against them."

Inspecting the codebase found the same shape of gap ADR-0002 found for
Agent Manifests, one phase earlier in maturity:

- `config/app_registry/MCP/` and `data/registry/MCP/` are empty placeholder
  directories (`.gitkeep` only) - no schema module exists.
- The only reference to MCP anywhere in `backend/src` is
  `capability_record.py`'s `IDENTITY_TYPES` enum including `"mcp-tool"` -
  parsed, never connected to anything. There is no MCP client
  implementation at all.
- `/mcp` (TUI) and `awf/registry.list` for kind `MCP` are wired end-to-end
  (the generic `.yaml` listing path already works for this kind, no
  special-casing needed) but permanently return `[]`.
- `AgentManifest.mcp` (ADR-0002) is parsed and stored but has no refs to
  resolve against and no consumer.

A survey of the same four tools surveyed for ADR-0002 found an even more
tightly converged shape than Agent Manifests had: Claude Code (`.mcp.json`),
Codex CLI (`~/.codex/config.toml` `[mcp_servers.*]`), GitHub Copilot CLI
(`mcp-config.json`), and Antigravity (`mcp_config.json`) all independently
use a per-server entry keyed by name, with `command`+`args`+`env` for
local/stdio servers or `url`/`serverUrl`+`headers` for remote/HTTP servers,
an explicit transport discriminator, and secrets always referenced by name
(never embedded - every tool uses `${VAR}`-style substitution; AWF's own
secrets table is the equivalent mechanism).

A separate survey of which MCP servers are actually installed in practice
for coding-agent use found strong, repeated convergence on four: the
**GitHub MCP server** (repos/issues/PRs - built into Copilot CLI by
default, cited everywhere), the **Playwright MCP server** (Microsoft's
official browser-automation server - the single most-used MCP server in
the ecosystem per multiple 2026 rankings), the official **Fetch**
reference server (simple web content retrieval, no API key, part of
`modelcontextprotocol/servers`), and **Context7** (Upstash's live,
version-accurate library-documentation lookup server - named specifically
alongside GitHub and Playwright as one of the "highest-value first
installs for coding agents"). One source names "Filesystem + GitHub +
Context7 + Playwright" as the community's own "starter four" outright;
GitHub and Playwright appear in literally every surveyed source. Fetch is
the lowest-friction "basic search/lookup" capability that needs no paid
API key or account, unlike Brave/Exa-style search servers.

## Decision

Adopt the converged shape: plain YAML at
`config/app_registry/MCP/<name>/<version>.yaml` (and `data/registry/MCP/`
for operator additions - `MCP` is not in `DATA_ONLY_KINDS`, same two-root
resolution as Capability Records). No Markdown body - unlike an Agent
Manifest, an MCP server definition has no "system prompt" concept.

| Field | Required | Shape | Notes |
|---|---|---|---|
| `name`, `version` | yes | string | self-describing, matches Capability Record's pattern |
| `transport` | yes | `stdio` \| `http` | matches every surveyed tool's discriminator |
| `command`, `args` | required if `stdio` | string, list of strings | matches the converged shape exactly |
| `url`, `headers` | required if `http` | string, list of `{name, secretName}` | `headers` values are never literal - always a secrets-table reference, matching Section 11's Model Profile `api_key_secret_name` pattern |
| `env` | no, default `[]` | list of `{name, secretName}` | environment variables the server needs, resolved through the secrets table by name - never a literal value in the file, same rule Section 11 already states for Model Profile API keys |
| `tools`, `resources`, `prompts` | no, default `[]` | list of strings | exposed names, for Capability Record cross-referencing (§9.3's own wording) |
| `protocolVersion` | no, default `2026-07-28` | string | AWF-specific addition, given the spec's own deprecation note - lets a future upgrade be a deliberate per-server bump, not silent drift |

Trust status is **not** a file field, same reasoning as every other
config-root kind: it lives in the `registry_index` DB column, and
`config/app_registry/` objects carry none because inclusion in the
repository is the review (§9.3).

**Four real default servers ship under `config/app_registry/MCP/`:**
`github` (stdio, official GitHub MCP server, requires a `GITHUB_TOKEN`
secret), `playwright` (stdio, `npx @playwright/mcp@latest`, no secret
needed), `fetch` (stdio, official reference Fetch server, no secret
needed), `context7` (stdio, `npx @upstash/context7-mcp`, requires a
`CONTEXT7_API_KEY` secret). All four are real, commonly-deployed servers,
not invented examples. Three need no paid API account at all; Context7's
free tier still needs a (free) API key, tracked the same way GitHub's
token is - as a named secrets-table reference, never a literal value in
the file.

## Scope for implementation (future work, not started)

1. `registry/mcp_server.py` - parser/dataclass module, mirroring
   `capability_record.py`.
2. Ship the four real default server definitions above. Context7's
   documented setup passes its API key via a `--api-key` CLI flag rather
   than confirmed to also accept an environment variable - if no env-var
   form exists at implementation time, its definition passes the resolved
   secret as an `args` entry instead of via `env`, still resolved by name
   through the secrets table, never literally in the file.
3. `cli/core_ops.py` - `op_registry_publish`/`op_registry_validate` gain an
   MCP branch (`op_registry_list` already works generically for this kind).
4. No MCP client is built in this pass - same boundary ADR-0002 drew around
   `AgentManifest.mcp`/`modelProfile`: the schema and registry plumbing
   exist and are real, but nothing in `backend/src` yet starts an MCP
   server process, speaks the 2026-07-28 wire protocol to it, or invokes
   one of its tools. That is a materially larger piece of work (a real
   client implementation, likely via the official MCP Python SDK) than
   "give this registry kind a schema," and is intentionally out of scope
   here.

## Consequences

- `/mcp` returns real content for the first time, once implemented -
  mirrors ADR-0002's `/agents` fix.
- An Agent Manifest's `mcp` field (ADR-0002) gains real registry objects to
  reference, but still has no consumer - resolving `mcp` refs into an
  actual live connection remains blocked on item 4 above, not on this ADR.
- The Capability Record identity type `mcp-tool` (§9.1) still has no real
  capability published against any of these three servers' tools - that is
  a separate, later step (publishing real Capability Records for e.g.
  `github.create_issue`), not part of this ADR.
