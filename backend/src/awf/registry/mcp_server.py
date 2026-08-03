"""MCP server registry schema, loading, and validation (ADR-0003).

AWF does not implement an MCP client - a `McpServer` object here is
rendered into whatever config format the invoking adapter reads, never
connected to directly (see `awf.mcp.render`).
"""

from dataclasses import dataclass, field
from pathlib import Path

import yaml

TYPES = ("stdio", "http")


class McpServerValidationError(ValueError):
    pass


@dataclass(frozen=True)
class McpServer:
    name: str
    version: str
    type: str
    command: str | None = None
    args: tuple[str, ...] = ()
    url: str | None = None
    env: dict = field(default_factory=dict)
    env_secrets: dict = field(default_factory=dict)
    headers: dict = field(default_factory=dict)
    header_secrets: dict = field(default_factory=dict)
    startup_timeout_sec: int = 10
    tool_timeout_sec: int = 60
    tools: tuple[str, ...] = ()
    resources: tuple[str, ...] = ()
    prompts: tuple[str, ...] = ()

    @property
    def ref(self) -> str:
        return f"{self.name}@{self.version}"


def _require(mapping: dict, key: str, context: str) -> object:
    if key not in mapping:
        raise McpServerValidationError(f"{context}: missing required field '{key}'")
    return mapping[key]


def parse_mcp_server(raw: dict) -> McpServer:
    server_type = _require(raw, "type", "mcp server")
    if server_type not in TYPES:
        raise McpServerValidationError(f"type '{server_type}' not in {TYPES}")

    if server_type == "stdio" and not raw.get("command"):
        raise McpServerValidationError("mcp server: type 'stdio' requires 'command'")
    if server_type == "http" and not raw.get("url"):
        raise McpServerValidationError("mcp server: type 'http' requires 'url'")

    return McpServer(
        name=_require(raw, "name", "mcp server"),
        version=_require(raw, "version", "mcp server"),
        type=server_type,
        command=raw.get("command"),
        args=tuple(raw.get("args", [])),
        url=raw.get("url"),
        env=raw.get("env", {}),
        env_secrets=raw.get("env_secrets", {}),
        headers=raw.get("headers", {}),
        header_secrets=raw.get("header_secrets", {}),
        startup_timeout_sec=int(raw.get("startup_timeout_sec", 10)),
        tool_timeout_sec=int(raw.get("tool_timeout_sec", 60)),
        tools=tuple(raw.get("tools", [])),
        resources=tuple(raw.get("resources", [])),
        prompts=tuple(raw.get("prompts", [])),
    )


def load_mcp_server(path: Path) -> McpServer:
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict):
        raise McpServerValidationError(f"{path}: mcp server must be a YAML mapping")
    return parse_mcp_server(raw)
