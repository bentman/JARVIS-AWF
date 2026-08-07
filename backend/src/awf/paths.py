"""Single source of truth for the repository root and paths derived from it
(ADR-0008). Every module under `backend/src/awf/` that needs the repository
root or the database path imports from here rather than deriving its own via
`Path(__file__).resolve().parents[N]` - this is the only one that does.

`scripts/validate_backend.py` and `backend/tests/conftest.py` keep deriving
their own: both must work before the package is importable.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

CONFIG_REGISTRY_RELATIVE = "config/app_registry"
DATA_REGISTRY_RELATIVE = "data/registry"


def db_path(repo_root: Path) -> Path:
    return repo_root / "data" / "awf_db" / "awf.db"


def models_dir(repo_root: Path, function: str) -> Path:
    return repo_root / "models" / function


def env_path(repo_root: Path) -> Path:
    return repo_root / ".env"


def config_registry_dir(repo_root: Path) -> Path:
    return repo_root / CONFIG_REGISTRY_RELATIVE


def data_registry_dir(repo_root: Path) -> Path:
    return repo_root / DATA_REGISTRY_RELATIVE


def artifacts_dir(repo_root: Path) -> Path:
    return repo_root / "data" / "artifacts"


def config_voice_dir(repo_root: Path) -> Path:
    return repo_root / "config" / "voice"


def sandbox_dir(repo_root: Path) -> Path:
    return repo_root / "cache" / "sandbox"


def scratch_dir(repo_root: Path, run_id: str) -> Path:
    return sandbox_dir(repo_root) / run_id
