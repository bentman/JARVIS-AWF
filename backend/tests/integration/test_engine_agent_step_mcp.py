import json

import pytest
from backend.tests.support import run_git
from cryptography.fernet import Fernet

from awf.adapters.base import AgentInvocation, AgentResult, AgentStatus
from awf.db.bootstrap import init_db
from awf.db.connection import get_connection
from awf.engine.agent_step import AgentStepError, run_agent_step
from awf.engine.run import create_run, create_step
from awf.isolation.worktree import create_worktree


@pytest.fixture
def repo_and_worktree(tmp_path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    run_git(["init", "-q"], cwd=repo_root)
    run_git(["config", "user.email", "test@example.com"], cwd=repo_root)
    run_git(["config", "user.name", "Test"], cwd=repo_root)
    (repo_root / "README.md").write_text("hello\n")
    run_git(["add", "-A"], cwd=repo_root)
    run_git(["commit", "-q", "-m", "init"], cwd=repo_root)

    worktree = create_worktree(repo_root, "run-1")
    return repo_root, worktree


@pytest.fixture
def conn(tmp_path):
    db_path = tmp_path / "awf.db"
    init_db(db_path)
    connection = get_connection(db_path)
    create_run(connection, run_id="run-1", workflow_ref="agent-node@1.0.0")
    create_step(connection, step_id="step-1", run_id="run-1", node_id="agent-node")
    return connection


def _write_fetch_server(repo_root):
    server_dir = repo_root / "config" / "app_registry" / "mcp" / "fetch"
    server_dir.mkdir(parents=True)
    (server_dir / "1.0.0.yaml").write_text(
        "name: fetch\nversion: 1.0.0\ntype: stdio\ncommand: npx\nargs: ['-y', '@modelcontextprotocol/server-fetch']\n"
    )


def _write_fetch_tool_capability(repo_root, name="fetch_url"):
    capability_dir = repo_root / "config" / "app_registry" / "capabilities" / name
    capability_dir.mkdir(parents=True)
    (capability_dir / "1.0.0.yaml").write_text(
        f"identity: {{type: mcp-tool, provider: fetch, name: {name}, version: 1.0.0}}\n"
        'schema: {input: "", output: ""}\n'
        "effects: {operation: communicate, reversible: false, idempotent: false, external_side_effect: true}\n"
        "risk_class: R1\n"
        "approval: per-invocation\n"
    )


def test_guarded_mcp_ref_renders_config_and_passes_extra_args_to_adapter(repo_and_worktree, conn):
    repo_root, worktree = repo_and_worktree
    _write_fetch_server(repo_root)
    seen = {}

    def adapter_fn(invocation: AgentInvocation) -> AgentResult:
        seen["invocation"] = invocation
        return AgentResult(status=AgentStatus.COMPLETED, output={}, termination_reason="success")

    invocation = AgentInvocation(objective="use fetch", inputs={}, workspace_root=worktree)
    run_agent_step(
        conn,
        step_id="step-1",
        run_id="run-1",
        worktree_path=worktree,
        invocation=invocation,
        adapter_fn=adapter_fn,
        commit_message="agent: used fetch",
        actor="copilot",
        mcp_refs=["fetch@1.0.0"],
        repo_root=repo_root,
    )

    rendered_invocation = seen["invocation"]
    assert "--additional-mcp-config" in rendered_invocation.constraints["mcp_extra_args"]
    assert (worktree / "mcp" / "copilot.mcp-config.json").is_file()

    event = conn.execute("SELECT new_status, payload_json FROM events WHERE new_status = 'mcp_rendered'").fetchone()
    assert event is not None
    assert "fetch@1.0.0" in event["payload_json"]


def test_mcp_server_with_declared_tools_requires_all_tools_to_have_allowed_capabilities(repo_and_worktree, conn):
    repo_root, worktree = repo_and_worktree
    server_dir = repo_root / "config" / "app_registry" / "mcp" / "fetch"
    server_dir.mkdir(parents=True)
    (server_dir / "1.0.0.yaml").write_text(
        "name: fetch\nversion: 1.0.0\ntype: stdio\ncommand: npx\n"
        "args: ['-y', '@modelcontextprotocol/server-fetch']\ntools: [fetch_url, scrape_url]\n"
    )
    seen = {}

    def adapter_fn(invocation: AgentInvocation) -> AgentResult:
        seen["invocation"] = invocation
        return AgentResult(status=AgentStatus.COMPLETED, output={}, termination_reason="success")

    run_agent_step(
        conn,
        step_id="step-1",
        run_id="run-1",
        worktree_path=worktree,
        invocation=AgentInvocation(objective="use fetch", inputs={}, workspace_root=worktree),
        adapter_fn=adapter_fn,
        commit_message="agent: used fetch",
        actor="copilot",
        mcp_refs=["fetch@1.0.0"],
        agent_allowlist=["fetch_url@1.0.0"],
        repo_root=repo_root,
    )

    assert "mcp_extra_args" not in seen["invocation"].constraints
    assert not (worktree / "mcp" / "claude-code.mcp.json").exists()
    assert conn.execute("SELECT 1 FROM events WHERE new_status = 'mcp_rendered'").fetchone() is None

    _write_fetch_tool_capability(repo_root, "fetch_url")
    _write_fetch_tool_capability(repo_root, "scrape_url")
    create_step(conn, step_id="step-2", run_id="run-1", node_id="agent-node-2")
    run_agent_step(
        conn,
        step_id="step-2",
        run_id="run-1",
        worktree_path=worktree,
        invocation=AgentInvocation(objective="use fetch", inputs={}, workspace_root=worktree),
        adapter_fn=adapter_fn,
        commit_message="agent: used fetch",
        actor="copilot",
        mcp_refs=["fetch@1.0.0"],
        agent_allowlist=["fetch_url@1.0.0", "scrape_url@1.0.0"],
        repo_root=repo_root,
    )

    rendered_file = worktree / "mcp" / "copilot.mcp-config.json"
    rendered = json.loads(rendered_file.read_text())
    assert rendered["mcpServers"]["fetch"]["command"] == "npx"
    event = conn.execute("SELECT payload_json FROM events WHERE new_status = 'mcp_rendered'").fetchone()
    payload = json.loads(event["payload_json"])
    assert payload["servers"][0]["tools"] == ["fetch_url", "scrape_url"]
    assert payload["servers"][0]["capabilities"] == ["fetch_url@1.0.0", "scrape_url@1.0.0"]


def test_no_mcp_refs_renders_nothing_and_labels_user_objective(repo_and_worktree, conn):
    repo_root, worktree = repo_and_worktree
    seen = {}

    def adapter_fn(invocation: AgentInvocation) -> AgentResult:
        seen["invocation"] = invocation
        return AgentResult(status=AgentStatus.COMPLETED, output={}, termination_reason="success")

    invocation = AgentInvocation(objective="do nothing special", inputs={}, workspace_root=worktree)
    run_agent_step(
        conn,
        step_id="step-1",
        run_id="run-1",
        worktree_path=worktree,
        invocation=invocation,
        adapter_fn=adapter_fn,
        commit_message="agent: plain",
        actor="claude-code",
        repo_root=repo_root,
    )

    assert seen["invocation"] is not invocation
    assert seen["invocation"].objective == "[user/input, untrusted]\ndo nothing special"
    assert not (worktree / "mcp").exists()
    assert conn.execute("SELECT 1 FROM events WHERE new_status = 'mcp_rendered'").fetchone() is None


def test_quarantined_mcp_ref_is_refused_before_adapter_runs(repo_and_worktree, conn):
    repo_root, worktree = repo_and_worktree
    server_dir = repo_root / "data" / "registry" / "mcp" / "fetch"
    server_dir.mkdir(parents=True)
    server_path = server_dir / "1.0.0.yaml"
    server_path.write_text(
        "name: fetch\nversion: 1.0.0\ntype: stdio\ncommand: npx\nargs: ['-y', '@modelcontextprotocol/server-fetch']\n"
    )
    conn.execute(
        "INSERT INTO registry_index (kind, name, version, digest, source, path, trust_status, indexed_at) "
        "VALUES ('mcp', 'fetch', '1.0.0', 'x', 'data', ?, 'quarantined', '2026-01-01T00:00:00Z')",
        (str(server_path.relative_to(repo_root)),),
    )
    conn.commit()
    seen = {}

    def adapter_fn(invocation: AgentInvocation) -> AgentResult:
        seen["invocation"] = invocation
        return AgentResult(status=AgentStatus.COMPLETED, output={}, termination_reason="success")

    invocation = AgentInvocation(objective="use fetch", inputs={}, workspace_root=worktree)
    run_agent_step(
        conn,
        step_id="step-1",
        run_id="run-1",
        worktree_path=worktree,
        invocation=invocation,
        adapter_fn=adapter_fn,
        commit_message="agent: refused",
        actor="copilot",
        mcp_refs=["fetch@1.0.0"],
        repo_root=repo_root,
    )

    assert seen["invocation"] is not invocation
    assert seen["invocation"].objective == "[user/input, untrusted]\nuse fetch"
    assert not (worktree / "mcp").exists()
    assert conn.execute("SELECT 1 FROM events WHERE new_status = 'mcp_rendered'").fetchone() is None


def test_unguarded_adapter_mcp_ref_is_denied_before_adapter_runs(repo_and_worktree, conn):
    repo_root, worktree = repo_and_worktree
    _write_fetch_server(repo_root)
    seen = []

    def adapter_fn(invocation: AgentInvocation) -> AgentResult:
        seen.append(invocation)
        return AgentResult(status=AgentStatus.COMPLETED, output={}, termination_reason="success")

    invocation = AgentInvocation(objective="use fetch", inputs={}, workspace_root=worktree)
    with pytest.raises(AgentStepError, match="pre-tool Guard hook"):
        run_agent_step(
            conn,
            step_id="step-1",
            run_id="run-1",
            worktree_path=worktree,
            invocation=invocation,
            adapter_fn=adapter_fn,
            commit_message="agent: denied fetch via antigravity",
            actor="antigravity",
            mcp_refs=["fetch@1.0.0"],
            repo_root=repo_root,
        )

    assert seen == []


def test_mcp_secret_reaches_env_overlay_never_the_rendered_file(repo_and_worktree, conn):
    repo_root, worktree = repo_and_worktree
    key = Fernet.generate_key().decode("ascii")
    (repo_root / ".env").write_text(f"AWF_SECRET_KEY={key}\n")
    from awf.secrets.store import set_secret

    set_secret(conn, "context7-api-key", "sk-real-secret-value", key.encode("ascii"))

    server_dir = repo_root / "config" / "app_registry" / "mcp" / "context7"
    server_dir.mkdir(parents=True)
    (server_dir / "1.0.0.yaml").write_text(
        "name: context7\nversion: 1.0.0\ntype: http\nurl: https://mcp.context7.com/mcp\n"
        "header_secrets:\n  CONTEXT7_API_KEY: context7-api-key\n"
    )
    seen = {}

    def adapter_fn(invocation: AgentInvocation) -> AgentResult:
        seen["invocation"] = invocation
        return AgentResult(status=AgentStatus.COMPLETED, output={}, termination_reason="success")

    invocation = AgentInvocation(objective="use context7", inputs={}, workspace_root=worktree)
    run_agent_step(
        conn,
        step_id="step-1",
        run_id="run-1",
        worktree_path=worktree,
        invocation=invocation,
        adapter_fn=adapter_fn,
        commit_message="agent: used context7",
        actor="copilot",
        mcp_refs=["context7@1.0.0"],
        repo_root=repo_root,
    )

    rendered_file = (worktree / "mcp" / "copilot.mcp-config.json").read_text()
    assert "sk-real-secret-value" not in rendered_file
    overlay = seen["invocation"].constraints["mcp_env_overlay"]
    assert overlay == {"AWF_MCP_CONTEXT7_CONTEXT7_API_KEY": "sk-real-secret-value"}


def test_cline_mcp_ref_is_denied_before_adapter_runs(repo_and_worktree, conn):
    repo_root, worktree = repo_and_worktree
    _write_fetch_server(repo_root)
    seen = []

    def adapter_fn(invocation: AgentInvocation) -> AgentResult:
        seen.append(invocation)
        return AgentResult(status=AgentStatus.COMPLETED, output={}, termination_reason="success")

    invocation = AgentInvocation(objective="use fetch", inputs={}, workspace_root=worktree)
    with pytest.raises(AgentStepError, match="pre-tool Guard hook"):
        run_agent_step(
            conn,
            step_id="step-1",
            run_id="run-1",
            worktree_path=worktree,
            invocation=invocation,
            adapter_fn=adapter_fn,
            commit_message="agent: denied fetch via cline",
            actor="cline",
            mcp_refs=["fetch@1.0.0"],
            repo_root=repo_root,
        )

    assert seen == []
