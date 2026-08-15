import json

from awf.mcp.render import RENDERERS, render_copilot
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


def test_renderers_match_guarded_mcp_adapters():
    from awf.engine.agent_step import GUARDED_MCP_ADAPTERS

    assert set(RENDERERS) == GUARDED_MCP_ADAPTERS


def test_no_servers_renders_nothing_for_copilot():
    result = render_copilot([], {})
    assert result.relative_path is None
    assert result.contents is None
    assert result.extra_args == ()
    assert result.env_overlay == {}
    assert result.home_relative_files == {}
    assert result.home_copy_paths == ()


def test_copilot_renders_local_type_and_additional_mcp_config_flag():
    result = render_copilot([fetch_server()], {})

    assert result.relative_path == "mcp/copilot.mcp-config.json"
    payload = json.loads(result.contents)
    assert payload["mcpServers"]["fetch"]["type"] == "local"
    assert result.extra_args == ("--additional-mcp-config", "@mcp/copilot.mcp-config.json")
