"""Unit tests for the Conversational Intent Router (ADR-0034)."""

from awf.cognition.router import (
    INTENT_ANSWER,
    INTENT_DRAFT_WORKFLOW,
    INTENT_PROPOSE_MEMORY,
    INTENT_RUN_WORKFLOW,
    _match_deterministic_pattern,
    classify_intent,
)


def test_deterministic_run_workflow_patterns():
    # Direct "run <workflow>"
    intent1 = _match_deterministic_pattern("run demo")
    assert intent1 is not None
    assert intent1.intent == INTENT_RUN_WORKFLOW
    assert intent1.target_ref == "demo"
    assert intent1.source == "deterministic"

    # "run workflow <name> with objective <obj>"
    intent2 = _match_deterministic_pattern("run workflow deploy@1.0.0 with objective ship to prod")
    assert intent2 is not None
    assert intent2.intent == INTENT_RUN_WORKFLOW
    assert intent2.target_ref == "deploy@1.0.0"
    assert intent2.payload == {"objective": "ship to prod"}

    # "start workflow <name>"
    intent3 = _match_deterministic_pattern("start workflow smoke-test")
    assert intent3 is not None
    assert intent3.intent == INTENT_RUN_WORKFLOW
    assert intent3.target_ref == "smoke-test"

    # "execute workflow <name>"
    intent4 = _match_deterministic_pattern("execute workflow backup-db for night run")
    assert intent4 is not None
    assert intent4.intent == INTENT_RUN_WORKFLOW
    assert intent4.target_ref == "backup-db"
    assert intent4.payload == {"objective": "night run"}


def test_deterministic_draft_workflow_patterns():
    # "draft workflow <desc>"
    intent1 = _match_deterministic_pattern("draft workflow that restarts nginx")
    assert intent1 is not None
    assert intent1.intent == INTENT_DRAFT_WORKFLOW
    assert intent1.payload == {"objective": "that restarts nginx"}

    # "create workflow <desc>"
    intent2 = _match_deterministic_pattern("create workflow for log rotation")
    assert intent2 is not None
    assert intent2.intent == INTENT_DRAFT_WORKFLOW
    assert intent2.payload == {"objective": "log rotation"}

    # "author workflow <desc>"
    intent3 = _match_deterministic_pattern("author workflow clean temp directory")
    assert intent3 is not None
    assert intent3.intent == INTENT_DRAFT_WORKFLOW
    assert intent3.payload == {"objective": "clean temp directory"}


def test_deterministic_propose_memory_patterns():
    # "remember that <fact>"
    intent1 = _match_deterministic_pattern("remember that staging server IP is 10.0.0.1")
    assert intent1 is not None
    assert intent1.intent == INTENT_PROPOSE_MEMORY
    assert intent1.payload == {"fact": "staging server IP is 10.0.0.1"}

    # "note that <fact>"
    intent2 = _match_deterministic_pattern("note that operator timezone is CST")
    assert intent2 is not None
    assert intent2.intent == INTENT_PROPOSE_MEMORY
    assert intent2.payload == {"fact": "operator timezone is CST"}

    # "save memory <fact>"
    intent3 = _match_deterministic_pattern("save memory operator prefers python 3.12")
    assert intent3 is not None
    assert intent3.intent == INTENT_PROPOSE_MEMORY
    assert intent3.payload == {"fact": "operator prefers python 3.12"}


def test_classify_intent_empty_text():
    intent = classify_intent(text="")
    assert intent.intent == INTENT_ANSWER
    assert intent.raw_text == ""


def test_classify_intent_fallback_without_connection():
    # Utterance without deterministic pattern and without db connection falls back to answer
    intent = classify_intent(text="how does the capability guard work?")
    assert intent.intent == INTENT_ANSWER
    assert intent.source == "fallback"


def test_classify_intent_with_mocked_model(monkeypatch, tmp_path):
    # Mock complete_structured to test model-assisted classification
    mock_payload = {
        "intent": "draft_workflow",
        "target_ref": None,
        "payload": {"objective": "deploy to kubernetes"},
        "confidence": 0.88,
        "reasoning": "User is asking to build a k8s deployment workflow",
    }
    monkeypatch.setattr("awf.cognition.router.complete_structured", lambda *args, **kwargs: mock_payload)
    monkeypatch.setattr("awf.cognition.router.resolve_registry_object", lambda *args, **kwargs: (tmp_path, "test"))
    monkeypatch.setattr("awf.cognition.router.load_model_profile", lambda *args: None)

    class FakeConn:
        pass

    intent = classify_intent(text="Could you build a pipeline that pushes containers to k8s?", conn=FakeConn())
    assert intent.intent == INTENT_DRAFT_WORKFLOW
    assert intent.source == "model"
    assert intent.confidence == 0.88
    assert intent.payload == {"objective": "deploy to kubernetes"}


def test_classify_intent_model_failure_falls_back_gracefully(monkeypatch):
    def fake_complete(*args, **kwargs):
        raise RuntimeError("LLM offline")

    monkeypatch.setattr("awf.cognition.router.complete_structured", fake_complete)

    class FakeConn:
        pass

    intent = classify_intent(text="Could you help me with this?", conn=FakeConn())
    assert intent.intent == INTENT_ANSWER
    assert intent.source == "fallback"
