"""Shared registry validation helpers."""

from collections.abc import Callable

import yaml
from jsonschema import Draft202012Validator, ValidationError

_VALIDATOR_CACHE: dict[int, Draft202012Validator] = {}


def _get_validator(schema: dict) -> Draft202012Validator:
    key = id(schema)
    validator = _VALIDATOR_CACHE.get(key)
    if validator is None:
        validator = Draft202012Validator(schema)
        _VALIDATOR_CACHE[key] = validator
    return validator


class RegistryValidationError(ValueError):
    pass


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


def validate_json_schema(raw: dict, schema: dict, context: str, *, error: Callable = RegistryValidationError) -> None:
    validator = _get_validator(schema)
    try:
        validator.validate(instance=raw)
    except ValidationError as exc:
        path = ".".join(str(part) for part in exc.absolute_path)
        location = f"{context}.{path}" if path else context
        raise error(f"{location}: {exc.message}") from exc


def validate_registry_identity(
    *,
    name: str,
    version: str,
    path,
    context: str,
    error: Callable = RegistryValidationError,
) -> None:
    if name != path.parent.name:
        raise error(f"{context} name '{name}' does not match its registry directory '{path.parent.name}'")
    if version != path.stem:
        raise error(f"{context} version '{version}' does not match its file name '{path.stem}'")
