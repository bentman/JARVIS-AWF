"""Phase 0 bootstrap: populate .env, create cache/sandbox/, create data/awf_db/awf.db.

Exit condition (Section 6, Phase 0): a fresh checkout plus one setup command
produces a valid empty data/awf_db/awf.db and a populated .env.
"""

import base64
import os
import sys
from pathlib import Path

from awf.db.bootstrap import init_db

PLACEHOLDER = "<your-secret-key-here>"


def _generate_secret_key() -> str:
    return base64.urlsafe_b64encode(os.urandom(32)).decode("ascii")


def bootstrap_repo(repo_root: Path) -> None:
    env_path = repo_root / ".env"
    example_path = repo_root / ".env.example"

    if not env_path.exists():
        if not example_path.exists():
            raise FileNotFoundError(f"missing template: {example_path}")
        content = example_path.read_text()
        content = content.replace(PLACEHOLDER, _generate_secret_key())
        env_path.write_text(content)

    (repo_root / "cache" / "sandbox").mkdir(parents=True, exist_ok=True)
    (repo_root / "cache" / "temp").mkdir(parents=True, exist_ok=True)

    init_db(repo_root / "data" / "awf_db" / "awf.db")


def _repo_root() -> Path:
    # backend/src/awf/setup.py -> awf -> src -> backend -> <repo root>
    return Path(__file__).resolve().parents[3]


def main() -> int:
    repo_root = _repo_root()
    bootstrap_repo(repo_root)
    print(f"AWF bootstrap complete: {repo_root / 'data' / 'awf_db' / 'awf.db'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
