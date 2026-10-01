# ADR-0037: cross interface continuity and operator design system

## Status

Implemented.

## Context

ADR-0024 established the familiar control center, and ADR-0025 defined the foundational deep navy and cyan palette. As Layer 8 (Fluid Voice) and asynchronous execution (ADR-0033, ADR-0034, ADR-0036) were integrated, several usability and continuity gaps emerged across operator interfaces:
1. Visual tokens for typography, surface layering, and button hierarchy lacked a standardized scale, leading to inconsistent sizing and contrast across views.
2. Cross-panel wayfinding was disconnected: workflows executed from Chat presented run identifiers in message text, but operators had to manually switch views and search for the run to inspect execution graphs or evidence.
3. Chat and voice were visually partitioned: the voice activation panel presented redundant input fields and manual overrides directly below the chat composer rather than operating as an integrated multi-modal HUD.
4. Empty states across Operate and Library provided flat status indicators without actionable guidance for new or returning operators.

## Decision

AWF establishes a unified design system and cross-panel continuity layer for the operator interface:

1. **Standardized Visual & Typography Hierarchy:**
   - Formalize semantic typography tokens (`--text-2xs` to `--text-xl`) with explicit font-smoothing rules.
   - Establish layered glassmorphic surface tokens (`--surface-card`, `--surface-raised`, `--surface-input`, `--border-subtle`, `--border-accent`, `--shadow-card`, `--shadow-glow`).
   - Define a consistent control hierarchy: vibrant gradient primary actions, elevated glass secondary controls, distinct danger states, and custom 6px non-intrusive scrollbars.

2. **Cross-Panel Deep Linking:**
   - Implement interactive run chips within transcript entries that parse referenced run identifiers.
   - Clicking a run chip navigates directly to Operate, selects the target run, and reveals its execution graph and evidence panel.
   - Standardize view headers across Chat, Operate, and Library with cohesive kickers, titles, and contextual navigation shortcuts.

3. **Multi-Modal Voice HUD:**
   - Consolidate voice controls into an integrated HUD directly adjacent to the conversational composer.
   - Expose dynamic audio-wave pulse indicators during active listening and speech states.
   - Present live interim hypotheses directly within the viewport during continuous speech.
   - Relocate developer diagnostics and raw override inputs to an expandable drawer, preserving a clean interaction surface by default.

4. **Actionable Wayfinding & Empty States:**
   - Replace static empty-state text in Operate and Library with guided empty-state cards containing direct action buttons to kick off workflows, inspect readiness, or return to chat.

## Consequences

- Operator navigation between conversational prompts, asynchronous run graphs, and registry artifacts becomes fluid and 1-click accessible.
- Visual hierarchy and readability improve with standardized typography scales and surface contrasts across high-DPI and standard displays.
- Headless architecture remains decoupled: deep linking and presentation tokens are managed strictly within the client interface layer without altering JSON-RPC or backend contracts.
