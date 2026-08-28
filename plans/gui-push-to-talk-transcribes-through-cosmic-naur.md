# Plan: MCP Renderers Reduced to the Guarded Adapter Set

## Context

`backend/src/awf/mcp/render.py` contains five renderers: `render_claude_code`, `render_codex`, `render_antigravity`, `render_copilot`, and `render_cline`. `_apply_mcp` in `engine/agent_step.py` raises `POLICY_DENIED` for any adapter not in `GUARDED_MCP_ADAPTERS = {"copilot"}` before reaching the renderer lookup. The four non-copilot renderers are therefore unreachable through any execution path. The test file exercises all five as pure functions, so coverage does not distinguish reachable from dead code.

Per YAGNI: no caller exists and none can be added without a per-adapter pre-tool guard hook. Removing the four dead renderers makes the invariant `set(RENDERERS) == GUARDED_MCP_ADAPTERS` explicit and enforced by a test.

Scope is strictly `render.py` and its test file. `agent_step.py` is not in scope — the scratch-$HOME and home_copy_paths handling in `_apply_mcp` becomes dead but is left for a later cleanup once the dataclass contract settles.

## What Changes

### 1. `backend/src/awf/mcp/render.py`

**Delete** the four unreachable renderer functions:
- `render_claude_code` (and its helpers that are exclusive to it, if any)
- `render_codex`
- `render_antigravity`
- `render_cline`

**Keep** `render_copilot`, all shared helpers (`_secret_env_var_name`, `_env_overlay_for`), the `RenderedMcpConfig` dataclass, and all imports still needed by the copilot renderer.

**Reduce RENDERERS** to:
```python
RENDERERS = {
    "copilot": render_copilot,
}
```

No changes to `_apply_mcp`, `GUARDED_MCP_ADAPTERS`, or anything in `agent_step.py`.

### 2. `backend/tests/unit/test_registry_mcp_render.py`

**Delete** all tests covering the four removed renderers:
- `test_no_servers_renders_nothing_for_every_adapter` (covers all adapters — rewrite or remove)
- All `test_claude_code_*` tests
- All `test_codex_*` tests
- All `test_antigravity_*` tests
- All `test_cline_*` tests

**Keep** the copilot test and the `fetch_server` fixture (used by it). Remove the `context7_server` fixture if no remaining test uses it.

**Add** a guard assertion test:
```python
def test_renderers_match_guarded_mcp_adapters():
    from awf.engine.agent_step import GUARDED_MCP_ADAPTERS
    from awf.mcp.render import RENDERERS
    assert set(RENDERERS) == GUARDED_MCP_ADAPTERS
```

If `test_no_servers_renders_nothing_for_every_adapter` is retained, rewrite it to cover only `copilot`:
```python
def test_no_servers_renders_nothing_for_copilot():
    rendered = render_copilot([])
    assert rendered.relative_path is not None or rendered.contents == ...
    # or simply assert it doesn't raise and returns a RenderedMcpConfig
```
(Adjust to the actual copilot empty-list behavior — check what the current test asserts for copilot specifically.)

## Files Modified

| File | Change |
|------|--------|
| `backend/src/awf/mcp/render.py` | Delete four renderer functions; reduce RENDERERS to `{"copilot": render_copilot}` |
| `backend/tests/unit/test_registry_mcp_render.py` | Delete tests for removed renderers; add `test_renderers_match_guarded_mcp_adapters` |

## Verification

```
.\backend\.venv\Scripts\python.exe -m pytest backend/tests/unit/test_registry_mcp_render.py -v
```

All remaining tests pass. `set(RENDERERS) == GUARDED_MCP_ADAPTERS` is asserted by the new test. Confirm `render.py` has no references to `render_claude_code`, `render_codex`, `render_antigravity`, or `render_cline`.
