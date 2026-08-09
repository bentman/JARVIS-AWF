import pytest

from awf.db.bootstrap import init_db
from awf.db.connection import get_connection
from awf.registry.index import compute_digest, index_row, latest_version, reindex, set_trust_status
from awf.registry.kinds import CAPABILITIES
from awf.registry.resolve import RegistryBlockedError, RegistryIntegrityError, RegistryObjectNotFoundError, resolve_registry_object


def make_repo(tmp_path):
    repo_root = tmp_path / "repo"
    (repo_root / "data" / "awf_db").mkdir(parents=True)
    (repo_root / "data" / "registry").mkdir(parents=True)
    (repo_root / "config" / "app_registry").mkdir(parents=True)
    db_path = repo_root / "data" / "awf_db" / "awf.db"
    init_db(db_path)
    conn = get_connection(db_path)
    return repo_root, conn


def _write_capability(root, name, version, text="identity: {}\n"):
    target = root / "capabilities" / name / f"{version}.yaml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text)
    return target


def test_reindex_covers_both_roots_and_all_kinds(tmp_path):
    repo_root, conn = make_repo(tmp_path)
    _write_capability(repo_root / "data" / "registry", "demo", "1.0.0")
    _write_capability(repo_root / "config" / "app_registry", "other", "1.0.0")

    counts = reindex(repo_root, conn)

    assert counts["capabilities"] == {"config": 1, "data": 1}
    assert set(counts.keys()) == {
        "workflows", "agents", "capabilities", "mcp", "skills", "voice-profiles", "model-profiles", "personas",
    }
    assert index_row(conn, "capabilities", "demo", "1.0.0") is not None
    assert index_row(conn, "capabilities", "other", "1.0.0") is not None


def test_reindex_preserves_an_existing_non_default_trust_status(tmp_path):
    repo_root, conn = make_repo(tmp_path)
    _write_capability(repo_root / "data" / "registry", "demo", "1.0.0")
    reindex(repo_root, conn)
    set_trust_status(conn, "capabilities", "demo", "1.0.0", "blocked")

    reindex(repo_root, conn)

    row = index_row(conn, "capabilities", "demo", "1.0.0")
    assert row["trust_status"] == "blocked"


def test_resolution_fails_with_integrity_error_after_the_file_is_mutated(tmp_path):
    repo_root, conn = make_repo(tmp_path)
    path = _write_capability(repo_root / "data" / "registry", "demo", "1.0.0")
    reindex(repo_root, conn)

    path.write_text("identity: {mutated: true}\n")

    with pytest.raises(RegistryIntegrityError):
        resolve_registry_object(repo_root, "capabilities", "demo", "1.0.0", conn=conn)


def test_resolution_succeeds_after_reindex_accepts_the_new_content(tmp_path):
    repo_root, conn = make_repo(tmp_path)
    path = _write_capability(repo_root / "data" / "registry", "demo", "1.0.0")
    reindex(repo_root, conn)
    path.write_text("identity: {mutated: true}\n")
    reindex(repo_root, conn)

    resolved_path, source = resolve_registry_object(repo_root, "capabilities", "demo", "1.0.0", conn=conn)
    assert resolved_path == path
    assert source == "data"


def test_blocked_object_fails_resolution(tmp_path):
    repo_root, conn = make_repo(tmp_path)
    _write_capability(repo_root / "data" / "registry", "demo", "1.0.0")
    reindex(repo_root, conn)
    set_trust_status(conn, "capabilities", "demo", "1.0.0", "blocked")

    with pytest.raises(RegistryBlockedError):
        resolve_registry_object(repo_root, "capabilities", "demo", "1.0.0", conn=conn)


def test_marking_trusted_restores_resolution(tmp_path):
    repo_root, conn = make_repo(tmp_path)
    _write_capability(repo_root / "data" / "registry", "demo", "1.0.0")
    reindex(repo_root, conn)
    set_trust_status(conn, "capabilities", "demo", "1.0.0", "blocked")
    set_trust_status(conn, "capabilities", "demo", "1.0.0", "local")

    path, source = resolve_registry_object(repo_root, "capabilities", "demo", "1.0.0", conn=conn)
    assert source == "data"


def test_gitkeep_only_data_directory_falls_through_to_config(tmp_path):
    repo_root, conn = make_repo(tmp_path)
    (repo_root / "data" / "registry" / "capabilities" / "demo").mkdir(parents=True)
    (repo_root / "data" / "registry" / "capabilities" / "demo" / ".gitkeep").touch()
    config_path = _write_capability(repo_root / "config" / "app_registry", "demo", "1.0.0")

    path, source = resolve_registry_object(repo_root, "capabilities", "demo", "1.0.0")

    assert path == config_path
    assert source == "config"


def test_set_trust_status_returns_none_for_an_unindexed_object(tmp_path):
    _repo_root, conn = make_repo(tmp_path)
    assert set_trust_status(conn, "capabilities", "missing", "1.0.0", "blocked") is None


def test_latest_version_orders_dotted_integer_versions(tmp_path):
    repo_root, _conn = make_repo(tmp_path)
    for version in ("1.0.0", "1.2.0", "1.10.0", "2.0.0"):
        _write_capability(repo_root / "data" / "registry", "demo", version)

    assert latest_version(repo_root, "capabilities", "demo") == "2.0.0"


def test_latest_version_tolerates_a_non_numeric_version(tmp_path):
    repo_root, _conn = make_repo(tmp_path)
    _write_capability(repo_root / "data" / "registry", "demo", "1.0.0")
    _write_capability(repo_root / "data" / "registry", "demo", "not-a-version")

    assert latest_version(repo_root, "capabilities", "demo") == "1.0.0"


def test_latest_version_raises_when_the_name_is_absent(tmp_path):
    repo_root, _conn = make_repo(tmp_path)
    with pytest.raises(RegistryObjectNotFoundError):
        latest_version(repo_root, "capabilities", "missing")


def test_compute_digest_matches_sha256_of_file_bytes(tmp_path):
    path = tmp_path / "obj.yaml"
    path.write_text("identity: {}\n")
    import hashlib

    assert compute_digest(path, CAPABILITIES) == hashlib.sha256(path.read_bytes()).hexdigest()
