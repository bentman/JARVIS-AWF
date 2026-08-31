import argparse
import json

import pytest

from awf.cli import main as cli_main
from awf.db.bootstrap import init_db
from awf.engine.run import create_run


def make_repo(tmp_path):
    repo_root = tmp_path / "repo"
    (repo_root / "data" / "awf_db").mkdir(parents=True)
    init_db(repo_root / "data" / "awf_db" / "awf.db")
    return repo_root


def test_status_command_prints_operator_summary(tmp_path, capsys):
    repo_root = make_repo(tmp_path)
    from awf.db.connection import get_connection

    conn = get_connection(repo_root / "data" / "awf_db" / "awf.db")
    create_run(conn, run_id="run-1", workflow_ref="demo@1.0.0")
    conn.close()

    exit_code = cli_main.run(["status", "run-1"], repo_root)

    assert exit_code == 0
    assert "Run: run-1" in capsys.readouterr().out


def test_status_command_json_flag_preserves_machine_output(tmp_path, capsys):
    repo_root = make_repo(tmp_path)
    from awf.db.connection import get_connection

    conn = get_connection(repo_root / "data" / "awf_db" / "awf.db")
    create_run(conn, run_id="run-1", workflow_ref="demo@1.0.0")
    conn.close()

    exit_code = cli_main.run(["status", "run-1", "--json"], repo_root)

    assert exit_code == 0
    out = json.loads(capsys.readouterr().out)
    assert out["run_id"] == "run-1"


def test_run_command_calls_op_run_start_and_reports_failure_exit_code(tmp_path, capsys, monkeypatch):
    repo_root = make_repo(tmp_path)
    captured = {}

    def fake_op_run_start(repo_root, conn, *, workflow_ref, input_data):
        captured["workflow_ref"] = workflow_ref
        captured["input_data"] = input_data
        return {"run_id": "run-1", "status": "FAILED", "repairs_used": 3}

    monkeypatch.setattr(cli_main.ops, "op_run_start", fake_op_run_start)

    input_file = tmp_path / "input.json"
    input_file.write_text(json.dumps({"objective": "demo"}))

    exit_code = cli_main.run(["run", "demo@1.0.0", "--input", str(input_file)], repo_root)

    assert exit_code == 1
    assert captured["workflow_ref"] == "demo@1.0.0"
    assert captured["input_data"] == {"objective": "demo"}


def test_run_command_accepts_objective_shorthand(tmp_path, monkeypatch):
    repo_root = make_repo(tmp_path)
    captured = {}

    def fake_op_run_start(repo_root, conn, *, workflow_ref, input_data):
        captured["workflow_ref"] = workflow_ref
        captured["input_data"] = input_data
        return {"run_id": "run-1", "status": "SUCCEEDED"}

    monkeypatch.setattr(cli_main.ops, "op_run_start", fake_op_run_start)

    exit_code = cli_main.run(["run", "assistant-default@1.0.0", "--objective", "check the system"], repo_root)

    assert exit_code == 0
    assert captured["workflow_ref"] == "assistant-default@1.0.0"
    assert captured["input_data"] == {"objective": "check the system"}


def test_run_command_prints_operator_outcome(tmp_path, capsys, monkeypatch):
    repo_root = make_repo(tmp_path)
    monkeypatch.setattr(
        cli_main.ops,
        "op_run_start",
        lambda repo_root, conn, *, workflow_ref, input_data: {
            "run_id": "run-1",
            "status": "SUCCEEDED",
            "outcome": {
                "run_id": "run-1",
                "workflow_ref": workflow_ref,
                "status": "SUCCEEDED",
                "response_text": "Useful result.",
                "evidence": [],
                "failures": [],
                "pending_approvals": [],
                "next_action": "No operator action required.",
            },
        },
    )

    exit_code = cli_main.run(["run", "demo@1.0.0"], repo_root)

    assert exit_code == 0
    assert "Result: Useful result." in capsys.readouterr().out


def test_run_command_success_exit_code(tmp_path, monkeypatch):
    repo_root = make_repo(tmp_path)
    monkeypatch.setattr(
        cli_main.ops,
        "op_run_start",
        lambda repo_root, conn, *, workflow_ref, input_data: {"run_id": "run-1", "status": "SUCCEEDED"},
    )

    exit_code = cli_main.run(["run", "demo@1.0.0"], repo_root)

    assert exit_code == 0


def test_run_command_reports_a_coreoperror_cleanly_not_a_traceback(tmp_path, capsys):
    # A CoreOpError (e.g. input that violates a workflow's inputSchema, or
    # any other op_run_start-raised error) must produce a clean CLI error
    # and a non-zero exit code, not an uncaught traceback - the JSON-RPC
    # surface already has this safety net; the CLI does not.
    repo_root = make_repo(tmp_path)
    workflow_dir = repo_root / "config" / "app_registry" / "workflows" / "requires-objective"
    workflow_dir.mkdir(parents=True)
    (workflow_dir / "1.0.0.yaml").write_text(
        "apiVersion: awf/v1\nkind: Workflow\n"
        "metadata: {name: requires-objective, version: 1.0.0, digest: 'sha256:demo'}\n"
        "spec:\n"
        "  inputSchema: {type: object, required: [objective]}\n"
        "  outputSchema: {}\n  budgets: {}\n"
        "  nodes: [{id: check, type: gate, checkCommand: 'true', next: null}]\n"
        "  outputs: {}\n"
    )
    input_file = tmp_path / "input.json"
    input_file.write_text(json.dumps({}))

    exit_code = cli_main.run(["run", "requires-objective@1.0.0", "--input", str(input_file)], repo_root)

    assert exit_code == 1
    assert "inputSchema" in capsys.readouterr().err


def test_approve_command_dispatches_to_ops(tmp_path, monkeypatch):
    repo_root = make_repo(tmp_path)
    captured = {}

    def fake_approve(conn, *, approval_id):
        captured["approval_id"] = approval_id
        return {"approval_id": approval_id, "status": "approved"}

    monkeypatch.setattr(cli_main.ops, "op_approval_approve", fake_approve)
    monkeypatch.setattr(
        cli_main.ops,
        "op_approval_detail",
        lambda conn, *, approval_id: {"approval": {"approval_id": approval_id}, "preview": None},
    )

    exit_code = cli_main.run(["review", "approve", "ap-1"], repo_root)

    assert exit_code == 0
    assert captured["approval_id"] == "ap-1"


def test_reject_command_requires_reason(tmp_path):
    repo_root = make_repo(tmp_path)
    try:
        cli_main.run(["review", "reject", "ap-1"], repo_root)
        raised = False
    except SystemExit:
        raised = True
    assert raised


def test_secret_subcommand_delegates_to_secrets_cli(tmp_path, monkeypatch):
    repo_root = make_repo(tmp_path)
    captured = {}

    def fake_run(argv, repo_root_arg):
        captured["argv"] = argv
        return 0

    monkeypatch.setattr(cli_main.secrets_cli, "run", fake_run)

    exit_code = cli_main.run(["system", "secret", "list"], repo_root)

    assert exit_code == 0
    assert captured["argv"] == ["list"]


def test_registry_validate_command(tmp_path, capsys, fixtures_dir):
    repo_root = make_repo(tmp_path)
    fixture = fixtures_dir / "guard_registry" / "capabilities" / "read_file" / "1.0.0.yaml"

    exit_code = cli_main.run(["registry", "validate", str(fixture), "--kind", "capabilities"], repo_root)

    assert exit_code == 0
    out = json.loads(capsys.readouterr().out)
    assert out["kind"] == "CapabilityRecord"


def test_author_workflow_command_dispatches_to_ops(tmp_path, monkeypatch):
    repo_root = make_repo(tmp_path)
    captured = {}

    def fake_author(repo_root, conn, *, objective, name, version, profile_ref):
        captured.update({"objective": objective, "name": name, "version": version, "profile_ref": profile_ref})
        return {"proposal_id": "p1", "status": "draft"}

    monkeypatch.setattr(cli_main.ops, "op_workflow_author_draft", fake_author)

    exit_code = cli_main.run(
        ["review", "draft", "--objective", "make demo", "--name", "demo", "--version", "0.1.0"],
        repo_root,
    )

    assert exit_code == 0
    assert captured == {
        "objective": "make demo",
        "name": "demo",
        "version": "0.1.0",
        "profile_ref": "resident-mind@1.0.0",
    }


def test_proposal_publish_command_dispatches_to_ops(tmp_path, monkeypatch):
    repo_root = make_repo(tmp_path)
    captured = {}

    def fake_publish(repo_root, conn, *, proposal_id, digest):
        captured.update({"proposal_id": proposal_id, "digest": digest})
        return {"proposal": {"proposal_id": proposal_id, "status": "published"}}

    monkeypatch.setattr(cli_main.ops, "op_proposal_publish", fake_publish)

    exit_code = cli_main.run(["review", "publish", "p1", "--digest", "abc"], repo_root)

    assert exit_code == 0
    assert captured == {"proposal_id": "p1", "digest": "abc"}


def test_improvement_commands_dispatch_to_ops(tmp_path, monkeypatch):
    repo_root = make_repo(tmp_path)
    captured = {}

    monkeypatch.setattr(
        cli_main.ops,
        "op_improvement_list",
        lambda conn, *, status=None: [{"improvement_id": "imp-1", "status": status, "summary": "s"}],
    )
    exit_code = cli_main.run(["review", "list", "--status", "ready_for_review"], repo_root)
    assert exit_code == 0

    def fake_prepare(repo_root, conn, *, run_id, summary):
        captured["prepare"] = {"run_id": run_id, "summary": summary}
        return {"improvement_id": "imp-1"}

    monkeypatch.setattr(cli_main.ops, "op_improvement_prepare", fake_prepare)
    exit_code = cli_main.run(["review", "prepare", "run-1", "--summary", "focused"], repo_root)
    assert exit_code == 0
    assert captured["prepare"] == {"run_id": "run-1", "summary": "focused"}

    def fake_ready(repo_root, conn, *, improvement_id, verdict_artifact_id, validation_artifact_ids):
        captured["ready"] = {
            "improvement_id": improvement_id,
            "verdict_artifact_id": verdict_artifact_id,
            "validation_artifact_ids": validation_artifact_ids,
        }
        return {"status": "ready_for_review"}

    monkeypatch.setattr(cli_main.ops, "op_improvement_mark_ready", fake_ready)
    exit_code = cli_main.run(
        [
            "review",
            "mark-ready",
            "imp-1",
            "--verdict-artifact-id",
            "verdict-1",
            "--validation-artifact-id",
            "test-1",
        ],
        repo_root,
    )
    assert exit_code == 0
    assert captured["ready"] == {
        "improvement_id": "imp-1",
        "verdict_artifact_id": "verdict-1",
        "validation_artifact_ids": ["test-1"],
    }

    monkeypatch.setattr(
        cli_main.ops,
        "op_improvement_request_merge",
        lambda repo_root, conn, *, improvement_id: captured.setdefault("request", improvement_id) or {},
    )
    exit_code = cli_main.run(["review", "request-merge", "imp-1"], repo_root)
    assert exit_code == 0
    assert captured["request"] == "imp-1"

    def fake_merge(repo_root, conn, *, improvement_id, approval_id):
        captured["merge"] = {"improvement_id": improvement_id, "approval_id": approval_id}
        return {"status": "merged"}

    monkeypatch.setattr(cli_main.ops, "op_improvement_merge", fake_merge)
    exit_code = cli_main.run(["review", "merge", "imp-1", "ap-1"], repo_root)
    assert exit_code == 0
    assert captured["merge"] == {"improvement_id": "imp-1", "approval_id": "ap-1"}


def test_registry_reindex_command_dispatches_to_ops(tmp_path, capsys, monkeypatch):
    repo_root = make_repo(tmp_path)
    monkeypatch.setattr(
        cli_main.ops, "op_registry_reindex", lambda repo_root, conn: {"capabilities": {"config": 1, "data": 0}}
    )

    exit_code = cli_main.run(["registry", "reindex"], repo_root)

    assert exit_code == 0
    out = json.loads(capsys.readouterr().out)
    assert out["capabilities"] == {"config": 1, "data": 0}


def test_doctor_command_dispatches_to_ops(tmp_path, capsys, monkeypatch):
    repo_root = make_repo(tmp_path)
    monkeypatch.setattr(
        cli_main.ops,
        "op_system_doctor",
        lambda repo_root: {
            "status": "warn",
            "checks": [{"name": "frontend", "status": "warn", "summary": "npm missing"}],
            "first_run_command": 'awf run assistant-default@1.0.0 --objective "check the system"',
        },
    )

    exit_code = cli_main.run(["doctor"], repo_root)

    assert exit_code == 0
    assert "AWF doctor: warn" in capsys.readouterr().out


def test_readiness_command_json_flag(tmp_path, capsys, monkeypatch):
    repo_root = make_repo(tmp_path)
    monkeypatch.setattr(
        cli_main.ops,
        "op_system_readiness",
        lambda repo_root: {"profile_id": "linux-x64-cpu", "tokens": [], "readiness": {}},
    )

    exit_code = cli_main.run(["system", "readiness", "--json"], repo_root)

    assert exit_code == 0
    out = json.loads(capsys.readouterr().out)
    assert out["profile_id"] == "linux-x64-cpu"


def test_registry_retire_command_dispatches_to_ops(tmp_path, capsys, monkeypatch):
    repo_root = make_repo(tmp_path)
    captured = {}

    def fake_retire(conn, *, kind, name, version):
        captured.update(kind=kind, name=name, version=version)
        return {"kind": kind, "name": name, "version": version, "trust_status": "blocked"}

    monkeypatch.setattr(cli_main.ops, "op_registry_retire", fake_retire)

    exit_code = cli_main.run(["registry", "retire", "capabilities", "demo", "1.0.0"], repo_root)

    assert exit_code == 0
    assert captured == {"kind": "capabilities", "name": "demo", "version": "1.0.0"}
    out = json.loads(capsys.readouterr().out)
    assert out["trust_status"] == "blocked"


def test_registry_trust_command_requires_status(tmp_path):
    repo_root = make_repo(tmp_path)
    try:
        cli_main.run(["registry", "trust", "capabilities", "demo", "1.0.0"], repo_root)
        raised = False
    except SystemExit:
        raised = True
    assert raised


def test_registry_trust_command_dispatches_to_ops(tmp_path, capsys, monkeypatch):
    repo_root = make_repo(tmp_path)
    captured = {}

    def fake_trust(conn, *, kind, name, version, status):
        captured.update(kind=kind, name=name, version=version, status=status)
        return {"kind": kind, "name": name, "version": version, "trust_status": status}

    monkeypatch.setattr(cli_main.ops, "op_registry_trust", fake_trust)

    exit_code = cli_main.run(["registry", "trust", "capabilities", "demo", "1.0.0", "--status", "trusted"], repo_root)

    assert exit_code == 0
    assert captured == {"kind": "capabilities", "name": "demo", "version": "1.0.0", "status": "trusted"}
    out = json.loads(capsys.readouterr().out)
    assert out["trust_status"] == "trusted"


def test_memory_search_command_dispatches_to_ops(tmp_path, monkeypatch):
    repo_root = make_repo(tmp_path)
    captured = {}

    def fake_search(repo_root, conn, *, query, profile_ref):
        captured.update(query=query, profile_ref=profile_ref)
        return {"semantic": [], "episodic": []}

    monkeypatch.setattr(cli_main.ops, "op_memory_search", fake_search)

    exit_code = cli_main.run(["memory", "search", "targeted", "--profile", "default@1.0.0"], repo_root)

    assert exit_code == 0
    assert captured == {"query": "targeted", "profile_ref": "default@1.0.0"}


def test_session_start_command_dispatches_to_ops(tmp_path, monkeypatch):
    repo_root = make_repo(tmp_path)
    captured = {}

    def fake_start(conn, *, title, expires_at):
        captured.update(title=title, expires_at=expires_at)
        return {"session_id": "s1"}

    monkeypatch.setattr(cli_main.ops, "op_session_start", fake_start)

    exit_code = cli_main.run(["memory", "session-start", "--title", "demo"], repo_root)

    assert exit_code == 0
    assert captured == {"title": "demo", "expires_at": None}


def test_every_command_can_render_its_help(tmp_path):
    # `awf run --help` crashed with "empty group" because each argument in a
    # mutually exclusive group created a fresh group, leaving an empty one
    # behind for argparse to format. Walk every parser so the whole class of
    # help-rendering failures is covered, not just the one command that hit it.
    def walk(parser, path):
        parser.format_help()
        for action in parser._actions:
            if isinstance(action, argparse._SubParsersAction):
                for name, subparser in action.choices.items():
                    walk(subparser, (*path, name))

    walk(cli_main.build_parser(), ())


def test_every_command_has_help_text():
    # An operator reading `awf --help` sees only what CLI_HELP provides.
    missing = [" ".join(spec["path"]) for spec in cli_main.CLI_COMMAND_SPECS if not cli_main.CLI_HELP.get(spec["path"])]
    assert missing == []


def test_run_command_names_available_workflows_when_the_ref_is_unknown(tmp_path, capsys):
    repo_root = make_repo(tmp_path)
    workflow_dir = repo_root / "config" / "app_registry" / "workflows" / "demo"
    workflow_dir.mkdir(parents=True)
    (workflow_dir / "1.0.0.yaml").write_text(
        "apiVersion: awf/v1\nkind: Workflow\n"
        "metadata: {name: demo, version: 1.0.0, digest: 'sha256:demo'}\n"
        "spec:\n  inputSchema: {}\n  outputSchema: {}\n  budgets: {}\n"
        "  nodes: [{id: check, type: gate, checkCommand: 'true', next: null}]\n"
        "  outputs: {}\n"
    )

    exit_code = cli_main.run(["run", "nope@1.0.0"], repo_root)

    err = capsys.readouterr().err
    assert exit_code == 1
    assert "unknown workflow 'nope@1.0.0'" in err
    assert "demo@1.0.0" in err


def test_spec_16_1_commands_moved_to_their_consolidated_paths():
    # ADR-0029 replaces Section 16.1's spellings rather than aliasing them.
    # Phase 10 acceptance now runs the right-hand column.
    parser = cli_main.build_parser()
    moved = {
        ("approvals",): ["review", "list"],
        ("approve",): ["review", "approve", "ap-1"],
        ("reject",): ["review", "reject", "ap-1", "--reason", "no"],
        ("artifacts",): ["status", "run-1", "--artifacts"],
        ("resume",): ["system", "resume"],
        ("secret",): ["system", "secret", "list"],
        ("serve",): ["system", "serve", "--stdio"],
    }
    for retired, replacement in moved.items():
        with pytest.raises(SystemExit):
            parser.parse_args(list(retired))
        parsed = parser.parse_args(replacement)
        assert getattr(parsed, "func", None) is not None or getattr(parsed, "is_secret", False), replacement

    # The commands ADR-0029 keeps unchanged still resolve to a handler.
    for argv in (
        ["run", "demo@1.0.0"],
        ["status", "run-1"],
        ["status"],
        ["doctor"],
        ["registry", "validate", "def.yaml"],
        ["registry", "publish", "def.yaml", "--kind", "workflows"],
    ):
        assert parser.parse_args(argv).func is not None, argv


def test_review_resolves_an_id_to_whichever_kind_owns_it(tmp_path, monkeypatch, capsys):
    repo_root = make_repo(tmp_path)

    def only_improvement(conn, *, improvement_id):
        if improvement_id != "imp-1":
            raise cli_main.CoreOpError(f"no such improvement: {improvement_id}")
        return {"improvement_id": "imp-1", "status": "draft", "summary": "s"}

    monkeypatch.setattr(cli_main.ops, "op_improvement_get", only_improvement)
    monkeypatch.setattr(
        cli_main.ops,
        "op_improvement_reject",
        lambda repo_root, conn, *, improvement_id, reason: {"improvement_id": improvement_id, "reason": reason},
    )

    assert cli_main.run(["review", "show", "imp-1"], repo_root) == 0
    assert cli_main.run(["review", "reject", "imp-1", "--reason", "not now"], repo_root) == 0
    assert '"reason": "not now"' in capsys.readouterr().out

    # An id that names nothing points the operator at the queue.
    assert cli_main.run(["review", "show", "nope"], repo_root) == 1
    assert "no approval, change, or draft with id 'nope'" in capsys.readouterr().err
