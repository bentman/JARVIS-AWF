"""One loader shape (ADR-0011): the `_require`/`_require_enum`/`_split_frontmatter`
scaffolding six registry loaders each defined independently, in one place.
Each loader passes its own error class via `error=`, so its exception types
and message text stay exactly what they were before this module existed.
"""

from collections.abc import Callable

import yaml


class RegistryValidationError(ValueError):
    pass


def require(mapping: dict, key: str, context: str, *, error: Callable = RegistryValidationError) -> object:
    if key not in mapping:
        raise error(f"{context}: missing required field '{key}'")
    return mapping[key]


def require_enum(
    value: object, allowed: tuple[str, ...], context: str, *, error: Callable = RegistryValidationError
) -> str:
    if value not in allowed:
        raise error(f"{context}: '{value}' not in {allowed}")
    return value  # type: ignore[return-value]


def split_frontmatter(text: str, *, label: str, error: Callable = RegistryValidationError) -> tuple[dict, str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise error(f"{label} must start with a '---' YAML frontmatter block")
    try:
        end = lines[1:].index("---") + 1
    except ValueError:
        raise error(f"{label} frontmatter has no closing '---'") from None

    frontmatter = yaml.safe_load("\n".join(lines[1:end])) or {}
    if not isinstance(frontmatter, dict):
        raise error(f"{label} frontmatter must be a YAML mapping")
    body = "\n".join(lines[end + 1 :]).strip()
    return frontmatter, body
