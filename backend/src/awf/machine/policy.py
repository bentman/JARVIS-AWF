"""Policy checks for ADR-0021 machine activities."""

import fnmatch
import ipaddress
import shlex
from pathlib import Path
from urllib.parse import urlparse

from awf.isolation.scratch import scratch_path


class MachinePolicyError(ValueError):
    pass


DENIED_RELATIVE_GLOBS = (".env", "data/awf_db/**", "data/registry/capabilities/**")


def constraint_family(constraints: dict, family: str) -> dict:
    value = constraints.get(family)
    if not isinstance(value, dict):
        raise MachinePolicyError(f"capability constraints must include {family!r}")
    return value


def _root_path(repo_root: Path, worktree: Path, run_id: str, root: str) -> Path:
    if root == "worktree":
        return worktree.resolve(strict=False)
    if root == "scratch":
        return scratch_path(repo_root, run_id).resolve(strict=False)
    if Path(root).is_absolute():
        return Path(root).resolve(strict=False)
    raise MachinePolicyError(f"unsupported root {root!r}")


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _matches_any(path: str, patterns: list[str] | tuple[str, ...]) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for pattern in patterns)


def resolve_allowed_path(
    *,
    repo_root: Path,
    worktree: Path,
    run_id: str,
    relative_or_absolute: str,
    constraints: dict,
    must_exist: bool = False,
) -> Path:
    roots = constraints.get("allowedRoots", ["worktree", "scratch"])
    root_paths = [_root_path(repo_root, worktree, run_id, root) for root in roots]
    raw = Path(relative_or_absolute)
    candidate = raw if raw.is_absolute() else worktree / raw
    candidate = candidate.resolve(strict=must_exist)
    if candidate.is_symlink() and not constraints.get("followSymlinks", False):
        raise MachinePolicyError(f"symlink traversal denied: {relative_or_absolute}")
    if not any(_is_relative_to(candidate, root) for root in root_paths):
        raise MachinePolicyError(f"path outside allowed roots: {relative_or_absolute}")

    try:
        display_path = str(candidate.relative_to(worktree.resolve(strict=False)))
    except ValueError:
        display_path = str(candidate)
    denied = list(DENIED_RELATIVE_GLOBS) + list(constraints.get("deniedGlobs", []))
    if _matches_any(display_path, denied):
        raise MachinePolicyError(f"path denied by policy: {display_path}")
    allowed = constraints.get("allowedGlobs")
    if allowed and not _matches_any(display_path, allowed):
        raise MachinePolicyError(f"path not allowed by glob policy: {display_path}")
    return candidate


def validate_command(*, argv: list[str], cwd: Path, worktree: Path, constraints: dict) -> None:
    if not argv:
        raise MachinePolicyError("command argv must not be empty")
    if any(token in item for item in argv for token in ("|", "&&", "||", ";", ">", "<")):
        raise MachinePolicyError("shell metacharacters require an explicit shell capability")
    executable = constraints.get("executable")
    if executable and argv[0] != executable:
        raise MachinePolicyError(f"executable {argv[0]!r} does not match policy {executable!r}")
    allowed_args = constraints.get("allowedArgs", [])
    if allowed_args:
        args = argv[1:]
        if not any(_argv_matches(args, pattern) for pattern in allowed_args):
            raise MachinePolicyError(f"argv not allowed by policy: {shlex.join(argv)}")
    cwd_root = constraints.get("cwdRoot", "worktree")
    if cwd_root == "worktree" and not _is_relative_to(cwd.resolve(strict=False), worktree.resolve(strict=False)):
        raise MachinePolicyError("command cwd outside worktree")
    if int(constraints.get("timeoutSeconds", 0)) < 1:
        raise MachinePolicyError("command timeoutSeconds must be positive")


def _argv_matches(args: list[str], pattern: list[str]) -> bool:
    if len(args) != len(pattern):
        return False
    return all(fnmatch.fnmatch(arg, pat) for arg, pat in zip(args, pattern, strict=True))


def validate_url(url: str, method: str, constraints: dict) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise MachinePolicyError(f"unsupported URL: {url}")
    allowed_methods = constraints.get("allowedMethods", ["GET", "HEAD"])
    if method.upper() not in allowed_methods:
        raise MachinePolicyError(f"method {method!r} is not allowed")
    allowed_hosts = constraints.get("allowedHosts", [])
    if not _host_allowed(parsed.hostname, allowed_hosts):
        raise MachinePolicyError(f"host {parsed.hostname!r} is not allowed")
    if not constraints.get("allowPrivateRanges", False):
        try:
            ip = ipaddress.ip_address(parsed.hostname)
        except ValueError:
            pass
        else:
            if ip.is_private or ip.is_loopback or ip.is_link_local:
                raise MachinePolicyError(f"private network host {parsed.hostname!r} is denied")
    if int(constraints.get("maxResponseBytes", 0)) < 1:
        raise MachinePolicyError("network maxResponseBytes must be positive")


def _host_allowed(host: str, allowed_hosts: list[str]) -> bool:
    for allowed in allowed_hosts:
        if allowed.startswith("*.") and host.endswith(allowed[1:]):
            return True
        if host == allowed:
            return True
    return False
