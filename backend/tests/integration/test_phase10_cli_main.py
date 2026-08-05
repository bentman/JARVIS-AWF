import json

from awf.cli import main as cli_main
from awf.db.bootstrap import init_db
from awf.engine.run import create_run


def make_repo(tmp_path):
    repo_root = tmp_path / "repo"
    (repo_root / "data" / "awf_db").mkdir(parents=True)
    init_db(repo_root / "data" / "awf_db" / "awf.db")
    return repo_root


def test_status_command_prints_json(tmp_path, capsys):
    repo_root = make_repo(tmp_path)
    from awf.db.connection import get_connection

    conn = get_connection(repo_root / "data" / "awf_db" / "awf.db")
    create_run(conn, run_id="run-1", workflow_ref="demo@1.0.0")
    conn.close()

    exit_code = cli_main.run(["status", "run-1"], repo_root)

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


def test_run_command_success_exit_code(tmp_path, monkeypatch):
    repo_root = make_repo(tmp_path)
    monkeypatch.setattr(
        cli_main.ops, "op_run_start",
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

    exit_code = cli_main.run(
        ["run", "requires-objective@1.0.0", "--input", str(input_file)], repo_root
    )

    assert exit_code == 1
    assert "inputSchema" in capsys.readouterr().err


def test_approve_command_dispatches_to_core_ops(tmp_path, monkeypatch):
    repo_root = make_repo(tmp_path)
    captured = {}

    def fake_approve(conn, *, approval_id):
        captured["approval_id"] = approval_id
        return {"approval_id": approval_id, "status": "approved"}

    monkeypatch.setattr(cli_main.ops, "op_approval_approve", fake_approve)

    exit_code = cli_main.run(["approve", "ap-1"], repo_root)

    assert exit_code == 0
    assert captured["approval_id"] == "ap-1"


def test_reject_command_requires_reason(tmp_path):
    repo_root = make_repo(tmp_path)
    try:
        cli_main.run(["reject", "ap-1"], repo_root)
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

    exit_code = cli_main.run(["secret", "list"], repo_root)

    assert exit_code == 0
    assert captured["argv"] == ["list"]


def test_registry_validate_command(tmp_path, capsys, fixtures_dir):
    repo_root = make_repo(tmp_path)
    fixture = fixtures_dir / "test_phase1" / "test_phase1_read_file_r0.yaml"

    exit_code = cli_main.run(["registry", "validate", str(fixture)], repo_root)

    assert exit_code == 0
    out = json.loads(capsys.readouterr().out)
    assert out["kind"] == "CapabilityRecord"
