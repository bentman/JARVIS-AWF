from types import SimpleNamespace

from awf.memory.context import retrieve_memory_context


def test_retrieve_memory_context_skips_oversized_entries_without_stopping(monkeypatch, tmp_path):
    profile = SimpleNamespace(
        retrieval=SimpleNamespace(
            max_tokens=20,
            max_items=2,
            include_semantic=True,
            include_episodic=False,
        )
    )
    monkeypatch.setattr("awf.memory.context._profile", lambda repo_root, profile_ref, conn=None: profile)
    monkeypatch.setattr(
        "awf.memory.context.search_semantic_memories",
        lambda repo_root, conn, *, query, profile_ref: (
            {"title": "too large", "text": "x" * 200},
            {"title": "small", "text": "remember this"},
        ),
    )

    segments = retrieve_memory_context(tmp_path, None, query="remember", profile_ref="default@1.0.0")

    assert len(segments) == 1
    assert segments[0].text == "small: remember this"
