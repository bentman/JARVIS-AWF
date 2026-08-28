"""Authority-tagged prompt envelope primitives (ADR-0018)."""

from dataclasses import dataclass, field

AUTHORITIES = ("application", "persona", "contract", "session", "memory", "retrieval", "skill", "tool", "user")
CONTENT_TYPES = ("instruction", "style", "context", "result", "input", "contract")
SYSTEM_AUTHORITIES = ("application", "persona", "contract")


@dataclass(frozen=True)
class PromptSegment:
    authority: str
    content_type: str
    trusted: bool
    text: str

    def __post_init__(self) -> None:
        if self.authority not in AUTHORITIES:
            raise ValueError(f"unknown prompt authority '{self.authority}'")
        if self.content_type not in CONTENT_TYPES:
            raise ValueError(f"unknown prompt content type '{self.content_type}'")


@dataclass(frozen=True)
class PromptEnvelope:
    segments: tuple[PromptSegment, ...] = ()
    example_messages: tuple[dict[str, str], ...] = ()
    generation: dict = field(default_factory=dict)
