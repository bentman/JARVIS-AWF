"""Conversational Intent Router.

Routes natural language utterances across four canonical intents:
- 'answer': conversational dialogue via assistant-default@1.0.0
- 'run_workflow': execute an existing workflow via op_run_start
- 'draft_workflow': author a workflow proposal via op_workflow_author_draft
- 'propose_memory': record and propose semantic memory fact
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from awf.cognition.envelope import PromptEnvelope, PromptSegment
from awf.cognition.render import render_chat
from awf.gateway.client import complete_structured
from awf.paths import REPO_ROOT
from awf.registry.model_profile import load_model_profile
from awf.registry.resolve import resolve_registry_object

INTENT_ANSWER = "answer"
INTENT_RUN_WORKFLOW = "run_workflow"
INTENT_DRAFT_WORKFLOW = "draft_workflow"
INTENT_PROPOSE_MEMORY = "propose_memory"

CANONICAL_INTENTS = (
    INTENT_ANSWER,
    INTENT_RUN_WORKFLOW,
    INTENT_DRAFT_WORKFLOW,
    INTENT_PROPOSE_MEMORY,
)

INTENT_ROUTER_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["intent", "confidence"],
    "properties": {
        "intent": {
            "type": "string",
            "enum": list(CANONICAL_INTENTS),
        },
        "target_ref": {"type": ["string", "null"]},
        "payload": {"type": "object"},
        "confidence": {"type": "number"},
        "reasoning": {"type": "string"},
    },
}


@dataclass(frozen=True)
class ClassifiedIntent:
    intent: str
    target_ref: str | None = None
    payload: dict = field(default_factory=dict)
    confidence: float = 1.0
    source: str = "deterministic"  # "deterministic" | "model" | "fallback"
    raw_text: str = ""

    def to_dict(self) -> dict:
        return {
            "intent": self.intent,
            "target_ref": self.target_ref,
            "payload": self.payload,
            "confidence": self.confidence,
            "source": self.source,
            "raw_text": self.raw_text,
        }


def _match_deterministic_pattern(text: str) -> ClassifiedIntent | None:
    trimmed = text.strip()

    # 1. run_workflow patterns: "run workflow <name>", "run <name>", "start workflow <name>", "execute workflow <name>"
    run_match = re.match(
        r"^(?:run\s+workflow|start\s+workflow|execute\s+workflow|run)\s+([a-zA-Z0-9_\-\.\@]+)(?:\s+(?:with\s+objective|objective|for)\s+(.+))?$",
        trimmed,
        re.IGNORECASE,
    )
    if run_match:
        ref = run_match.group(1).strip()
        obj = run_match.group(2).strip() if run_match.group(2) else ""
        # Do not mistake conversational "run" phrases like "run through this" as a workflow ref
        if not ref.lower().endswith((".py", ".sh", ".md", ".txt")) and ref.lower() not in {
            "through",
            "by",
            "away",
            "out",
            "over",
        }:
            payload = {"objective": obj or f"Execute {ref}"}
            return ClassifiedIntent(
                intent=INTENT_RUN_WORKFLOW,
                target_ref=ref,
                payload=payload,
                confidence=0.95,
                source="deterministic",
                raw_text=trimmed,
            )

    # 2. draft_workflow patterns: "draft workflow <desc>", "create workflow <desc>", "author workflow <desc>", "make workflow <desc>"
    draft_match = re.match(
        r"^(?:draft\s+workflow|create\s+workflow|author\s+workflow|make\s+workflow|author\s+draft)(?:\s+(?:for|to|called)?\s*(.+))?$",
        trimmed,
        re.IGNORECASE,
    )
    if draft_match:
        desc = draft_match.group(1).strip() if draft_match.group(1) else trimmed
        return ClassifiedIntent(
            intent=INTENT_DRAFT_WORKFLOW,
            target_ref=None,
            payload={"objective": desc},
            confidence=0.95,
            source="deterministic",
            raw_text=trimmed,
        )

    # 3. propose_memory patterns: "remember that <fact>", "remember <fact>", "note that <fact>", "save memory <fact>"
    mem_match = re.match(
        r"^(?:remember\s+that|remember|note\s+that|save\s+memory|store\s+memory)\s+(.+)$",
        trimmed,
        re.IGNORECASE,
    )
    if mem_match:
        fact = mem_match.group(1).strip()
        return ClassifiedIntent(
            intent=INTENT_PROPOSE_MEMORY,
            target_ref=None,
            payload={"fact": fact},
            confidence=0.95,
            source="deterministic",
            raw_text=trimmed,
        )

    return None


def _classify_with_model(
    repo_root: Path,
    conn: sqlite3.Connection,
    text: str,
    *,
    profile_ref: str = "resident-mind@1.0.0",
) -> ClassifiedIntent:
    name, _, version = profile_ref.partition("@")
    profile_path, _ = resolve_registry_object(repo_root, "model-profiles", name, version or "1.0.0", conn=conn)
    profile = load_model_profile(profile_path)

    envelope = PromptEnvelope(
        segments=(
            PromptSegment(
                "application",
                "instruction",
                True,
                "You are the AWF conversational intent router. Classify the user input into exactly one of four intents:\n"
                "- 'run_workflow': if the operator asks to execute, start, or run a workflow by name or description.\n"
                "- 'draft_workflow': if the operator asks to create, author, or design a new workflow.\n"
                "- 'propose_memory': if the operator asks to remember, note, or save a persistent fact or preference.\n"
                "- 'answer': for conversational questions, system queries, advice, or general chat.\n\n"
                "Return a structured JSON object matching the schema.",
            ),
            PromptSegment("user", "input", False, text),
        )
    )

    chat = render_chat(envelope)
    data = complete_structured(
        profile,
        chat.messages,
        INTENT_ROUTER_SCHEMA,
        schema_name="intent_classification",
        conn=conn,
        actor="intent-router",
        repo_root=repo_root,
    )

    intent = data.get("intent", INTENT_ANSWER)
    if intent not in CANONICAL_INTENTS:
        intent = INTENT_ANSWER

    return ClassifiedIntent(
        intent=intent,
        target_ref=data.get("target_ref"),
        payload=data.get("payload") or {},
        confidence=float(data.get("confidence", 0.8)),
        source="model",
        raw_text=text,
    )


def classify_intent(
    repo_root: Path = REPO_ROOT,
    conn: sqlite3.Connection | None = None,
    text: str = "",
    *,
    profile_ref: str = "resident-mind@1.0.0",
) -> ClassifiedIntent:
    trimmed = text.strip()
    if not trimmed:
        return ClassifiedIntent(intent=INTENT_ANSWER, raw_text="")

    # 1. Deterministic rule check
    matched = _match_deterministic_pattern(trimmed)
    if matched is not None:
        return matched

    # 2. Model-assisted classification
    if conn is not None:
        try:
            return _classify_with_model(repo_root, conn, trimmed, profile_ref=profile_ref)
        except Exception:
            pass

    # 3. Fallback
    return ClassifiedIntent(
        intent=INTENT_ANSWER,
        confidence=0.5,
        source="fallback",
        raw_text=trimmed,
    )
