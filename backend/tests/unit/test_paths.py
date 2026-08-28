from awf.paths import (
    config_registry_dir,
    data_registry_dir,
    db_path,
    env_path,
    models_dir,
    sandbox_dir,
    scratch_dir,
)


def test_db_path(tmp_path):
    assert db_path(tmp_path) == tmp_path / "data" / "awf_db" / "awf.db"


def test_models_dir(tmp_path):
    assert models_dir(tmp_path, "stt") == tmp_path / "models" / "stt"


def test_env_path(tmp_path):
    assert env_path(tmp_path) == tmp_path / ".env"


def test_config_registry_dir(tmp_path):
    assert config_registry_dir(tmp_path) == tmp_path / "config" / "app_registry"


def test_data_registry_dir(tmp_path):
    assert data_registry_dir(tmp_path) == tmp_path / "data" / "registry"


def test_sandbox_dir(tmp_path):
    assert sandbox_dir(tmp_path) == tmp_path / "cache" / "sandbox"


def test_scratch_dir(tmp_path):
    assert scratch_dir(tmp_path, "run-123") == tmp_path / "cache" / "sandbox" / "run-123"
