import pytest

from awf.workflow.io_schema import (
    InputValidationError,
    OutputValidationError,
    render_outputs,
    validate_input,
    validate_output,
)


def test_validate_input_accepts_conforming_data():
    validate_input({"objective": "do a thing"}, {"type": "object", "required": ["objective"]})


def test_validate_input_rejects_missing_required_field():
    with pytest.raises(InputValidationError):
        validate_input({}, {"type": "object", "required": ["objective"]})


def test_render_outputs_resolves_engine_template():
    rendered = render_outputs({"repairs": "{{ engine.repairs_used }}"}, {"repairs_used": 2, "hops_used": 0})
    assert rendered == {"repairs": 2}


def test_render_outputs_passes_through_literal_values():
    rendered = render_outputs({"note": "static text"}, {})
    assert rendered == {"note": "static text"}


def test_render_outputs_unresolvable_reference_renders_none():
    rendered = render_outputs({"missing": "{{ engine.nonexistent }}"}, {"repairs_used": 0})
    assert rendered == {"missing": None}


def test_validate_output_accepts_conforming_data():
    validate_output({"repairs": 2}, {"type": "object", "properties": {"repairs": {"type": "integer"}}})


def test_validate_output_rejects_type_mismatch():
    with pytest.raises(OutputValidationError):
        validate_output(
            {"repairs": None},
            {"type": "object", "properties": {"repairs": {"type": "integer"}}, "required": ["repairs"]},
        )
