# ADR-0025: control-center look and usability

## Status

Implemented, with one presentation correction pending: the navigation shape.

Scope is AWF-GUI only. The CLI and TUI reach their own ADR-0024 targets in a
separate record.

## Context

ADR-0024 delivered the control-center data path: `awf/control.summary`,
`awf/control.runDetail`, `awf/system.readiness`, and `awf/llm.*` reach the
renderer through narrow IPC, and the panels display real protocol data —
readiness rows, LLM state and model catalog, hardware tokens/inventory, a
registry browse-then-act flow, an artifact/diff viewer, run timeline, and
improvement proposals. That substance is real, implemented, and covered by
the GUI test suite (`Overview.tsx`, `RunsView.tsx`, `ApprovalsView.tsx`,
`Dashboard.tsx`, `RegistryActions.tsx`, `ApprovalConfirmation.tsx`,
`ProposalReview.tsx`, `MemoryPanel.tsx`, `Transcript.tsx`,
`VoiceActivation.tsx`, `state.ts`).

This record went through two presentation revisions before landing on the
current decision:

1. A left-side vertical rail with one active view and a persistent status
   bar. This shipped and is what the repository currently contains outside
   the shell itself: a dark token set (`#0a0a0b` background, `#e2e8f0` text,
   `#22d3ee` cyan accent, `#34d399` emerald, Inter/JetBrains Mono), cards,
   chips, a `stateClass()` helper driving all status colour, and 50 passing
   GUI tests. The rail's own markup and CSS (`.rail`, `.rail-nav`,
   `.rail-item`) is the one piece this record now replaces.
2. A three-column always-visible console with a different navy token set,
   drafted but never implemented — rejected before any file was touched. An
   operator who can only see one workflow at a glance in a compact desktop
   window does not need every panel visible simultaneously; the one-active-
   view model from revision 1 was the right shape, only the wrong nav
   orientation.

The reference for this record is `../JARVISvX2/` — a sibling prototype
(Electron + React + Tailwind), consulted for its **colour scheme and layout
shape only**, not copied wholesale. Reading `src/index.css`,
`src/App.tsx`, and `src/components/Header.tsx` there confirms that revision
1's token values already match vX2's exactly (same `#0a0a0b`/`#e2e8f0`/
`#22d3ee`/`#34d399` hex values, same font stack) — the lineage is shared.
What revision 1 lacks relative to vX2 is:

- vX2's navigation is a **sticky top header** — brand left, a horizontal row
  of view-select buttons centre, status pills right — not a left rail.
- vX2's panels use a **glass/blur treatment**
  (`backdrop-filter: blur()` over translucent surfaces) and soft accent-
  coloured glows on active/primary elements; revision 1's cards are flat.
- vX2 uses `lucide-react` icons and Tailwind utility spacing sized for a wide
  desktop web page; neither is appropriate here (no new dependency, and
  AWF-GUI's window is a compact desktop app, not a browser tab).
- vX2's `VoiceOrb.tsx` renders an animated canvas particle visualization for
  voice state. This is explicitly excluded — out of scope, adds a canvas
  render loop and complexity for a text-first control surface (ADR-0023's
  text-first invariant already covers voice state legibility via the
  existing status chip and transcript).

## Decision

**Navigation is a sticky top header, not a rail, and not a three-column
console.** `App.tsx` keeps the one-active-view model it already has —
`ViewName`, the `views` array derived from callback presence, `activeView`,
every child component's existing conditional-render guard — and moves the
nav itself from a left `<aside className="rail">` into a top
`<header className="topbar">`: brand on the left, the same view-select
buttons now laid out horizontally (wrapping/scrolling at narrow widths
instead of collapsing to a horizontal strip, since they're horizontal
already), the same three status chips (readiness, LLM state, pending-approval
count), and the same Refresh button — all in one row instead of split
between a sidebar and a separate bar.

**Glass panel treatment, referenced from vX2's values, not its stack.**
`.card` and `.topbar` gain `backdrop-filter: blur(12px)` (and the
`-webkit-` prefix) over their existing translucent `--surface`/
`--surface-raised` backgrounds, and the active nav item plus primary buttons
gain a soft `box-shadow` glow using the existing `--accent`/`--ok` custom
properties. No new colour tokens — revision 1's palette already matches
vX2's.

**No animated voice orb.** `VoiceActivation.tsx` keeps its existing
text/button-based controls (status chip, stacked fields, button row). No
canvas element, no particle animation, is added anywhere.

**More compact than vX2's own spacing, not a straight port.** vX2's Tailwind
classes (`px-3 py-1.5`, `gap-4`) target a wide browser layout. AWF-GUI keeps
its existing tighter token scale (`--space-1` through `--space-6`, 4–32px)
and the top bar itself uses the smaller end of that scale so the nav row
stays compact rather than adopting vX2's larger touch-target sizing.

**No new dependency.** No Tailwind, no `lucide-react` or any other icon
library — nav buttons stay text-label-only, consistent with every other
decision in this record's history.

**Accessible names are preserved exactly.** Every existing `role` and
`aria-label` string stays byte-identical. This is now trivially true rather
than merely promised: no component below the shell (`Overview`, `RunsView`,
`ApprovalsView`, `Dashboard`, `RegistryActions`, `ApprovalConfirmation`,
`ProposalReview`, `MemoryPanel`, `Transcript`, `VoiceActivation`) changes at
all — only the shell/nav markup around them moves from a sidebar to a header,
and every prop threaded into them is unchanged.

## Deviation recorded

None. This record changes only `frontend/gui/src/renderer/App.tsx`,
`frontend/gui/src/renderer/styles.css`, and (if the new layout's minimum
window size differs from the rail's) `frontend/gui/src/main/main.ts`'s
`BrowserWindow` options. No protocol method, IPC channel, backend operation,
registry object, or authorization path is touched.

## Mechanism

### Shell and top bar

`.shell` changes from the rail revision's two-column grid
(`grid-template-columns: var(--rail-width) minmax(0, 1fr)`) to a single
flex column (`display: flex; flex-direction: column; min-height: 100vh`).

`.rail`/`.rail-nav`/`.rail-item` are replaced by:

- `.topbar` — the header itself: horizontal flex, `flex-wrap: wrap` so it
  degrades gracefully at narrow widths instead of needing the rail's old
  `@media (max-width: 900px)` collapse rule (which is deleted — a wrapping
  horizontal bar needs no separate narrow-width layout), `backdrop-filter:
  blur(12px)` plus `-webkit-backdrop-filter`, sticky positioning
  (`position: sticky; top: 0; z-index: 10`) so it stays visible while `.main`
  scrolls beneath it.
- `.nav-list` — the view-button row itself: horizontal flex,
  `overflow-x: auto` so it scrolls rather than wraps mid-button if the window
  is narrower than the button row (matching vX2's `overflow-x-auto` on its
  nav).
- `.nav-item` — same properties `.rail-item` had (background/border/colour
  transitions, `[aria-current="page"]` active state), oriented for a
  horizontal row instead of a vertical stack, plus a `box-shadow` glow on the
  active item using `--accent`.

`.rail-badge` (the Approvals/Proposals count badge), `.status-bar`, `.main`,
`.card`, `.list`, `.row`, `.chip`, every `.btn*` variant, inputs,
`.pre-scroll`, `.transcript-*`, `.empty`, and the scrollbar rules are
unchanged — none of them describe the nav, all of them describe content that
doesn't know or care what shape the nav above it takes.

### Glass and glow

`.card` gains the same `backdrop-filter: blur(12px)` the top bar has, over
its existing `--surface` background — matching vX2's `.glass-panel` treatment
by value (vX2: `background: rgba(18, 18, 22, 0.7); backdrop-filter:
blur(16px)`, already equal to this repo's `--surface-raised` token).
`.btn-primary` and `.nav-item[aria-current="page"]` gain a `box-shadow` glow
(`0 0 20px` at low opacity, using `--accent` for nav/primary buttons,
`--ok` where a success/ready state is being emphasized) — matching vX2's
`.glow-cyan`/`.glow-emerald` utility classes by value, expressed as plain
selectors instead of Tailwind utilities.

## Layout delta

```text
frontend/gui/
  src/
    main/main.ts                     (BrowserWindow minimums re-checked for the narrower shell)
    renderer/
      App.tsx                        (rail markup -> header/topbar markup; view logic unchanged)
      styles.css                     (.rail/.rail-nav/.rail-item -> .topbar/.nav-list/.nav-item; glass/glow added)
      Overview.tsx                   (unchanged)
      RunsView.tsx                   (unchanged)
      ApprovalsView.tsx              (unchanged)
      Dashboard.tsx                  (unchanged)
      RegistryActions.tsx            (unchanged)
      ApprovalConfirmation.tsx       (unchanged)
      ProposalReview.tsx             (unchanged)
      MemoryPanel.tsx                (unchanged)
      Transcript.tsx                 (unchanged)
      VoiceActivation.tsx            (unchanged)
      state.ts                       (unchanged)
```

## The tradeoffs accepted

- A horizontal nav row degrades to horizontal scrolling rather than wrapping
  to multiple lines once every possible view is available (Overview, Runs,
  Approvals, Proposals, Memory, Registry, Voice) — chosen over wrapping to
  keep the top bar's height fixed regardless of how many views are active,
  matching vX2's own `overflow-x-auto` choice.
- Glass/blur is a GPU-compositing cost `backdrop-filter` always carries; at
  this window scale (a handful of translucent panels, not a scrolling feed of
  them) it's the same cost vX2 already accepts at a larger scale.
- Referencing vX2 for values without adopting its stack means hand-copying
  colour/blur/glow numbers into plain CSS rather than sharing a source of
  truth with that repo — accepted because AWF-GUI's no-new-dependency,
  no-Tailwind constraint predates this record and isn't renegotiated here.
- Dark only, still. A light theme doubles the token block for a surface with
  one operator, and ADR-0024's CLI already owns a `/theme` command this
  record doesn't extend to the GUI.

## Scope for implementation

1. Replace `.shell`/`.rail`/`.rail-nav`/`.rail-item` in
   `src/renderer/styles.css` with `.topbar`/`.nav-list`/`.nav-item`, per
   Mechanism above.
2. Add `backdrop-filter: blur(12px)` (+ `-webkit-` prefix) to `.card` and
   `.topbar`; add glow `box-shadow` rules to `.btn-primary` and
   `.nav-item[aria-current="page"]`.
3. Replace `App.tsx`'s `<aside className="rail">` markup with
   `<header className="topbar">`, keeping every prop, callback, and the
   `views`/`activeView` derivation byte-identical.
4. Re-check `main.ts`'s `BrowserWindow` `minWidth`/`minHeight` against the
   new layout's actual minimum (the rail's fixed 260px column is gone, so the
   practical minimum width shrinks) — adjust only if the built layout
   genuinely needs a different number.
5. Run the full existing GUI test suite unmodified and confirm all pass;
   run `npm --prefix frontend run build --workspaces` and
   `npm --prefix frontend test --workspaces`.

## Acceptance

- The window shows a sticky top bar with horizontal navigation buttons and
  status pills — no left rail, no three-column console.
- Exactly one view renders below the top bar at a time, switched by clicking
  a nav button, exactly as the rail revision already provided.
- `.card` and `.topbar` show visible blur/glass treatment; active nav items
  and primary buttons show a soft glow.
- No canvas, no particle animation, anywhere in the renderer.
- All 50 existing GUI tests pass with no change to any query, assertion, or
  accessible name.
- No new entry in `frontend/gui/package.json` `dependencies` or
  `devDependencies`.
- `npm --prefix frontend run build --workspaces` and
  `npm --prefix frontend test --workspaces` both pass.

## Consequences

- The desktop surface keeps ADR-0024's full data substance and the
  one-active-view model, corrected only in navigation orientation and visual
  polish.
- The palette and component substance built for the rail revision carry
  forward unchanged — this record's actual code delta is small (shell markup
  and CSS only).
- Future presentation changes to this shell should reference `../JARVISvX2/`
  the same way — values and layout shape, not its dependency stack.
