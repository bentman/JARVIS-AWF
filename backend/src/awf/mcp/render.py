"""Adapter-specific MCP config rendering (ADR-0003).

AWF has no MCP client - each function here renders a list of `McpServer`
registry objects into the shape the named adapter's own client reads, and
returns what the caller needs to actually invoke the adapter with it:
an optional file to write, extra CLI arguments, and an environment overlay
of resolved secret plaintext to inject into the adapter's own subprocess
environment (never into the rendered file itself).

Pure functions: no subprocess, no filesystem access. `engine.agent_step`
writes the file (if any) and injects the environment overlay.

Per-adapter mechanism:
  - Claude Code: `--mcp-config <path> --strict-mcp-config` - a
    non-interactive flag that skips the project-trust prompt.
  - Codex CLI: repeated `-c mcp_servers.<name>.<field>=<value>` overrides
    (the same override mechanism `adapters/codex_cli.py` uses for
    `sandbox_mode`/`approval_policy`) - no separate file.
  - GitHub Copilot CLI: `--additional-mcp-config @<path>` augments
    `~/.copilot/mcp-config.json` for the invoked session.
  - Antigravity (`agy`): has no per-invocation flag and only reads MCP
    servers from `~/.gemini/config/mcp_config.json` in the operator's home
    directory, which is never written to directly. Instead, each
    invocation gets its own throwaway `$HOME`
    (`cache/sandbox/<run_id>/agy_home/`, never the operator's real home):
    `.gemini/antigravity-cli/antigravity-oauth-token` is copied in
    read-only from the real home, and
    `.gemini/antigravity-cli/settings.json` /
    `.gemini/config/mcp_config.json` are written fresh, scoped to this Run
    only. `settings.json`'s `permissions.allow` needs an `mcp(*)` entry,
    since MCP tool calls are denied by default in headless mode and no
    narrower per-server/per-tool allow syntax exists. This never touches
    the operator's persistent `~/.gemini/antigravity-cli/settings.json` -
    the copy is scoped to the scratch `$HOME`.
"""

import json
from dataclasses import dataclass, field

from awf.registry.mcp_server import McpServer

# No narrower per-server syntax (e.g. "mcp(context7)") was found to work
# against the installed CLI - broad, but scoped to the Run's own scratch
# $HOME, never the operator's persistent settings.
ANTIGRAVITY_MCP_PERMISSION_ALLOW = ("mcp(*)",)
ANTIGRAVITY_OAUTH_TOKEN_RELATIVE_PATH = ".gemini/antigravity-cli/antigravity-oauth-token"


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


def render_claude_code(servers: list[McpServer], resolved_secrets: dict[str, str]) -> RenderedMcpConfig:
    if not servers:
        return RenderedMcpConfig(relative_path=None, contents=None)

    mcp_servers = {}
    for server in servers:
        if server.type == "stdio":
            entry = {"type": "stdio", "command": server.command, "args": list(server.args)}
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
    path = "mcp/claude-code.mcp.json"
    return RenderedMcpConfig(
        relative_path=path,
        contents=contents,
        extra_args=("--mcp-config", path, "--strict-mcp-config"),
        env_overlay=_env_overlay_for(servers, resolved_secrets),
    )


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
        extra_args=(f"--additional-mcp-config", f"@{path}"),
        env_overlay=_env_overlay_for(servers, resolved_secrets),
    )


def render_codex(servers: list[McpServer], resolved_secrets: dict[str, str]) -> RenderedMcpConfig:
    if not servers:
        return RenderedMcpConfig(relative_path=None, contents=None)

    extra_args: list[str] = []
    for server in servers:
        prefix = f"mcp_servers.{server.name}"
        if server.type == "stdio":
            extra_args += ["-c", f'{prefix}.command="{server.command}"']
            args_toml = json.dumps(list(server.args))
            extra_args += ["-c", f"{prefix}.args={args_toml}"]
            for key, value in server.env.items():
                extra_args += ["-c", f'{prefix}.env.{key}="{value}"']
            if server.env_secrets:
                env_var_names = [_secret_env_var_name(server.name, k) for k in server.env_secrets]
                extra_args += ["-c", f"{prefix}.env_vars={json.dumps(env_var_names)}"]
        else:
            extra_args += ["-c", f'{prefix}.url="{server.url}"']
            for key, value in server.headers.items():
                extra_args += ["-c", f'{prefix}.http_headers.{key}="{value}"']
            for header_name in server.header_secrets:
                env_var_name = _secret_env_var_name(server.name, header_name)
                extra_args += ["-c", f'{prefix}.env_http_headers.{header_name}="{env_var_name}"']
        extra_args += ["-c", f"{prefix}.startup_timeout_sec={server.startup_timeout_sec}"]
        extra_args += ["-c", f"{prefix}.tool_timeout_sec={server.tool_timeout_sec}"]

    return RenderedMcpConfig(
        relative_path=None,
        contents=None,
        extra_args=tuple(extra_args),
        env_overlay=_env_overlay_for(servers, resolved_secrets),
    )


def render_antigravity(servers: list[McpServer], resolved_secrets: dict[str, str]) -> RenderedMcpConfig:
    if not servers:
        return RenderedMcpConfig(relative_path=None, contents=None)

    mcp_servers = {}
    for server in servers:
        if server.type == "stdio":
            entry = {"command": server.command, "args": list(server.args)}
            env = dict(server.env)
            for env_var in server.env_secrets:
                env[env_var] = f"${{{_secret_env_var_name(server.name, env_var)}}}"
            if env:
                entry["env"] = env
        else:
            entry = {"url": server.url}
            headers = dict(server.headers)
            for header_name in server.header_secrets:
                headers[header_name] = f"${{{_secret_env_var_name(server.name, header_name)}}}"
            if headers:
                entry["headers"] = headers
        mcp_servers[server.name] = entry

    mcp_config_contents = json.dumps({"mcpServers": mcp_servers}, indent=2)
    settings_contents = json.dumps(
        {"permissions": {"allow": list(ANTIGRAVITY_MCP_PERMISSION_ALLOW)}}, indent=2
    )

    return RenderedMcpConfig(
        relative_path=None,
        contents=None,
        env_overlay=_env_overlay_for(servers, resolved_secrets),
        home_relative_files={
            ".gemini/config/mcp_config.json": mcp_config_contents,
            ".gemini/antigravity-cli/settings.json": settings_contents,
        },
        home_copy_paths=(ANTIGRAVITY_OAUTH_TOKEN_RELATIVE_PATH,),
    )


RENDERERS = {
    "claude-code": render_claude_code,
    "codex": render_codex,
    "antigravity": render_antigravity,
    "copilot": render_copilot,
}
