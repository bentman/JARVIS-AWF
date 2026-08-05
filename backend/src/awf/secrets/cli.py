"""`awf secret set|list|rotate-key` (Section 16.1).

A standalone entrypoint for Phase 2. `run()` is what Phase 10 wires into the
unified `awf` command's subparser tree — the handler logic does not move.
"""

import argparse
import base64
import getpass
import os
import sys
from pathlib import Path

from awf.db.bootstrap import init_db
from awf.db.connection import get_connection
from awf.envfile import get_env_value, set_env_value
from awf.paths import REPO_ROOT, db_path
from awf.secrets.store import get_secret, list_secret_names, rotate_key, set_secret


def _load_key(repo_root: Path) -> bytes:
    return get_env_value(repo_root / ".env", "AWF_SECRET_KEY").encode("ascii")


def cmd_set(args: argparse.Namespace, repo_root: Path) -> int:
    plaintext = getpass.getpass(f"value for '{args.name}': ")
    conn = get_connection(db_path(repo_root))
    try:
        set_secret(conn, args.name, plaintext, _load_key(repo_root))
    finally:
        conn.close()
    return 0


def cmd_list(args: argparse.Namespace, repo_root: Path) -> int:
    conn = get_connection(db_path(repo_root))
    try:
        for name in list_secret_names(conn):
            print(name)
    finally:
        conn.close()
    return 0


def cmd_rotate_key(args: argparse.Namespace, repo_root: Path) -> int:
    new_key = base64.urlsafe_b64encode(os.urandom(32)).decode("ascii")
    conn = get_connection(db_path(repo_root))
    try:
        rotate_key(conn, _load_key(repo_root), new_key.encode("ascii"))
    finally:
        conn.close()
    set_env_value(repo_root / ".env", "AWF_SECRET_KEY", new_key)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="awf secret")
    sub = parser.add_subparsers(dest="command", required=True)

    set_parser = sub.add_parser("set")
    set_parser.add_argument("name")
    set_parser.set_defaults(func=cmd_set)

    list_parser = sub.add_parser("list")
    list_parser.set_defaults(func=cmd_list)

    rotate_parser = sub.add_parser("rotate-key")
    rotate_parser.set_defaults(func=cmd_rotate_key)

    return parser


def run(argv: list[str], repo_root: Path) -> int:
    args = build_parser().parse_args(argv)
    init_db(db_path(repo_root))
    return args.func(args, repo_root)


def main() -> int:
    return run(sys.argv[1:], REPO_ROOT)


if __name__ == "__main__":
    sys.exit(main())
