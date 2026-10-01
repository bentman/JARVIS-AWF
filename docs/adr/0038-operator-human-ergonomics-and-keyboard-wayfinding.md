# ADR-0038: operator human ergonomics and keyboard wayfinding

## Status

Implemented.

## Context

While ADR-0037 established visual tokens and cross-panel deep linking, operator daily usability remained constrained by mouse dependency, inspector navigation friction, and incomplete theme fidelity:

1. **Mouse-Heavy Interaction Loop:**
   - Navigating between Operate, Chat, and Library required clicking nav buttons.
   - Focusing the prompt composer required manual cursor positioning.
   - Dismissing active run inspectors or approval dialogs lacked standard keyboard shortcuts (`Escape`, `Ctrl+Enter`).
   - In the CLI, repeating previous commands required retyping without history recall, and slash commands lacked Tab completion.

2. **Inspector Wayfinding & Dismissability:**
   - Selecting a run in Operate opened an extensive run timeline and evidence graph without an explicit dismiss or close button, cluttering the view when operators sought to review other queue items.
   - Deep-linking into a run from Chat did not auto-scroll to the newly rendered inspector.
   - Top-level header status indicators (readiness, pending approvals) functioned purely as static indicators rather than actionable navigation waypoints.

3. **Theme Parity & Discovery Ergonomics:**
   - The settings contract declared `theme: "dark" | "light" | "system"`, yet the CSS design system lacked a dedicated light palette token specification.
   - Empty chat states offered no concrete prompt suggestions for new or returning operators.
   - Message bubbles lacked 1-click clipboard extraction for generated commands, error logs, or execution IDs.

## Decision

AWF establishes a unified human ergonomics and keyboard wayfinding layer across the operator interfaces:

1. **Global Keyboard Ergonomics (GUI & CLI):**
   - Register global window shortcuts in the GUI shell:
     - `Ctrl+1` / `Cmd+1`: Switch to Operate.
     - `Ctrl+2` / `Cmd+2`: Switch to Chat.
     - `Ctrl+3` / `Cmd+3`: Switch to Library.
     - `Ctrl+K` / `Cmd+K`: Focus active text input (composer, search, or workflow launch).
     - `Escape`: Close active run inspector, artifact view, or modal.
     - `Ctrl+Enter`: Trigger primary approval or submission.
   - Render keyboard hint badges on navigation items and composer footers.
   - Implement command history navigation (Up/Down arrows) and Tab autocompletion for slash commands in the CLI TUI.

2. **Run Inspector Dismissability & Wayfinding:**
   - Equip `RunTimeline` with an explicit inspector header, breadcrumb path (`Operate > Runs > <run_id>`), and dismiss action (`Close Inspector` with `Esc` indicator).
   - Auto-scroll smoothly to `#selected-run-inspector` when run details are requested.
   - Transform topbar status chips into interactive waypoints that scroll directly to System Readiness or Approvals upon activation.

3. **Accessible Light Theme & Focus Outlines:**
   - Provide a complete `[data-theme="light"]` token specification in `styles.css` utilizing slate base tones, high-contrast typography, and compliant ready/warn/danger state chips.
   - Enforce visible, glowing `:focus-visible` outlines on all interactive elements for accessible keyboard navigation.

4. **Discovery Starter Prompts & Copy Actions:**
   - Populate empty conversation viewports with suggested starter prompt chips ("Check system readiness", "List active workflows", "Summarize recent runs").
   - Attach 1-click clipboard copy actions to conversation bubbles with ephemeral feedback.

## Consequences

- Operators can perform routine operational loops—switching views, checking readiness, reviewing approvals, and submitting commands—entirely via keyboard.
- Inspecting and dismissing complex execution timelines is fluid without losing queue context.
- System color preference (`theme: "light"`) is fully supported with accessible WCAG AA contrast.
- Core architecture remains headless; all ergonomics improvements reside in the presentation layer.
