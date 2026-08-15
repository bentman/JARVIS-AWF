"""Adapter-specific MCP config rendering (ADR-0003).

AWF has no MCP client - each function here renders a list of `McpServer`
registry objects into the shape the named adapter's own client reads, and
returns what the caller needs to actually invoke the adapter with it:
an optional file to write, extra CLI arguments, and an environment overlay
of resolved secret plaintext to inject into the adapter's own subprocess
environment (never into the rendered file itself).

Pure functions: no subprocess, no filesystem access. `engine.agent_step`
writes the file (if any) and injects the environment overlay.

Only adapters in `engine.agent_step.GUARDED_MCP_ADAPTERS` are reachable
through `_apply_mcp`; all others are rejected with POLICY_DENIED before the
renderer lookup. RENDERERS is kept equal to that set. See ADR-0003 for the
full per-adapter design that was narrowed to this guarded subset.

  - GitHub Copilot CLI: `--additional-mcp-config @<path>` augments
    `~/.copilot/mcp-config.json` for the invoked session.
"""

import json
from dataclasses import dataclass, field

from awf.registry.mcp_server import McpServer


@dataclass(frozen=True)
class RenderedMcpConfig:
    relative_path: str | None
    contents: str | None
    extra_args: tuple[str, ...] = ()
    env_overlay: dict = field(default_factory=dict)
    home_relative_files: dict = field(default_factory=dict)
    home_copy_paths: tuple[str, ...] = ()


def _secret_env_var_name(server_name: str, key: str) -> str:
    # Namespaced so two servers referencing a same-named secret key (e.g.
    # both calling it API_KEY) can't collide in the adapter's own process
    # environment.
    slug = server_name.upper().replace("-", "_")
    key_slug = key.upper().replace("-", "_")
    return f"AWF_MCP_{slug}_{key_slug}"


def _env_overlay_for(servers: list[McpServer], resolved_secrets: dict[str, str]) -> dict:
    overlay = {}
    for server in servers:
        for env_var, secret_name in server.env_secrets.items():
            overlay[_secret_env_var_name(server.name, env_var)] = resolved_secrets[secret_name]
        for header_name, secret_name in server.header_secrets.items():
            overlay[_secret_env_var_name(server.name, header_name)] = resolved_secrets[secret_name]
    return overlay


def render_copilot(servers: list[McpServer], resolved_secrets: dict[str, str]) -> RenderedMcpConfig:
    if not servers:
        return RenderedMcpConfig(relative_path=None, contents=None)

    mcp_servers = {}
    for server in servers:
        if server.type == "stdio":
            entry = {"type": "local", "command": server.command, "args": list(server.args)}
            env = dict(server.env)
            for env_var in server.env_secrets:
                env[env_var] = f"${{{_secret_env_var_name(server.name, env_var)}}}"
            if env:
                entry["env"] = env
        else:
            entry = {"type": "http", "url": server.url}
            headers = dict(server.headers)
            for header_name in server.header_secrets:
                headers[header_name] = f"${{{_secret_env_var_name(server.name, header_name)}}}"
            if headers:
                entry["headers"] = headers
        mcp_servers[server.name] = entry

    contents = json.dumps({"mcpServers": mcp_servers}, indent=2)
    path = "mcp/copilot.mcp-config.json"
    return RenderedMcpConfig(
        relative_path=path,
        contents=contents,
        extra_args=("--additional-mcp-config", f"@{path}"),
        env_overlay=_env_overlay_for(servers, resolved_secrets),
    )


RENDERERS = {
    "copilot": render_copilot,
}
