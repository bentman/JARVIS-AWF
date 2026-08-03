import json

import pytest

from awf.mcp.render import (
    McpRenderError,
    render_antigravity,
    render_claude_code,
    render_codex,
    render_copilot,
)
from awf.registry.mcp_server import parse_mcp_server


def fetch_server():
    return parse_mcp_server(
        {
            "name": "fetch",
            "version": "1.0.0",
            "type": "stdio",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-fetch"],
        }
    )


def context7_server():
    return parse_mcp_server(
        {
            "name": "context7",
            "version": "1.0.0",
            "type": "http",
            "url": "https://mcp.context7.com/mcp",
            "header_secrets": {"CONTEXT7_API_KEY": "context7-api-key"},
        }
    )


def test_no_servers_renders_nothing_for_every_adapter():
    for render in (render_claude_code, render_copilot, render_codex):
        result = render([], {})
        assert result.relative_path is None
        assert result.contents is None
        assert result.extra_args == ()
        assert result.env_overlay == {}


def test_claude_code_stdio_server_renders_mcp_json():
    result = render_claude_code([fetch_server()], {})

    assert result.relative_path == "mcp/claude-code.mcp.json"
    payload = json.loads(result.contents)
    assert payload["mcpServers"]["fetch"]["command"] == "npx"
    assert payload["mcpServers"]["fetch"]["args"] == ["-y", "@modelcontextprotocol/server-fetch"]
    assert result.extra_args == ("--mcp-config", "mcp/claude-code.mcp.json", "--strict-mcp-config")
    assert result.env_overlay == {}


def test_claude_code_http_server_uses_var_reference_never_the_literal_secret():
    result = render_claude_code([context7_server()], {"context7-api-key": "sk-real-secret-value"})

    payload = json.loads(result.contents)
    header_value = payload["mcpServers"]["context7"]["headers"]["CONTEXT7_API_KEY"]
    assert header_value == "${AWF_MCP_CONTEXT7_CONTEXT7_API_KEY}"
    assert "sk-real-secret-value" not in result.contents
    assert result.env_overlay == {"AWF_MCP_CONTEXT7_CONTEXT7_API_KEY": "sk-real-secret-value"}


def test_copilot_renders_local_type_and_additional_mcp_config_flag():
    result = render_copilot([fetch_server()], {})

    assert result.relative_path == "mcp/copilot.mcp-config.json"
    payload = json.loads(result.contents)
    assert payload["mcpServers"]["fetch"]["type"] == "local"
    assert result.extra_args == ("--additional-mcp-config", "@mcp/copilot.mcp-config.json")


def test_codex_renders_dash_c_overrides_with_no_file():
    result = render_codex([fetch_server()], {})

    assert result.relative_path is None
    assert result.contents is None
    assert "-c" in result.extra_args
    joined = " ".join(result.extra_args)
    assert 'mcp_servers.fetch.command="npx"' in joined
    assert "mcp_servers.fetch.args=" in joined


def test_codex_http_secret_uses_env_http_headers_reference_never_the_literal():
    result = render_codex([context7_server()], {"context7-api-key": "sk-real-secret-value"})

    joined = " ".join(result.extra_args)
    assert "sk-real-secret-value" not in joined
    assert "mcp_servers.context7.env_http_headers.CONTEXT7_API_KEY=" in joined
    assert result.env_overlay == {"AWF_MCP_CONTEXT7_CONTEXT7_API_KEY": "sk-real-secret-value"}


def test_antigravity_raises_when_servers_given_but_is_a_noop_when_empty():
    assert render_antigravity([], {}).relative_path is None
    with pytest.raises(McpRenderError):
        render_antigravity([fetch_server()], {})
