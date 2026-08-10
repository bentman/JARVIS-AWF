# ADR-0025: control-center look and usability

## Status

Proposed. Not implemented. Supersedes the presentation decisions in the first
revision of this record.

Scope is AWF-GUI only. The CLI and TUI reach their own ADR-0024 targets in a
separate record.

This record is self-contained. Every colour, dimension, and rule needed to
implement it is written below. No external repository, prototype, or design
file needs to be consulted.

## Context

ADR-0024 delivered the control-center data path. `awf/control.summary`,
`awf/control.runDetail`, `awf/system.readiness`, and `awf/llm.*` reach the
renderer through narrow IPC, and the panels display real protocol data.

The shipped surface has these defects, observed in the running application:

- **Layout is a single scrolling column behind a navigation rail.** Selecting
  one view hides the others, so an operator watching a run cannot see the
  approval queue, and an operator in the voice view cannot see readiness. An
  operator console shows its state continuously; it does not page between
  states.
- **Raw JSON is rendered as the inventory display.** The Overview prints the
  entire `HardwareInventory` mapping as a `<pre>` block, occupying more
  vertical space than every other readiness element combined.
- **Preflight tokens render as one comma-separated paragraph** that wraps
  across three lines and cannot be scanned.
- **The voice controls are an inline run of labels and inputs.** "Final
  recognized text" wraps between "Final" and "recognized text", the three
  inputs sit at unaligned baselines, and the five buttons sit in one
  undifferentiated row.
- **Empty panels render as empty bordered boxes** with no text explaining what
  they will contain.
- **Density is a web page, not a console.** 16–32px padding around every card
  puts five readiness rows and nothing else on the first screen.

Current renderer state, read from the source:

- `src/renderer/index.html` links a stylesheet; `styles.css` exists.
- `App.tsx` implements a fixed rail plus one active view.
- `Dashboard.tsx` renders sections for readiness, LLM status, registry, runs,
  run detail, approvals, and improvements.
- Every panel carries `role` and `aria-label`; the 39 GUI tests query by
  accessible role and label.
- `frontend/gui/package.json` has no CSS tooling and no UI library.
- `esbuild.config.js` bundles `src/renderer/index.tsx`; a CSS import in that
  entry point emits `dist/renderer/index.css` with no loader configuration.

## Decision

**A three-column console, all state visible at once.** The navigation rail and
the one-view-at-a-time model are removed. Status sits left, conversation
centre, operator controls right — the arrangement an operator console uses,
and the arrangement that keeps readiness, transcript, and approvals on screen
together.

**A dense, dark, navy-based palette on a fixed token set.** Exact values are
given below and are not open to interpretation.

**Console density.** The spacing scale tops out at 9px. Panels are 7px padded.
Body text is 0.78–0.82rem. The shell is `height: 100vh` with
`overflow: hidden`; each column scrolls independently.

**State is carried by a left border and a badge, not by a dot.** A readiness
row, a run row, and an approval card each show a 4px coloured left edge and a
glyph, so state is legible without relying on colour alone.

**Structured data renders as fields, not as JSON.** The inventory becomes a
definition list of labelled rows. Tokens become a list.

**Every control is in a labelled form row.** Label above input, one input per
row, no inline label-input runs.

**Accessible names are preserved exactly.** Every existing `role` and
`aria-label` string stays byte-identical, so all 39 GUI tests pass without
modification.

**No new dependency.**

## Deviation recorded

None. This record changes only `frontend/gui/src/` and the GUI build step. No
protocol method, IPC channel, backend operation, registry object, or
authorization path is touched.

## Mechanism

### Part A — the token block

`src/renderer/styles.css` opens with exactly this. These values are the
specification; do not substitute a different palette.

```css
:root {
  color-scheme: dark;

  --font-ui: "Segoe UI", system-ui, sans-serif;
  --font-mono: Consolas, "Cascadia Mono", ui-monospace, monospace;

  --text-xs: 0.66rem;
  --text-sm: 0.74rem;
  --text-md: 0.82rem;
  --text-lg: 1.08rem;

  --space-1: 3px;
  --space-2: 5px;
  --space-3: 7px;
  --space-4: 9px;

  --radius-sm: 4px;
  --radius-md: 6px;
  --radius-lg: 10px;

  --color-bg-base:     #070b12;
  --color-bg-sunken:   #010409;
  --color-bg-panel:    #111827;
  --color-bg-elevated: #172033;
  --color-bg-soft:     #0d1422;

  --color-text-primary:   #e6edf3;
  --color-text-secondary: #b7c3d1;
  --color-text-muted:     #8b949e;
  --color-text-inverse:   #001018;

  --color-accent:       #00bfff;
  --color-ready:        #00ff99;
  --color-degraded:     #f6c177;
  --color-failed:       #ff6b6b;
  --color-capture:      #38bdf8;
  --color-speaking:     #7dd3fc;
  --color-thinking:     #a78bfa;
  --color-transcribing: #67e8f9;

  --color-border:        #30363d;
  --color-border-strong: #4b5563;

  --shadow-panel: 0 14px 30px #0000004d;
  --glow-capture: 0 0 0 1px #38bdf8, 0 0 22px #38bdf866;
}

body {
  margin: 0;
  min-height: 100vh;
  font-family: var(--font-ui);
  color: var(--color-text-primary);
  background: radial-gradient(circle at top left, var(--color-bg-soft), var(--color-bg-base));
}

button, input, select, textarea { font: inherit; }
```

The blue is `#00bfff`, not cyan. The ready green is `#00ff99`. Backgrounds are
navy-tinted, not neutral grey.

### Part B — the shell

```css
.shell {
  max-width: 1480px;
  margin: 0 auto;
  padding: var(--space-4);
  height: 100vh;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.header {
  display: grid;
  grid-template-columns: minmax(220px, 280px) minmax(320px, 1fr) minmax(260px, 340px);
  align-items: stretch;
  gap: var(--space-4);
  margin-bottom: var(--space-3);
}

.grid {
  display: grid;
  grid-template-columns: minmax(220px, 280px) minmax(320px, 1fr) minmax(260px, 340px);
  gap: var(--space-4);
  flex: 1;
  min-height: 0;
}

@media (max-width: 820px) {
  .grid, .header { grid-template-columns: 1fr; }
}
```

Column assignment:

| Column | Contents |
|---|---|
| Left — status | profile, readiness families, preflight tokens, LLM status, host inventory, registry counts |
| Centre — conversation | transcript log, text input, voice controls |
| Right — operator | approvals, proposals, runs and run detail, memory, registry actions |

`App.tsx` renders all three columns simultaneously. The `view` state, the rail,
and the rail badges are removed. Every component currently rendered
conditionally on its callbacks keeps that condition.

### Part C — the header

Three cells matching the body grid.

**Left:** `AWF` as `<h1>` at `var(--text-lg)`, profile ID beneath as
`.subtitle` in `--color-text-muted` at `var(--text-sm)`.

**Centre — the turn-status rail.** The voice pipeline as a single line of
monospace labels at `0.58rem`, separated by `·`, all at
`color: var(--color-text-muted); opacity: 0.4`:

```
LISTENING · TRANSCRIBING · REASONING · RESPONDING · SPEAKING
```

The label matching the current session state gets `.active`:
`opacity: 1; text-shadow: 0 0 8px currentColor` and a colour from the state
map in Part D. When no session is open, every label stays dimmed. The rail
sits in a `--color-bg-panel` card with a `.turn-status-title` eyebrow reading
`TURN`.

**Right — system state card.** LLM state, server id, and pending-approval
count, right-aligned, in a `--color-bg-panel` card. Pending approvals above
zero render in `--color-degraded`.

### Part D — state colour

One mapping, used by every status display. `src/renderer/state.ts` exports
`stateColorVar(value: string): string` returning the CSS variable name.

| State | Variable |
|---|---|
| `ready`, `SUCCEEDED`, `running`, `adopted`, `approved`, `trusted`, `IDLE` | `--color-ready` |
| `LISTENING` | `--color-capture` |
| `TRANSCRIBING` | `--color-transcribing` |
| `REASONING`, `ACTING`, `RESPONDING` | `--color-thinking` |
| `SPEAKING` | `--color-speaking` |
| `WAITING_APPROVAL`, `WAITING_INPUT`, `pending`, `draft`, `degraded`, `quarantined`, `INTERRUPTED`, `RECOVERING` | `--color-degraded` |
| `FAILED`, `CANCELED`, `not ready`, `denied`, `blocked`, `rejected`, `R3` | `--color-failed` |
| anything else | `--color-text-muted` |

Components set `data-state="<value>"` and the stylesheet selects on it, as in
Part E. Colour is never the only signal: every element also renders its state
as text, and readiness and approval rows carry a glyph.

### Part E — panels and rows

```css
.panel {
  background: var(--color-bg-panel);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: var(--space-3);
  box-shadow: var(--shadow-panel);
  min-height: 0;
  overflow-y: auto;
}

.panel-section {
  border-bottom: 1px solid var(--color-border);
  padding-bottom: var(--space-2);
  margin-bottom: var(--space-2);
}
.panel-section:last-child { border-bottom: 0; margin-bottom: 0; padding-bottom: 0; }

.label, dt {
  display: block;
  font-size: var(--text-xs);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--color-text-muted);
}
```

**Readiness rows.** A `.readiness-family` per function, with a state-coloured
left edge and a glyph badge:

```css
.readiness-family {
  position: relative;
  border: 1px solid var(--color-border);
  border-left: 4px solid var(--color-border);
  border-radius: var(--radius-sm);
  padding: var(--space-2) var(--space-2) var(--space-2) 28px;
  margin-bottom: var(--space-2);
  background: var(--color-bg-elevated);
}
.readiness-family::before {
  position: absolute;
  left: var(--space-2);
  top: var(--space-2);
  width: 16px; height: 16px;
  border-radius: var(--radius-sm);
  display: grid; place-items: center;
  font-size: var(--text-xs);
  font-weight: 800;
}
.readiness-family[data-readiness-state="ready"] { border-left-color: var(--color-ready); }
.readiness-family[data-readiness-state="ready"]::before {
  content: "✓"; color: var(--color-text-inverse); background: var(--color-ready);
}
.readiness-family[data-readiness-state="degraded"] { border-left-color: var(--color-degraded); }
.readiness-family[data-readiness-state="degraded"]::before {
  content: "!"; color: var(--color-text-inverse); background: var(--color-degraded);
}
.readiness-family[data-readiness-state="failed"] { border-left-color: var(--color-failed); }
.readiness-family[data-readiness-state="failed"]::before {
  content: "×"; color: var(--color-text-primary); background: var(--color-failed);
}
```

Row content: function name in `--color-text-primary`, device as a monospace
chip, then the reason on its own line in `--color-text-muted` at
`var(--text-sm)`.

**Field lists replace JSON.** The host inventory renders as:

```css
.facts {
  display: grid;
  grid-template-columns: minmax(62px, max-content) 1fr;
  gap: var(--space-1) var(--space-2);
  margin: 0;
}
dd { margin: 0; word-break: break-word; font-size: 0.78rem; line-height: 1.22;
     color: var(--color-text-secondary); }
```

Displayed fields, in this order, with `null` and empty values omitted:
`gpu_name`, `gpu_vram_gb`, `cuda_version`, `cpu_name`, `cpu_logical_cores`,
`memory_total_gb`, `memory_available_gb`, `os_name`, `os_version`, `arch`.
The remaining inventory keys move behind a `<details>` element labelled
`Full inventory`, collapsed by default, rendering the same field list. No
`JSON.stringify` output appears in any panel.

**Tokens.** One `<li>` per token, monospace at `var(--text-xs)`, no bullets.
A token ending in `:MISSING` renders in `--color-degraded`.

**State chips.**

```css
.state-chip {
  display: inline-block;
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  padding: var(--space-1) var(--space-2);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-bg-sunken);
  color: var(--color-accent);
}
```

with `[data-state="…"]` rules setting `color` and `border-color` from the
Part D map.

### Part F — conversation column

```css
.conversation-panel {
  min-height: 0;
  display: flex;
  flex-direction: column;
  padding: var(--space-4);
}
.conversation-log {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-bg-sunken);
  padding: var(--space-3);
  font-family: var(--font-mono);
  font-size: 0.82rem;
}
.message {
  border: 1px solid var(--color-border);
  border-left: 4px solid var(--color-border);
  border-radius: var(--radius-sm);
  padding: var(--space-2);
  margin-bottom: var(--space-2);
  background: var(--color-bg-soft);
}
.message strong { text-transform: uppercase; color: var(--color-accent); }
.message.user { border-left-color: var(--color-ready); }
.message.user strong { color: var(--color-ready); }
.message.assistant { border-left-color: var(--color-accent); background: var(--color-bg-elevated); }
.message.system { border-left-color: var(--color-text-muted); }
.message.system strong { color: var(--color-text-muted); }
.message p { margin: var(--space-1) 0 0; white-space: pre-wrap; color: var(--color-text-primary); }
```

Below the log, a `.text-form` at `grid-template-columns: 1fr auto` — one input
and one submit button — then `.voice-controls` as a wrapping flex row.

### Part G — form rows and controls

Every label-input pair becomes a stacked row. No label sits inline with its
input.

```css
.field { display: grid; gap: var(--space-1); }
.field > span {
  font-size: var(--text-xs);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--color-text-muted);
}
input, select, textarea {
  width: 100%;
  box-sizing: border-box;
  min-width: 0;
  padding: var(--space-2);
  color: var(--color-text-primary);
  background: var(--color-bg-sunken);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
}
input:focus-visible, select:focus-visible, textarea:focus-visible, button:focus-visible {
  outline: 2px solid var(--color-accent);
  outline-offset: 1px;
}
textarea { min-height: 4.5rem; resize: vertical; }

button {
  color: var(--color-text-inverse);
  background: var(--color-accent);
  border: 1px solid var(--color-accent);
  border-radius: var(--radius-sm);
  padding: var(--space-2) var(--space-4);
  font-weight: 700;
  font-size: 0.82rem;
  cursor: pointer;
}
button.secondary {
  color: var(--color-text-primary);
  background: var(--color-bg-elevated);
  border-color: var(--color-border-strong);
}
button.danger {
  color: var(--color-text-inverse);
  background: var(--color-failed);
  border-color: var(--color-failed);
}
button:disabled, input:disabled, select:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}
```

The voice view's three inputs — default workflow, voice profile, final
recognized text — each become a `.field`, stacked, full width of the centre
column. The textarea is last and spans the row.

Button grouping: **Start voice session** primary; **Push to talk** primary;
**Stop talking** and **Submit voice text** secondary; **Interrupt** danger.

**Push-to-talk feedback.** The button carries
`data-capture-state="idle | recording | processing"`:

```css
#ptt-button[data-capture-state="recording"] {
  background: var(--color-capture);
  border-color: var(--color-capture);
  box-shadow: var(--glow-capture);
  animation: capture-pulse 1.2s ease-in-out infinite;
}
#ptt-button[data-capture-state="processing"] {
  color: var(--color-text-secondary);
  background: var(--color-bg-elevated);
  border-color: var(--color-border-strong);
}
@keyframes capture-pulse {
  0%, 100% { transform: scale(1); }
  50%      { transform: scale(1.03); }
}
@media (prefers-reduced-motion: reduce) {
  #ptt-button[data-capture-state="recording"] { animation: none; }
}
```

### Part H — approvals

An approval renders as a `.panel-section` with a state-coloured left edge by
risk class, the action digest in monospace and selectable, and the machine
action as a field list — not as `JSON.stringify` output — with a
`<details>` holding the full payload. Approve and Reject sit at the foot;
Reject is `button.secondary`, Approve is `button.danger` for R2 and R3 so the
irreversible action is not styled as the safe default, and neither is
autofocused.

### Part I — empty states

Every panel that can be empty renders its existing text — "No runs yet." and
the equivalents — styled `color: var(--color-text-muted); font-style: italic;
font-size: var(--text-sm)`. No panel renders as a bordered box with nothing in
it.

### Part J — window chrome

`src/main/main.ts` already constructs its `BrowserWindow` with `width: 1000,
height: 700` and a `webPreferences` block. Three keys are added alongside
those, leaving the existing options and the
`resolveBackendCommand`/`repoRoot` spawn path untouched:

```ts
const win = new BrowserWindow({
  width: 1000,
  height: 700,
  minWidth: 1100,
  minHeight: 680,
  backgroundColor: "#070b12",
  webPreferences: { /* unchanged */ },
});
```

`minWidth: 1100` keeps the three columns above their combined minimum of
220 + 320 + 260 plus gaps before the 820px single-column fallback applies.

## Layout delta

```text
frontend/gui/
  package.json                       (unchanged)
  esbuild.config.js                  (unchanged)
  src/
    main/main.ts                     (backgroundColor and minimums added to existing options)
    renderer/
      index.html                     (unchanged)
      index.tsx                      (unchanged)
      styles.css                     (rewritten to Parts A-I)
      state.ts                       (stateColorVar map from Part D)
      App.tsx                        (three-column shell and header; rail removed)
      StatusColumn.tsx               (new: readiness, tokens, inventory, LLM, registry)
      ConversationColumn.tsx         (new: transcript log, text form, voice controls)
      OperatorColumn.tsx             (new: approvals, proposals, runs, memory, registry actions)
      Dashboard.tsx                  (composition of the three columns)
      ApprovalConfirmation.tsx       (field list, button classes)
      ProposalReview.tsx             (field rows, button classes)
      MemoryPanel.tsx                (field rows, button classes)
      RegistryActions.tsx            (field rows, button classes)
      Transcript.tsx                 (message rows)
      VoiceActivation.tsx            (stacked fields, button classes, capture state)
```

## The tradeoffs accepted

- Three columns at this density need 1100px. Below 820px the layout stacks to
  one column and becomes a scrolling list, which is the fallback rather than
  the target.
- Showing every panel at once means more on screen than any single task needs.
  That is the point of a console: the operator sees readiness and pending
  approvals without navigating to them.
- Hand-authored CSS means no utility classes and no design-system upgrades. It
  also means no build dependency, no purge step, and one file to read.
- Dark only. A light theme doubles the token block for a surface with one
  operator.
- Splitting `Dashboard.tsx` into three column files touches a component with
  existing tests. Keeping `Dashboard.tsx` as their composition, with unchanged
  `aria-label` strings, is what allows those tests to pass untouched.

## Scope for implementation

1. Rewrite `src/renderer/styles.css` to Parts A–I exactly.
2. Rewrite `src/renderer/state.ts` to the Part D map.
3. Rewrite `App.tsx` as the three-column shell with the Part C header; remove
   the rail, the `view` state, and the rail badges.
4. Split `Dashboard.tsx` into `StatusColumn.tsx`, `ConversationColumn.tsx`,
   and `OperatorColumn.tsx`; keep `Dashboard.tsx` composing them with
   unchanged accessible names.
5. Replace every `JSON.stringify` display with a field list plus a collapsed
   `<details>`.
6. Convert every label-input pair to a stacked `.field`.
7. Apply panel, readiness-family, message, chip, and button classes across the
   remaining components without altering props, callbacks, or accessible
   names.
8. Add `data-capture-state` to the push-to-talk button.
9. Add `minWidth`, `minHeight`, and `backgroundColor` to the existing
   `BrowserWindow` options in `main.ts`, leaving `width`, `height`,
   `webPreferences`, and the command/repo-root resolution unchanged.
10. Add `frontend/gui/tests/state.test.ts` covering every row of the Part D
    map including the fallback.
11. Run `npm --prefix frontend run build --workspaces` and
    `npm --prefix frontend test --workspaces`.

## Acceptance

- The window shows three columns simultaneously; there is no navigation rail
  and no view selection.
- Readiness, transcript, and approvals are all visible without interaction at
  1100×680.
- No panel renders `JSON.stringify` output; the host inventory renders as
  labelled fields with the remainder behind a collapsed `Full inventory`
  disclosure.
- Preflight tokens render one per line, with `:MISSING` entries in the
  degraded colour.
- Every readiness row shows a coloured left edge, a `✓`/`!`/`×` badge, and its
  state as text.
- Every label sits above its input; no label wraps mid-phrase.
- The push-to-talk button changes colour and pulses while recording, and does
  not animate under `prefers-reduced-motion: reduce`.
- Every colour in `styles.css` outside the `:root` block is a `var(--…)`
  reference.
- Every interactive element shows a visible `--color-accent` focus ring on
  keyboard traversal.
- All 39 existing GUI tests pass with no change to any query or assertion.
- No new entry in `frontend/gui/package.json` `dependencies` or
  `devDependencies`.
- `npm --prefix frontend run build --workspaces` and
  `npm --prefix frontend test --workspaces` both pass.

## Consequences

- The desktop surface is an operator console: state left, conversation centre,
  controls right, all visible together.
- Readiness and pending approvals cannot be hidden by navigation.
- Structured backend data is displayed as fields, and raw payloads are
  available on demand rather than by default.
- One token block governs the whole surface, so a colour or spacing change is
  a single edit.
- The GUI gains no dependency and no build configuration.
