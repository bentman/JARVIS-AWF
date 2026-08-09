import pytest

from awf.registry.agent_manifest import (
    AgentManifestValidationError,
    load_agent_manifest,
    parse_agent_manifest,
)


@pytest.fixture
def agents_root(repo_root):
    return repo_root / "config" / "app_registry" / "agents"


def minimal_raw(**overrides):
    raw = {
        "name": "demo",
        "version": "1.0.0",
        "description": "A demo agent.",
        "adapter": "claude-code",
    }
    raw.update(overrides)
    return raw


def test_parse_minimal_manifest():
    manifest = parse_agent_manifest(minimal_raw())
    assert manifest.ref == "demo@1.0.0"
    assert manifest.adapter == "claude-code"
    assert manifest.capabilities == ()
    assert manifest.role is None


def test_parse_rejects_missing_adapter():
    raw = minimal_raw()
    del raw["adapter"]
    with pytest.raises(AgentManifestValidationError):
        parse_agent_manifest(raw)


def test_parse_rejects_invalid_role():
    with pytest.raises(AgentManifestValidationError):
        parse_agent_manifest(minimal_raw(role="not-a-real-role"))


def test_parse_accepts_valid_role_and_capabilities():
    manifest = parse_agent_manifest(minimal_raw(role="verifier", capabilities=["read_file@1.0.0", "git_push@1.0.0"]))
    assert manifest.role == "verifier"
    assert manifest.capabilities == ("read_file@1.0.0", "git_push@1.0.0")


def test_parse_captures_optional_voice_persona_mcp_and_model_profile():
    manifest = parse_agent_manifest(
        minimal_raw(
            voice="builder@1.0.0",
            persona="builder@1.0.0",
            mcp=["some-server@1.0.0"],
            modelProfile="example-openai-adversary@1.0.0",
        )
    )
    assert manifest.voice == "builder@1.0.0"
    assert manifest.persona == "builder@1.0.0"
    assert manifest.mcp == ("some-server@1.0.0",)
    assert manifest.model_profile == "example-openai-adversary@1.0.0"


def test_split_frontmatter_requires_opening_and_closing_delimiters(tmp_path):
    bad = tmp_path / "bad.md"
    bad.write_text("name: demo\n")
    with pytest.raises(AgentManifestValidationError):
        load_agent_manifest(bad)


def test_load_real_file_carries_instructions_body(tmp_path):
    path = tmp_path / "demo.md"
    path.write_text(
        "---\n"
        "name: demo\n"
        "version: 1.0.0\n"
        "description: A demo agent.\n"
        "adapter: claude-code\n"
        "---\n"
        "\n"
        "You are the demo agent. Be helpful.\n"
    )
    manifest = load_agent_manifest(path)
    assert manifest.instructions == "You are the demo agent. Be helpful."


@pytest.mark.parametrize(
    "name,expected_adapter,expected_role",
    [
        ("builder", "claude-code", "builder"),
        ("verifier", "codex", "verifier"),
        ("adversary", "antigravity", "adversary"),
    ],
)
def test_load_real_shipped_default_manifest(name, expected_adapter, expected_role, agents_root):
    manifest = load_agent_manifest(agents_root / name / "1.0.0.md")
    assert manifest.name == name
    assert manifest.adapter == expected_adapter
    assert manifest.role == expected_role
    assert manifest.voice == f"{name}@1.0.0"
    assert manifest.persona == f"{name}@1.0.0"
    assert manifest.instructions
