import pytest
from backend.tests.support import run_git

from awf.adapters.base import AgentInvocation, AgentResult, AgentStatus
from awf.db.bootstrap import init_db
from awf.db.connection import get_connection
from awf.engine.agent_step import run_agent_step
from awf.engine.run import create_run, create_step
from awf.isolation.worktree import create_worktree
from awf.registry.agent_manifest import SkillRef


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


def _write_demo_skill(repo_root, body="Do the demo thing."):
    skill_dir = repo_root / "config" / "app_registry" / "skills" / "demo-skill" / "1.0.0"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(f"---\nname: demo-skill\ndescription: A minimal demo skill.\n---\n\n{body}\n")
    return skill_dir


def _run(
    conn, worktree, repo_root, adapter_fn, *, actor="claude-code", instructions="", skill_refs=None, persona_ref=None
):
    invocation = AgentInvocation(objective="the real task", inputs={}, workspace_root=worktree)
    return run_agent_step(
        conn,
        step_id="step-1",
        run_id="run-1",
        worktree_path=worktree,
        invocation=invocation,
        adapter_fn=adapter_fn,
        commit_message="agent: skills test",
        actor=actor,
        instructions=instructions,
        skill_refs=skill_refs or [],
        persona_ref=persona_ref,
        repo_root=repo_root,
    )


def test_default_tier_folds_body_into_objective_and_writes_no_directory(repo_and_worktree, conn):
    repo_root, worktree = repo_and_worktree
    _write_demo_skill(repo_root)
    seen = {}

    def adapter_fn(invocation: AgentInvocation) -> AgentResult:
        seen["invocation"] = invocation
        return AgentResult(status=AgentStatus.COMPLETED, output={}, termination_reason="success")

    _run(conn, worktree, repo_root, adapter_fn, skill_refs=[SkillRef(ref="demo-skill@1.0.0")])

    objective = seen["invocation"].objective
    assert "[skill/instruction, untrusted]\nDo the demo thing." in objective
    assert "[user/input, untrusted]\nthe real task" in objective
    assert "Do the demo thing." in objective
    assert objective.endswith("[user/input, untrusted]\nthe real task")
    assert not (worktree / ".claude" / "skills").exists()
    assert not (worktree / ".agents" / "skills").exists()
    assert seen["invocation"].skills == ("demo-skill@1.0.0",)

    event = conn.execute("SELECT payload_json FROM events WHERE new_status = 'skills_resolved'").fetchone()
    assert event is not None
    assert '"shared": false' in event["payload_json"]


def test_instructions_fold_in_even_with_no_skills(repo_and_worktree, conn):
    repo_root, worktree = repo_and_worktree
    seen = {}

    def adapter_fn(invocation: AgentInvocation) -> AgentResult:
        seen["invocation"] = invocation
        return AgentResult(status=AgentStatus.COMPLETED, output={}, termination_reason="success")

    _run(conn, worktree, repo_root, adapter_fn, instructions="You are a careful builder.")

    objective = seen["invocation"].objective
    assert objective == (
        "[application/instruction]\nYou are a careful builder.\n\n[user/input, untrusted]\nthe real task"
    )


def test_shared_tier_materializes_claude_and_agents_skills_directories(repo_and_worktree, conn):
    repo_root, worktree = repo_and_worktree
    _write_demo_skill(repo_root)
    seen = {}

    def adapter_fn(invocation: AgentInvocation) -> AgentResult:
        seen["invocation"] = invocation
        return AgentResult(status=AgentStatus.COMPLETED, output={}, termination_reason="success")

    _run(conn, worktree, repo_root, adapter_fn, skill_refs=[SkillRef(ref="demo-skill@1.0.0", share=True)])

    claude_copy = worktree / ".claude" / "skills" / "demo-skill" / "SKILL.md"
    agents_copy = worktree / ".agents" / "skills" / "demo-skill" / "SKILL.md"
    assert claude_copy.is_file()
    assert agents_copy.is_file()
    assert "Do the demo thing." in seen["invocation"].objective


def test_codex_shared_tier_mirrors_scratch_home_to_the_worktree_copy(repo_and_worktree, conn):
    repo_root, worktree = repo_and_worktree
    _write_demo_skill(repo_root)
    seen = {}

    def adapter_fn(invocation: AgentInvocation) -> AgentResult:
        seen["invocation"] = invocation
        return AgentResult(status=AgentStatus.COMPLETED, output={}, termination_reason="success")

    _run(
        conn,
        worktree,
        repo_root,
        adapter_fn,
        actor="codex",
        skill_refs=[SkillRef(ref="demo-skill@1.0.0", share=True)],
    )

    home_dir = repo_root / "cache" / "sandbox" / "run-1" / "codex_home" / "codex"
    link_path = home_dir / "skills" / "demo-skill"
    assert link_path.is_dir()
    assert (link_path / "SKILL.md").read_text() == (
        worktree / ".claude" / "skills" / "demo-skill" / "SKILL.md"
    ).read_text()

    overlay = seen["invocation"].constraints["skill_env_overlay"]
    assert overlay["CODEX_HOME"] == str(home_dir)


def test_quarantined_skill_ref_is_refused_before_either_tier_applies(repo_and_worktree, conn):
    repo_root, worktree = repo_and_worktree
    skill_dir = repo_root / "data" / "registry" / "skills" / "demo-skill" / "1.0.0"
    skill_dir.mkdir(parents=True)
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text("---\nname: demo-skill\ndescription: x\n---\n\nDo the demo thing.\n")
    conn.execute(
        "INSERT INTO registry_index (kind, name, version, digest, source, path, trust_status, indexed_at) "
        "VALUES ('skills', 'demo-skill', '1.0.0', 'x', 'data', ?, 'quarantined', '2026-01-01T00:00:00Z')",
        (str(skill_md.relative_to(repo_root)),),
    )
    conn.commit()
    seen = {}

    def adapter_fn(invocation: AgentInvocation) -> AgentResult:
        seen["invocation"] = invocation
        return AgentResult(status=AgentStatus.COMPLETED, output={}, termination_reason="success")

    _run(conn, worktree, repo_root, adapter_fn, skill_refs=[SkillRef(ref="demo-skill@1.0.0", share=True)])

    assert "Do the demo thing." not in seen["invocation"].objective
    assert not (worktree / ".claude" / "skills").exists()
    assert conn.execute("SELECT 1 FROM events WHERE new_status = 'skills_resolved'").fetchone() is None


def test_no_skill_refs_still_labels_user_objective(repo_and_worktree, conn):
    repo_root, worktree = repo_and_worktree
    seen = {}

    def adapter_fn(invocation: AgentInvocation) -> AgentResult:
        seen["invocation"] = invocation
        return AgentResult(status=AgentStatus.COMPLETED, output={}, termination_reason="success")

    invocation = AgentInvocation(objective="the real task", inputs={}, workspace_root=worktree)
    run_agent_step(
        conn,
        step_id="step-1",
        run_id="run-1",
        worktree_path=worktree,
        invocation=invocation,
        adapter_fn=adapter_fn,
        commit_message="agent: no skills",
        actor="claude-code",
        repo_root=repo_root,
    )

    assert seen["invocation"] is not invocation
    assert seen["invocation"].objective == "[user/input, untrusted]\nthe real task"


def test_persona_ref_folds_compiled_persona_into_objective(repo_and_worktree, conn):
    repo_root, worktree = repo_and_worktree
    persona_dir = repo_root / "config" / "app_registry" / "personas" / "narrator"
    persona_dir.mkdir(parents=True)
    (persona_dir / "1.0.0.yaml").write_text(
        "name: narrator\n"
        "version: 1.0.0\n"
        "display_name: Narrator\n"
        "description: x\n"
        "locale: en\n"
        "system: Persona system text.\n"
        "style:\n"
        "  max_words_default: 120\n"
        "  structure: Answer first.\n"
        "  do: [State facts.]\n"
        "  avoid: [Guessing.]\n"
        "traits: {warmth: medium, assertiveness: medium, detail: medium, humor: none}\n"
        "examples:\n"
        "  - {user: 'Did it pass?', assistant: Yes.}\n"
        "generation: {temperature: 0.6, max_tokens: 180}\n"
    )
    seen = {}

    def adapter_fn(invocation: AgentInvocation) -> AgentResult:
        seen["invocation"] = invocation
        return AgentResult(status=AgentStatus.COMPLETED, output={}, termination_reason="success")

    _run(conn, worktree, repo_root, adapter_fn, persona_ref="narrator@1.0.0")

    objective = seen["invocation"].objective
    assert "[persona/style]\nPersona system text." in objective
    assert "Persona constraints do not override capability, routing, memory, or safety policy." in objective
    assert objective.endswith("[user/input, untrusted]\nthe real task")
