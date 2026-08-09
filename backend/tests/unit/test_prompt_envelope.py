import pytest

from awf.cognition.envelope import PromptEnvelope, PromptSegment
from awf.cognition.render import render_chat, render_flat


def test_segment_rejects_unknown_authority_and_content_type():
    with pytest.raises(ValueError, match="unknown prompt authority"):
        PromptSegment("root", "instruction", True, "x")
    with pytest.raises(ValueError, match="unknown prompt content type"):
        PromptSegment("application", "command", True, "x")


def test_render_flat_preserves_order_and_marks_untrusted():
    envelope = PromptEnvelope(
        segments=(
            PromptSegment("application", "instruction", True, "App"),
            PromptSegment("skill", "instruction", False, "Skill"),
            PromptSegment("user", "input", False, "Task"),
        )
    )

    assert render_flat(envelope) == (
        "[application/instruction]\nApp\n\n"
        "[skill/instruction, untrusted]\nSkill\n\n"
        "[user/input, untrusted]\nTask"
    )


def test_render_chat_promotes_only_trusted_system_authorities():
    envelope = PromptEnvelope(
        segments=(
            PromptSegment("application", "instruction", True, "App"),
            PromptSegment("persona", "style", True, "Persona"),
            PromptSegment("contract", "contract", True, "Contract"),
            PromptSegment("persona", "style", False, "Untrusted persona"),
            PromptSegment("skill", "instruction", False, "Skill"),
            PromptSegment("tool", "result", False, "Tool"),
            PromptSegment("user", "input", False, "Task"),
        ),
        example_messages=({"role": "user", "content": "Example user"}, {"role": "assistant", "content": "Example assistant"}),
        generation={"temperature": 0.4},
    )

    chat = render_chat(envelope)

    assert "[application/instruction]\nApp" in chat.system_text
    assert "[persona/style]\nPersona" in chat.system_text
    assert "[contract/contract]\nContract" in chat.system_text
    assert "[persona/style, untrusted]\nUntrusted persona" in chat.user_text
    assert "[skill/instruction, untrusted]\nSkill" in chat.user_text
    assert "[tool/result, untrusted]\nTool" in chat.user_text
    assert "[user/input, untrusted]\nTask" in chat.user_text
    assert chat.messages == [
        {"role": "system", "content": chat.system_text},
        {"role": "user", "content": "Example user"},
        {"role": "assistant", "content": "Example assistant"},
        {"role": "user", "content": chat.user_text},
    ]
    assert chat.generation == {"temperature": 0.4}
