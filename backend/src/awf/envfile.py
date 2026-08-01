"""Minimal .env parsing/editing — stdlib only, no third-party dependency for a KEY=VALUE format."""

from pathlib import Path


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        values[key.strip()] = value.strip()
    return values


def get_env_value(path: Path, key: str) -> str:
    values = parse_env_file(path)
    if key not in values:
        raise KeyError(f"{key} not found in {path}")
    return values[key]


def set_env_value(path: Path, key: str, value: str) -> None:
    lines = path.read_text().splitlines()
    prefix = f"{key}="
    for i, line in enumerate(lines):
        if line.strip().startswith(prefix):
            lines[i] = f"{key}={value}"
            break
    else:
        lines.append(f"{key}={value}")
    path.write_text("\n".join(lines) + "\n")
