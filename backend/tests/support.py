import subprocess
from pathlib import Path

import yaml

from awf.db.bootstrap import init_db
from awf.db.connection import get_connection
from awf.engine.run import create_run, create_step
from awf.registry.kinds import KINDS


def make_awf_repo(tmp_path: Path):
    repo_root = tmp_path / "repo"
    (repo_root / "data" / "awf_db").mkdir(parents=True)
    (repo_root / "data" / "registry").mkdir(parents=True)
    (repo_root / "config" / "app_registry").mkdir(parents=True)
    for kind in KINDS:
        (repo_root / "data" / "registry" / kind.key).mkdir(parents=True, exist_ok=True)
    db_path = repo_root / "data" / "awf_db" / "awf.db"
    init_db(db_path)
    return repo_root, get_connection(db_path)


def make_db(tmp_path: Path):
    db_path = tmp_path / "awf.db"
    init_db(db_path)
    return get_connection(db_path)


def seed_run_step(conn, *, run_id: str = "run-1", step_id: str = "s1", node_id: str = "n1") -> None:
    create_run(conn, run_id=run_id, workflow_ref="demo@1.0.0")
    create_step(conn, step_id=step_id, run_id=run_id, node_id=node_id)


def seed_approval(
    conn,
    *,
    approval_id: str = "ap-1",
    run_id: str = "run-1",
    step_id: str = "s1",
    status: str = "pending",
    risk_class: str | None = None,
) -> None:
    conn.execute(
        "INSERT INTO approvals "
        "(approval_id, run_id, step_id, action_digest, status, requested_at, risk_class) "
        "VALUES (?, ?, ?, 'sha256:deadbeef', ?, '2026-01-01T00:00:00Z', ?)",
        (approval_id, run_id, step_id, status, risk_class),
    )
    conn.commit()


def run_git(args: list[str], cwd: Path):
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    return result


def make_git_awf_repo(tmp_path: Path):
    repo_root, conn = make_awf_repo(tmp_path)
    run_git(["init", "-q"], cwd=repo_root)
    run_git(["config", "user.email", "t@e.com"], cwd=repo_root)
    run_git(["config", "user.name", "T"], cwd=repo_root)
    (repo_root / "README.md").write_text("x\n")
    run_git(["add", "-A"], cwd=repo_root)
    run_git(["commit", "-q", "-m", "init"], cwd=repo_root)
    return repo_root, conn


def publish_workflow(repo_root: Path, raw: dict) -> None:
    target = (
        repo_root
        / "config"
        / "app_registry"
        / "workflows"
        / raw["metadata"]["name"]
        / f"{raw['metadata']['version']}.yaml"
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(yaml.safe_dump(raw))


def single_gate_workflow(name: str, version: str = "1.0.0", digest: str = "sha256:demo") -> dict:
    return {
        "apiVersion": "awf/v1",
        "kind": "Workflow",
        "metadata": {"name": name, "version": version, "digest": digest},
        "spec": {
            "inputSchema": {},
            "outputSchema": {},
            "budgets": {},
            "nodes": [{"id": "check", "type": "gate", "checkCommand": "true", "next": None}],
            "outputs": {},
        },
    }


def publish_trivial_gate_workflow(repo_root: Path, *, name: str, version: str = "1.0.0") -> None:
    publish_workflow(repo_root, single_gate_workflow(name, version))
