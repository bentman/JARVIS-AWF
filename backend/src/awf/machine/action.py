"""Normalized machine action payloads and digests (ADR-0021)."""

import hashlib
import json
from dataclasses import dataclass, field


@dataclass(frozen=True)
class MachineAction:
    kind: str
    run_id: str
    step_id: str
    node_id: str
    operation: str
    capability_ref: str
    risk_class: str
    approval: str
    target: dict
    body_digest: str | None = None
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        payload = {
            "kind": self.kind,
            "run_id": self.run_id,
            "step_id": self.step_id,
            "node_id": self.node_id,
            "operation": self.operation,
            "capability_ref": self.capability_ref,
            "risk_class": self.risk_class,
            "approval": self.approval,
            "target": self.target,
            "body_digest": self.body_digest,
            "metadata": self.metadata,
        }
        return {key: value for key, value in payload.items() if value is not None}

    @property
    def digest(self) -> str:
        payload = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":")).encode("utf-8")
        return "sha256:" + hashlib.sha256(payload).hexdigest()


def content_digest(payload: bytes | str) -> str:
    data = payload.encode("utf-8") if isinstance(payload, str) else payload
    return "sha256:" + hashlib.sha256(data).hexdigest()
