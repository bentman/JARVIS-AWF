# Plan: Semantic Memory Context Line Rendering

## Context

`_semantic_line` in `backend/src/awf/memory/context.py` tries to read `title`, `key`, `memory_id`, `text`, `content`, and `summary` from each result dict — keys that `search_semantic_memories` never emits. Its actual output shape has `ref`, `name`, `version`, `digest`, `trust_status`, `score`, `confidence`, and `object` (which is `dataclasses.asdict(SemanticMemory)` containing `subject`, `predicate`, `value`). The fall-through in the current code reaches `json.dumps(result, sort_keys=True)` — injecting the entire record, including digest and trust metadata, into the prompt context.

The test monkeypatches the same wrong shape (`{"title", "text"}`), so it never catches the defect and validates a code path that cannot occur in production.

## What Changes

### 1. `backend/src/awf/memory/context.py` — fix `_semantic_line` only

Replace the current body with one that reads the actual result schema:

```python
def _semantic_line(result: dict) -> str:
    label = result.get("ref") or result.get("name") or "semantic memory"
    obj = result.get("object") or {}
    subject = obj.get("subject", "")
    predicate = obj.get("predicate", "")
    value = obj.get("value", "")
    body = f"{subject} {predicate} {value}".strip()
    if not body:
        body = json.dumps(result, sort_keys=True)
    confidence = result.get("confidence")
    prefix = f"{label}: {body}"
    if confidence is not None:
        return f"{prefix} (confidence={confidence})"
    return prefix
```

No other function in `context.py` changes. `_event_line`, `_append_budgeted`, and `retrieve_memory_context` are untouched.

### 2. `backend/tests/unit/test_memory_context.py` — replace the single test with two

**Test 1 — correct field rendering:**  
Mock `search_semantic_memories` with a result shaped exactly as the real function emits: top-level keys `ref`, `confidence`, `digest`, `trust_status`, and `object` containing `subject`, `predicate`, `value`. Assert the segment text:
- contains `subject`, `predicate`, and `value`
- does **not** contain `digest` or `trust_status`

```python
def test_semantic_line_renders_subject_predicate_value(monkeypatch, tmp_path):
    profile = SimpleNamespace(
        retrieval=SimpleNamespace(
            max_tokens=200, max_items=5,
            include_semantic=True, include_episodic=False,
        )
    )
    monkeypatch.setattr("awf.memory.context._profile", lambda *a, **kw: profile)
    monkeypatch.setattr(
        "awf.memory.context.search_semantic_memories",
        lambda *a, **kw: (
            {
                "ref": "claude-is-assistant@1.0.0",
                "confidence": 0.95,
                "digest": "abc123",
                "trust_status": "trusted",
                "object": {
                    "subject": "Claude Code",
                    "predicate": "is",
                    "value": "an AI coding assistant",
                },
            },
        ),
    )

    segments = retrieve_memory_context(tmp_path, None, query="Claude", profile_ref="default@1.0.0")

    assert len(segments) == 1
    text = segments[0].text
    assert "Claude Code" in text
    assert "is" in text
    assert "an AI coding assistant" in text
    assert "abc123" not in text
    assert "trust_status" not in text
```

**Test 2 — budget-skip continues retrieval (replaces the original test, correct shape):**  
Same budget-skip coverage as before, but with the real result shape so the test is honest:

```python
def test_retrieve_memory_context_skips_oversized_entries_without_stopping(monkeypatch, tmp_path):
    profile = SimpleNamespace(
        retrieval=SimpleNamespace(
            max_tokens=20, max_items=2,
            include_semantic=True, include_episodic=False,
        )
    )
    monkeypatch.setattr("awf.memory.context._profile", lambda *a, **kw: profile)
    monkeypatch.setattr(
        "awf.memory.context.search_semantic_memories",
        lambda *a, **kw: (
            {
                "ref": "big@1.0.0",
                "confidence": None,
                "object": {"subject": "x" * 200, "predicate": "is", "value": "large"},
            },
            {
                "ref": "small@1.0.0",
                "confidence": None,
                "object": {"subject": "remember", "predicate": "this", "value": "fact"},
            },
        ),
    )

    segments = retrieve_memory_context(tmp_path, None, query="q", profile_ref="default@1.0.0")

    assert len(segments) == 1
    assert "remember" in segments[0].text
```

## Files Modified

| File | Change |
|------|--------|
| `backend/src/awf/memory/context.py` | Rewrite `_semantic_line` to read `ref`/`object.subject`/`object.predicate`/`object.value` |
| `backend/tests/unit/test_memory_context.py` | Replace one test with two: field rendering + budget-skip (both with correct result shape) |

## Verification

```bash
python -m pytest backend/tests/unit/test_memory_context.py -v
```

Both tests pass. Additionally confirm that no `digest`, `trust_status`, `title`, or `text` key appears in any segment text produced by `_semantic_line` against a real `search_semantic_memories` result shape.
