from types import SimpleNamespace

from awf.memory.context import retrieve_memory_context


def _profile(max_tokens, max_items):
    return SimpleNamespace(
        retrieval=SimpleNamespace(
            max_tokens=max_tokens,
            max_items=max_items,
            include_semantic=True,
            include_episodic=False,
        )
    )


def test_semantic_line_renders_subject_predicate_value(monkeypatch, tmp_path):
    monkeypatch.setattr("awf.memory.context._profile", lambda *a, **kw: _profile(200, 5))
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


def test_retrieve_memory_context_skips_oversized_entries_without_stopping(monkeypatch, tmp_path):
    monkeypatch.setattr("awf.memory.context._profile", lambda *a, **kw: _profile(20, 2))
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
