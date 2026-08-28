import pytest

from awf.registry.mcp_server import (
    McpServerValidationError,
    load_mcp_server,
    parse_mcp_server,
)


def minimal_stdio(**overrides):
    raw = {
        "name": "fetch",
        "version": "1.0.0",
        "type": "stdio",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-fetch"],
    }
    raw.update(overrides)
    return raw


def test_parse_minimal_stdio_server():
    server = parse_mcp_server(minimal_stdio())
    assert server.ref == "fetch@1.0.0"
    assert server.type == "stdio"
    assert server.command == "npx"
    assert server.args == ("-y", "@modelcontextprotocol/server-fetch")
    assert server.startup_timeout_sec == 10
    assert server.tool_timeout_sec == 60


def test_parse_rejects_invalid_type():
    with pytest.raises(McpServerValidationError):
        parse_mcp_server(minimal_stdio(type="carrier-pigeon"))


def test_parse_rejects_stdio_without_command():
    raw = minimal_stdio()
    del raw["command"]
    with pytest.raises(McpServerValidationError):
        parse_mcp_server(raw)


def test_parse_rejects_http_without_url():
    with pytest.raises(McpServerValidationError):
        parse_mcp_server({"name": "x", "version": "1.0.0", "type": "http"})


def test_parse_http_server_with_header_secrets():
    server = parse_mcp_server(
        {
            "name": "context7",
            "version": "1.0.0",
            "type": "http",
            "url": "https://mcp.context7.com/mcp",
            "header_secrets": {"CONTEXT7_API_KEY": "context7-api-key"},
        }
    )
    assert server.url == "https://mcp.context7.com/mcp"
    assert server.header_secrets == {"CONTEXT7_API_KEY": "context7-api-key"}


def test_load_real_file(tmp_path):
    path = tmp_path / "mcp" / "fetch" / "1.0.0.yaml"
    path.parent.mkdir(parents=True)
    path.write_text(
        "name: fetch\nversion: 1.0.0\ntype: stdio\ncommand: npx\nargs: ['-y', '@modelcontextprotocol/server-fetch']\n"
    )
    server = load_mcp_server(path)
    assert server.ref == "fetch@1.0.0"
