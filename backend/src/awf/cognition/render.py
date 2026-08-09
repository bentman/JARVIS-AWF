"""Prompt envelope renderers (ADR-0018)."""

from dataclasses import dataclass

from awf.cognition.envelope import PromptEnvelope, PromptSegment, SYSTEM_AUTHORITIES


@dataclass(frozen=True)
class ChatPrompt:
    system_text: str
    user_text: str
    messages: list[dict[str, str]]
    generation: dict


def _header(segment: PromptSegment) -> str:
    suffix = "" if segment.trusted else ", untrusted"
    return f"[{segment.authority}/{segment.content_type}{suffix}]"


def _render_segment(segment: PromptSegment) -> str:
    return f"{_header(segment)}\n{segment.text.strip()}"


def render_flat(envelope: PromptEnvelope) -> str:
    return "\n\n".join(_render_segment(segment) for segment in envelope.segments if segment.text.strip())


def render_chat(envelope: PromptEnvelope) -> ChatPrompt:
    system_parts: list[str] = []
    user_parts: list[str] = []
    for segment in envelope.segments:
        if not segment.text.strip():
            continue
        rendered = _render_segment(segment)
        if segment.trusted and segment.authority in SYSTEM_AUTHORITIES:
            system_parts.append(rendered)
        else:
            user_parts.append(rendered)

    system_text = "\n\n".join(system_parts)
    user_text = "\n\n".join(user_parts)
    messages: list[dict[str, str]] = []
    if system_text:
        messages.append({"role": "system", "content": system_text})
    messages.extend(dict(message) for message in envelope.example_messages)
    if user_text:
        messages.append({"role": "user", "content": user_text})

    return ChatPrompt(
        system_text=system_text,
        user_text=user_text,
        messages=messages,
        generation=dict(envelope.generation),
    )
