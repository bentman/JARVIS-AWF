"""Enforces a WorkflowDefinition's `inputSchema`/`outputSchema` (Section 12.1)
against real values.

`outputs` templates are `{{ engine.<name> }}` strings referencing values
`workflow/engine.py` tracks across a Run. Built-in engine keys include
`repairs_used`, `hops_used`, and `verdict_artifact_id`; node outputs are also
available as `<node_id>_<output_key>` with non-word characters normalized to
underscores. Rendering happens once, at Run completion, against whatever the
engine actually accumulated - an unreferenced name renders `None`, which
`outputSchema` then either accepts or correctly rejects, same as any other
value.
"""

import re

import jsonschema

_TEMPLATE_RE = re.compile(r"^\{\{\s*engine\.(\w+)\s*\}\}$")


class InputValidationError(ValueError):
    pass


class OutputValidationError(ValueError):
    pass


def _brief(exc: jsonschema.ValidationError) -> str:
    """One operator-readable line instead of jsonschema's schema dump."""
    location = ".".join(str(part) for part in exc.absolute_path)
    return f"{location}: {exc.message}" if location else exc.message


def validate_input(input_data: dict, input_schema: dict) -> None:
    try:
        jsonschema.validate(instance=input_data, schema=input_schema)
    except jsonschema.ValidationError as exc:
        raise InputValidationError(_brief(exc)) from exc


def render_outputs(outputs_spec: dict, engine_context: dict) -> dict:
    rendered = {}
    for key, template in outputs_spec.items():
        match = _TEMPLATE_RE.match(template) if isinstance(template, str) else None
        rendered[key] = engine_context.get(match.group(1)) if match else template
    return rendered


def validate_output(rendered: dict, output_schema: dict) -> None:
    try:
        jsonschema.validate(instance=rendered, schema=output_schema)
    except jsonschema.ValidationError as exc:
        raise OutputValidationError(_brief(exc)) from exc
