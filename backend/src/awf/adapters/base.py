"""Generic Agent Runtime Adapter contract (Section 10.1).

Every adapter - named or future - normalizes to these two envelopes.
`COMPLETED` means the invocation satisfied its completion contract; it does
NOT mean accepted - acceptance is computed by the Gate node (Section 12.3),
never by the agent itself.
"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class AgentStatus(Enum):
    COMPLETED = "COMPLETED"
    NEEDS_INPUT = "NEEDS_INPUT"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    LIMIT_EXCEEDED = "LIMIT_EXCEEDED"
    CANCELED = "CANCELED"


@dataclass(frozen=True)
class AgentInvocation:
    objective: str
    inputs: dict
    workspace_root: Path
    capabilities: tuple[str, ...] = ()
    skills: tuple[str, ...] = ()
    constraints: dict = field(default_factory=dict)
    completion_contract: str = ""
    trace_context: dict = field(default_factory=dict)


@dataclass(frozen=True)
class AgentResult:
    status: AgentStatus
    output: dict
    artifact_candidates: tuple[str, ...] = ()
    findings: tuple[dict, ...] = ()
    usage: dict = field(default_factory=dict)
    termination_reason: str = ""
