# ADR-0025: control-center look and usability

## Status

Implemented.

Scope is AWF-GUI only. The CLI and TUI reach their own ADR-0024 targets in a
separate record.

This record documents the shipped renderer. It is written against
`frontend/gui/src/renderer/`, which is the source of truth for the look and
feel; where this record and that directory disagree, the code is correct.

## Context

ADR-0024 delivered the control-center data path. `awf/control.summary`,
`awf/control.runDetail`, `awf/system.readiness`, and `awf/llm.*` reach the
renderer through narrow IPC, and the panels display real protocol data.

What that left was presentation. Before this record there was no stylesheet
anywhere under `frontend/gui/`, no stylesheet link in `index.html`, and no CSS
step in the build, so the surface rendered in the browser default stylesheet:
Times New Roman, white background, native bullets and buttons. `App.tsx`
rendered every panel in one scrolling column.

Two later revisions of this record proposed layouts — a left navigation rail
with one active view, then a three-column console — that the implementation
did not adopt. What shipped is a top navigation bar over a single content
area, with conversation as the first page.

Constraints that held throughout: every panel carries `role` and `aria-label`,
the GUI tests query by accessible role and label, `frontend/gui/package.json`
has no CSS tooling and no UI library, and `esbuild` bundles
`src/renderer/index.tsx` so a CSS import in that entry point emits
`dist/renderer/index.css` with no loader configuration.

## Decision

**A top bar over one content area.** Brand, view navigation, live status, and
Refresh sit in a sticky `.topbar`. Below it, `.main` renders exactly one view.
There is no left rail and no multi-column console.

**Conversation is the first page.** The `chat` view is always present and
always first. Status and diagnostics live behind their own navigation button.

**A navy palette on named tokens.** Canonical colours are declared once as
`--color-*` and the working shorthands derive from them, so every selector
reads a variable and a palette change is one edit.

**Four semantic state classes.** `state-ok`, `state-warn`, `state-danger`,
`state-idle`, produced by one exported function and applied to dots and chips.

**Chat renders as a messenger window.** Title bar, auto-scrolling bubble
stream with letter avatars, operator right and agent left, and a composer with
a mic button and a Send button.

**Inline SVG icons, no icon package.** One `makeIcon` factory over 24×24
stroke paths.

**No new dependency.**

## Deviation recorded

None. This record changes only `frontend/gui/src/` and the GUI build step. No
protocol method, IPC channel, backend operation, registry object, or
authorization path is touched.

## Mechanism

### Part A — tokens

`src/renderer/styles.css` opens with the canonical palette and derived
shorthands:

```css
:root {
  --color-bg-base:   #070b12;  /* deep navy base */
  --color-panel:     #111827;  /* card / panel surface */
  --color-elevated:  #172033;  /* inputs, code, raised blocks */
  --color-accent:    #00bfff;  /* deep sky blue */
  --color-ready:     #00ff99;  /* ready / ok green */
  --color-not-ready: #e0115f;  /* ruby red for not-ready / danger */
  --color-warn:      #fbbf24;  /* amber */

  --bg:             var(--color-bg-base);
  --surface:        rgba(17, 24, 39, 0.7);
  --surface-raised: rgba(23, 32, 51, 0.7);
  --border:         rgba(255, 255, 255, 0.08);
  --border-strong:  rgba(255, 255, 255, 0.16);

  --text:       #e2e8f0;
  --text-dim:   #94a3b8;
  --text-faint: #64748b;

  --accent: var(--color-accent);
  --ok:     var(--color-ready);
  --warn:   var(--color-warn);
  --danger: var(--color-not-ready);

  --font-sans: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  --font-mono: "JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, monospace;

  --space-1: 4px;  --space-2: 8px;  --space-3: 12px;
  --space-4: 16px; --space-5: 24px; --space-6: 32px;

  --radius: 8px;  --radius-lg: 12px;
}
```

The page background is layered: a 56px grid from two 1px linear gradients at
`rgba(30,41,59,0.14)`, an accent radial glow at 78%/−12%, a ready-green radial
glow at −12%/112%, over `--bg`.

### Part B — shell and top bar

```css
.shell { display: flex; flex-direction: column; height: 100vh; }
.main  { display: flex; flex-direction: column; padding: var(--space-5);
         overflow-y: auto; flex: 1; min-height: 0; }
.main:has(.chat-page) { padding: 0; }
```

`.topbar` is `position: sticky; top: 0; z-index: 10`, a wrapping flex row over
`rgba(17,24,39,0.6)` with a bottom border and a soft drop shadow. It holds, in
order: `.brand`, the `Views` nav, `.status-bar` pushed right with
`margin-left: auto`, and the Refresh button.

The top bar uses a flat translucent background rather than `backdrop-filter`.
Software compositors under WSLg mis-render blurred surfaces and their
children, so the blur is omitted deliberately.

`.brand` is a 40px `.brand-badge` — monospace `A`, accent on
`rgba(0,191,255,0.12)` with a ring and an 18px glow — beside a two-line
`.brand-text`: `AWF` in monospace with a `System active` pill, and
`Agentic Workflow Fabric` as a 10px uppercase `.brand-tag`.

Navigation is a horizontal `.nav-list` of `.nav-item` buttons. The active item
carries `aria-current="page"` and renders `rgba(0,191,255,0.15)` with accent
text and an accent ring. A view with a pending count renders a `.rail-badge`
pill in `--danger`.

`.status-bar` shows the profile ID in monospace, then three chips: overall
readiness, LLM state, and the pending-approval count.

### Part C — state classes

`src/renderer/state.ts` exports `stateClass(value: string): string` over three
sets:

| Class | Members |
|---|---|
| `state-ok` | `SUCCEEDED`, `ready`, `running`, `adopted`, `approved`, `trusted` |
| `state-warn` | `WAITING_APPROVAL`, `WAITING_INPUT`, `pending`, `draft`, `degraded`, `quarantined` |
| `state-danger` | `FAILED`, `CANCELED`, `not ready`, `denied`, `blocked`, `rejected`, `R3` |
| `state-idle` | anything else |

`.dot` and `.chip` each carry a rule per class. A chip sets colour, a matching
50%-alpha ring, and a 10%-alpha fill.

`VoiceActivation` keeps a local `voiceStateClass` over its own session
vocabulary: `speaking` is ok; `listening`, `transcribing`, `submitting`, and
`recovering` are warn; everything else idle.

### Part D — views

`App.tsx` holds `view` state over
`chat | status | runs | approvals | proposals | memory | registry`. `chat` is
unconditional and first; every other view is included only when its callbacks
are present. `activeView` falls back to the first available view.

| View | Renders |
|---|---|
| Chat | `Transcript` and, when voice callbacks exist, `VoiceActivation` |
| Status | a `.view-header` with kicker `Resident Mind` and title `Control center`, then `Overview` |
| Runs | `RunsView` |
| Approvals | `ApprovalsView` |
| Proposals | `ProposalReview` and `ImprovementProposals` |
| Memory | `MemoryPanel` |
| Registry | `RegistryActions` |

`ApprovalConfirmation` renders outside `.main`, so a pending approval is
present in every view.

### Part E — cards, stats, lists

`.card` is `--surface-raised` at 16px radius with a 24px pad and a 24px bottom
margin; hover lifts the border to `rgba(0,191,255,0.22)`. A card's `<h2>` is a
monospace 11px uppercase eyebrow at `0.12em` tracking with a bottom rule.

`.view-header` is a flex row with a monospace accent `.view-kicker` above a
26px `.view-title` at weight 300, over a bottom rule.

`.stat-grid` is `repeat(auto-fill, minmax(190px, 1fr))`. A `.stat-card` holds a
`.stat-label` (10px uppercase monospace, with a state dot), a `.stat-value`
(22px monospace), and a `.stat-sub` (12px faint). Readiness renders one stat
card per function: dot from `result.ready`, device as the value, and
`ready`/`not ready` plus the reason as the sub-line.

`.list` is a gapped flex column of `--surface` rows with a hairline ring.

`.pre-scroll` caps a scrollable block at 320px with an inset shadow, used for
approval previews, artifact content, and the readiness inventory.

### Part F — chat page

```css
.chat-page  { flex: 1; min-height: 0; display: flex; }
.chat-frame { width: 100%; max-width: 1152px; margin: 0 auto;
              display: flex; flex-direction: column; min-height: 0;
              background: rgba(10, 14, 22, 0.55);
              box-shadow: -1px 0 0 var(--border), 1px 0 0 var(--border); }
```

`Transcript` renders `.chat-window`: a `.chat-title` bar with a glowing green
`.chat-dot`, a `.chat-scroll` log that follows its newest entry through a
`useEffect` on `entries`, and a `.composer` form.

A message is a `.bubble` at `max-width: 82%`. Speaker matching `/^operator/i`
gets `.bubble-user` — `align-self: flex-end`, `flex-direction: row-reverse`,
ready-green avatar and tint. Everything else gets `.bubble-agent` — accent
avatar and `--surface-raised` body. Each bubble carries a 28px `.avatar` (`U`
or `A`), a 10px uppercase `.bubble-speaker`, and 14px `.bubble-text` at 1.5
line height.

The composer is a flex row: a 36px `.btn-mic` labelled `Push to talk`, a
`.composer-input` labelled `Message`, and a `.btn-send` labelled `Send`,
disabled until the draft is non-empty.

`VoiceActivation` renders `.voice-bar` beneath the composer: a first
`.voice-row` with the session-state chip, the session id, and the five session
buttons; a second `.voice-row` with the workflow, voice-profile, and
recognized-text controls at fixed widths, plus the partial transcript and any
error.

### Part G — buttons and inputs

`.btn` is 8px radius at 13px sans. `.btn-primary` is accent on `#04121a` with
a 20px glow that brightens on hover. `.btn-secondary` is `--surface-raised`
with a hairline ring that turns accent-tinted on hover. `.btn-danger` is
`--danger` on `#250509`. Disabled drops to 0.45 opacity with
`cursor: not-allowed`.

Inputs are borderless over `--surface-raised` with a `box-shadow` ring that
becomes accent on focus. `.mono` switches an input or textarea to the
monospace stack.

Focus is a 2px accent outline at 2px offset on buttons, links, inputs,
textareas, and anything with `tabindex`.

Scrollbars are 6px with a `--border` thumb that turns accent on hover, plus
`scrollbar-width: thin` for non-WebKit.

### Part H — icons

`src/renderer/icons.tsx` exports a `makeIcon` factory producing 24×24
`currentColor` stroke icons at `strokeWidth={2}`, all `aria-hidden`:
`SparkleIcon`, `ChatIcon`, `PlayIcon`, `ShieldIcon`, `ZapIcon`, `ArchiveIcon`,
`DatabaseIcon`, `RefreshIcon`, `MicIcon`, `SendIcon`, `CpuIcon`,
`TerminalIcon`, `CheckIcon`. Navigation items render theirs at 13px; the view
kicker at 12px.

### Part I — empty states

`.empty` is faint, italic, centred. Every panel that can be empty renders one:
`No readiness data.`, `No LLM status.`, `No registry counts.`,
`No recent verdicts.`, and the chat page's
`No conversation yet — type a message or use voice to start.`

## Layout delta

```text
frontend/gui/src/renderer/
  styles.css              (the whole visual system)
  state.ts                (stateClass)
  icons.tsx               (makeIcon and the icon set)
  App.tsx                 (shell, top bar, nav, status bar, view switch)
  Overview.tsx            (readiness stat grid, LLM status, registry, verdicts)
  RunsView.tsx
  ApprovalsView.tsx
  Dashboard.tsx           (shared types and ImprovementProposals)
  Transcript.tsx          (chat window, bubbles, composer)
  VoiceActivation.tsx     (voice bar)
  ApprovalConfirmation.tsx
  ProposalReview.tsx
  MemoryPanel.tsx
  RegistryActions.tsx
```

## The tradeoffs accepted

- One view at a time. Readiness is not visible while reading the chat page;
  the top bar's status chips carry overall readiness, LLM state, and the
  pending-approval count into every view, and `ApprovalConfirmation` renders
  outside the view switch.
- Hand-authored CSS with no utility classes and no design-system upgrades, in
  exchange for no build dependency, no purge step, and one file to read.
- Dark only. A light theme doubles the token block for a surface with one
  operator.
- No `backdrop-filter` on the top bar, because software compositors under
  WSLg mis-render blurred surfaces and their children.
- The readiness inventory still renders as a `.pre-scroll` JSON block rather
  than a field list. It is bounded at 320px and scrolls, so it no longer
  dominates the view.

## Acceptance

- `dist/renderer/index.css` exists after a build and is linked from
  `dist/renderer/index.html`.
- The window renders dark navy with the sans stack; no default serif, no
  native bullets, no unstyled buttons.
- The chat view is the landing page and is present regardless of which
  callbacks are supplied.
- Every colour outside the `:root` block is a `var(--…)` reference.
- Readiness dots, run status, approval risk class, and LLM state all derive
  their class from `stateClass`, and each also renders its state as text.
- The active navigation item carries `aria-current="page"`.
- A pending approval raises a `.rail-badge` count on the Approvals nav item.
- Every interactive element shows a visible accent focus ring on keyboard
  traversal.
- The chat log scrolls to its newest entry when entries change.
- No new entry in `frontend/gui/package.json` `dependencies` or
  `devDependencies`.
- `npm --prefix frontend run build --workspaces` and
  `npm --prefix frontend test --workspaces` both pass.

## Consequences

- The desktop surface leads with conversation and keeps system state one
  click away, with the top bar carrying readiness, LLM state, and pending
  approvals continuously.
- One token block governs the whole surface, so a colour or spacing change is
  a single edit.
- The GUI gains no dependency and no build configuration.
- The CLI and TUI remain at their current level; their alignment to ADR-0024
  is recorded separately.
