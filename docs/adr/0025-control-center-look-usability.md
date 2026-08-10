# ADR-0025: control-center look and usability

## Status

Proposed. Not implemented.

Scope is AWF-GUI only. The CLI and TUI reach their own ADR-0024 targets in a
separate record.

## Context

ADR-0024 delivered the control-center data path: `awf/control.summary`,
`awf/control.runDetail`, `awf/system.readiness`, and `awf/llm.*` reach the
renderer through narrow IPC, and the panels display real protocol data. Its
own acceptance criteria say the desktop must show "one coherent
control-center view." What shipped is a vertical stack of unstyled sections.

Current renderer state, read from the source:

- `src/renderer/index.html` contains a `<title>`, a `#root` div, and a module
  script. There is no stylesheet link and no CSS file anywhere under
  `frontend/gui/`.
- `esbuild.config.js` bundles `src/renderer/index.tsx` to
  `dist/renderer/index.js`; `package.json`'s `build` copies only `index.html`
  into `dist/renderer/`. No CSS entry point, no loader, no copy step.
- `App.tsx` returns a bare `<div>` wrapping `Dashboard`, `ProposalReview`,
  `MemoryPanel`, `RegistryActions`, `Transcript`, `VoiceActivation`, and
  `ApprovalConfirmation` in source order. Every panel that has its callbacks
  renders at once; there is no selection, no layout, and no visual hierarchy.
- `Dashboard.tsx` renders eight `<section>` elements — readiness, LLM status,
  registry, runs, selected run detail, approvals, improvements — each an `<h2>`
  followed by a `<ul>` or `<p>`. Approval previews render as raw
  `JSON.stringify(..., null, 2)` inside `<pre>`.
- `VoiceActivation.tsx` renders five buttons and three labelled inputs in a
  flat `<div role="group">`, including the operator typing the recognized text
  by hand.
- The rendered result is the browser default stylesheet: Times New Roman,
  white background, native bullets and buttons, no spacing system, no state
  colour.

Every panel carries `role` and `aria-label` attributes, and the 39 GUI tests
query by accessible role and label. The accessibility scaffolding is present
and correct; only presentation is missing.

The reference implementations establish the target. `JARVISvX2` styles a
dark control surface with a fixed token set: page background `#0a0a0b`, body
text `#e2e8f0`, cyan accent `#22d3ee`, emerald for healthy state, rose for
interrupt and error, Inter for prose and JetBrains Mono for identifiers, a
`glass` treatment of `rgba(255,255,255,0.03)` over a `rgba(255,255,255,0.08)`
border, and a 6px custom scrollbar. Its `Header` is a sticky bar holding
brand, a persona selector, seven view tabs, and three live status pills —
model mode, voice status, and hardware — so system state is visible from every
view. `JARVISvX` uses a two-column shell, `grid-template-columns: 270px
minmax(0,1fr)`, with a fixed navigation rail, a `radial-gradient` page
background, a `1100px` main column, and status rows built from an 8px
`online-dot`/`offline-dot` pair.

Both references are Tailwind or hand-authored CSS with no design-system
dependency. `frontend/gui/package.json` has no CSS tooling and no UI library.

## Decision

**One stylesheet, no framework.** `src/renderer/styles.css` holds the whole
visual system as CSS custom properties and plain selectors. No Tailwind, no
component library, no CSS-in-JS. The reference implementations achieve their
look with a token block and about 120 lines of rules; AWF needs less, because
it has fewer views.

**Tokens, not literals.** Colour, spacing, radius, and type are declared once
on `:root` and referenced everywhere. A component that needs a new colour adds
a token.

**A shell with a navigation rail and one active view.** `App.tsx` becomes a
two-column layout: a fixed rail listing the views, and a main column rendering
exactly one. The current all-panels-at-once stack becomes seven selectable
views over the same components.

**A persistent status bar.** Profile ID, per-function readiness, LLM state, and
pending-approval count stay visible in every view, because a control center
that hides its readiness cannot be trusted when it claims to be ready.

**Semantic state colour, applied consistently.** Ready, running, and succeeded
are one colour; waiting and degraded another; failed, denied, and blocked a
third. The same status token drives run status, readiness rows, approval risk
class, and LLM state.

**Identifiers are monospace.** Run IDs, step IDs, digests, refs, and profile
IDs are the values an operator compares character by character.

**Approvals are the visual priority.** A pending R2 or R3 approval is the one
thing that stops work, so it gets a distinct treatment and a rail badge rather
than a bullet in a list.

**Accessible names are preserved exactly.** Every existing `role` and
`aria-label` string stays, so all 39 GUI tests keep passing without
modification. This is a presentation change; no query in the test suite may
need to change.

**No new dependency.** `esbuild` already bundles the renderer and supports CSS
entry points natively.

## Deviation recorded

None. This record changes only `frontend/gui/src/renderer/` and the GUI build
step. No protocol method, IPC channel, backend operation, registry object, or
authorization path is touched.

## Mechanism

### Part A — build wiring

`src/renderer/index.tsx` gains `import "./styles.css";` at the top. esbuild
resolves the import and emits `dist/renderer/index.css` alongside
`index.js` — its default behaviour for a CSS import in a bundled entry point,
requiring no loader configuration.

`src/renderer/index.html` gains
`<link rel="stylesheet" href="./index.css" />` in `<head>`, and
`<meta name="viewport" content="width=device-width, initial-scale=1" />`.

`package.json`'s `build` script copies `index.html` only. It stays as written;
esbuild writes the CSS into `dist/renderer/` itself.

### Part B — the token block

`src/renderer/styles.css` opens with:

```css
:root {
  --bg:            #0a0a0b;
  --surface:       rgba(255, 255, 255, 0.03);
  --surface-raised:rgba(18, 18, 22, 0.7);
  --border:        rgba(255, 255, 255, 0.08);
  --border-strong: rgba(255, 255, 255, 0.16);

  --text:          #e2e8f0;
  --text-dim:      #94a3b8;
  --text-faint:    #64748b;

  --accent:        #22d3ee;
  --ok:            #34d399;
  --warn:          #fbbf24;
  --danger:        #fb7185;

  --font-sans: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  --font-mono: "JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, monospace;

  --space-1: 4px;  --space-2: 8px;  --space-3: 12px;
  --space-4: 16px; --space-5: 24px; --space-6: 32px;

  --radius:    8px;
  --radius-lg: 12px;
  --rail-width: 260px;
}
```

Fonts are referenced by family name only. Neither reference bundles a font
file, and both fall back through the same system stack. AWF adds no font
asset and no network font request.

### Part C — state colour

One class set, used by every status display:

| Class | Token | Applies to |
|---|---|---|
| `.state-ok` | `--ok` | `SUCCEEDED`, `ready`, `running`, `adopted`, `approved`, `trusted` |
| `.state-warn` | `--warn` | `WAITING_APPROVAL`, `WAITING_INPUT`, `pending`, `draft`, `degraded`, `quarantined` |
| `.state-danger` | `--danger` | `FAILED`, `CANCELED`, `not ready`, `denied`, `blocked`, `rejected`, `R3` |
| `.state-idle` | `--text-faint` | `idle`, `stopped`, `closed`, unknown |

A single exported helper, `stateClass(value: string): string`, maps a status
string to one of the four. Every component calls it rather than embedding its
own conditional.

Colour is never the only signal: each status also renders its own text, and a
readiness row keeps its `ready`/`not ready` word alongside the dot.

### Part D — the shell

`App.tsx` gains a `view` state over the seven views and renders:

```
┌──────────────┬──────────────────────────────────────┐
│  AWF         │  status bar: profile · readiness ·   │
│              │  llm · approvals badge               │
│  Overview  ● ├──────────────────────────────────────┤
│  Runs        │                                      │
│  Approvals 2 │  active view                         │
│  Proposals   │                                      │
│  Memory      │                                      │
│  Registry    │                                      │
│  Voice       │                                      │
│              │                                      │
│  ─────────   │                                      │
│  Refresh     │                                      │
└──────────────┴──────────────────────────────────────┘
```

Layout is `display: grid; grid-template-columns: var(--rail-width) minmax(0, 1fr);`
on a `min-height: 100vh` shell, matching the reference's proven shape. Below
900px the rail collapses to a horizontal tab strip through one media query.

View-to-component mapping, with every existing component retained:

| View | Renders |
|---|---|
| Overview | readiness, LLM status, registry counts, recent verdicts |
| Runs | run list and selected run detail |
| Approvals | approval queue plus `ApprovalConfirmation` |
| Proposals | `ProposalReview` and the improvement-proposal list |
| Memory | `MemoryPanel` |
| Registry | `RegistryActions` and registry counts |
| Voice | `VoiceActivation` and `Transcript` |

The rail shows a count badge on Approvals and Proposals when either is
non-empty. A view whose callbacks are absent is not listed, preserving the
current conditional-render behaviour.

`Dashboard.tsx` splits along the same lines into `Overview.tsx`, `RunsView.tsx`,
and `ApprovalsView.tsx`, each keeping the `aria-label` its sections carry
today. `Dashboard.tsx` remains as the composition the existing
`Dashboard.test.tsx` renders, so that file's queries continue to resolve.

### Part E — component treatment

**Cards.** Each `<section>` becomes a card: `background: var(--surface)`,
`border: 1px solid var(--border)`, `border-radius: var(--radius-lg)`,
`padding: var(--space-5)`. The `<h2>` becomes an uppercase eyebrow at
`font-size: 11px; letter-spacing: 0.12em; color: var(--text-dim)`.

**Lists.** `list-style: none`, rows separated by a `1px solid var(--border)`
top border rather than bullets.

**Readiness rows.** Function name in sans at full contrast, device as a
monospace chip, an 8px status dot, and the reason in `--text-dim` at 12px.
Five rows in one card.

**Run rows.** Workflow ref in sans, status as a coloured chip, run ID in
monospace `--text-faint`, and the details button aligned right.

**Approval cards.** Risk class as a chip coloured by `stateClass`, action
digest in monospace and selectable, and the machine-action preview in a
scrollable `<pre>` with `background: var(--surface-raised)`,
`max-height: 320px`, and `font-size: 12px`. Approve and Reject sit at the card
foot; Approve for R2 or R3 is not the default focus target.

**Buttons.** One primary style using `--accent` with dark text, one secondary
using `--surface` with `--border`, one danger using `--danger`. `:disabled`
drops opacity to 0.45 and sets `cursor: not-allowed`. A visible
`:focus-visible` outline in `--accent` is required — the reference
implementations omit this and keyboard operation suffers for it.

**Inputs.** `background: var(--surface-raised)`, `border: 1px solid
var(--border)`, focus border `--accent`, monospace where the value is a ref or
a path.

**Voice.** The five controls become one row with the state shown as a labelled
chip. The state colour follows `stateClass`, so `listening` reads warn and
`speaking` reads ok. The "Final recognized text" textarea keeps its label and
its behaviour; ADR-0023's push-to-talk path is unchanged by this record.

**Transcript.** Speaker in `--accent` monospace at 11px uppercase, body in
sans at 14px with `line-height: 1.55`, alternating rows offset by
`background: var(--surface)`.

**Scrollbars.** 6px, `--border` thumb, `--accent` on hover, matching the
reference.

**Empty states.** Each panel's existing "No runs yet." text stays, styled
`--text-faint`, italic, centred in the card.

### Part F — window chrome

`src/main/main.ts` already constructs its `BrowserWindow` with `width: 1000,
height: 700` and a `webPreferences` block. Two keys are added alongside those,
leaving the existing options and the `resolveBackendCommand`/`repoRoot` spawn
path untouched:

```ts
const win = new BrowserWindow({
  width: 1000,
  height: 700,
  minWidth: 960,
  minHeight: 640,
  backgroundColor: "#0a0a0b",
  webPreferences: { /* unchanged */ },
});
```

`backgroundColor` stops the shell flashing white before the renderer paints.
The minimums give the two-column layout room before the rail collapses to its
horizontal tab strip at 900px.

## Layout delta

```text
frontend/gui/
  package.json                       (unchanged)
  esbuild.config.js                  (unchanged)
  src/
    main/main.ts                     (backgroundColor and minimum size added to the existing BrowserWindow options)
    renderer/
      index.html                     (stylesheet link, viewport meta)
      index.tsx                      (import "./styles.css")
      styles.css                     (new: tokens and rules)
      state.ts                       (new: stateClass helper)
      App.tsx                        (shell, rail, status bar, view state)
      Overview.tsx                   (new: split from Dashboard)
      RunsView.tsx                   (new: split from Dashboard)
      ApprovalsView.tsx              (new: split from Dashboard)
      Dashboard.tsx                  (composition of the three above)
      ApprovalConfirmation.tsx       (class names only)
      ProposalReview.tsx             (class names only)
      MemoryPanel.tsx                (class names only)
      RegistryActions.tsx            (class names only)
      Transcript.tsx                 (class names only)
      VoiceActivation.tsx            (class names and control grouping)
```

## The tradeoffs accepted

- Hand-authored CSS means no utility classes and no design-system upgrades.
  It also means no build-step dependency, no purge configuration, and one file
  to read. Both reference implementations reached a finished look at this
  scale without a framework.
- One active view replaces the all-panels stack, so an operator watching runs
  no longer sees the memory panel at the same time. The status bar carries what
  must remain visible, and the rail badges carry what must remain noticed.
- Splitting `Dashboard.tsx` into three files touches a component with existing
  tests. Keeping `Dashboard.tsx` as their composition, with unchanged
  `aria-label` strings, is what allows those tests to pass untouched.
- Dark-only. A light theme doubles the token block for a surface with one
  operator, and ADR-0024's CLI already owns a `/theme` command that this record
  does not extend to the GUI.

## Scope for implementation

1. Add `src/renderer/styles.css` with the token block and base element rules.
2. Add `import "./styles.css"` to `index.tsx`; add the stylesheet link and
   viewport meta to `index.html`.
3. Add `src/renderer/state.ts` with `stateClass`.
4. Restructure `App.tsx` into shell, rail, status bar, and view switch.
5. Split `Dashboard.tsx` into `Overview.tsx`, `RunsView.tsx`, and
   `ApprovalsView.tsx`; keep `Dashboard.tsx` composing them with unchanged
   accessible names.
6. Apply card, list, chip, button, and input classes across the remaining
   components without altering their props, callbacks, or accessible names.
7. Add `minWidth`, `minHeight`, and `backgroundColor` to the existing
   `BrowserWindow` options in `main.ts`, leaving `width`, `height`,
   `webPreferences`, and the command/repo-root resolution unchanged.
8. Add `frontend/gui/tests/state.test.ts` covering all four `stateClass`
   branches, and a rail-navigation test asserting that selecting a view
   renders that view's region and not the others.
9. Run `npm --prefix frontend run build --workspaces` and
   `npm --prefix frontend test --workspaces`.

## Acceptance

- `dist/renderer/index.css` exists after a build and is referenced by
  `dist/renderer/index.html`.
- The window renders dark with the sans stack; no Times New Roman, no native
  bullets, no unstyled buttons.
- All 39 existing GUI tests pass with no change to any query or assertion.
- Every colour in `styles.css` outside the `:root` block is a `var(--…)`
  reference.
- Readiness, run status, approval risk class, and LLM state all derive their
  colour from `stateClass`, and each also renders its status as text.
- Selecting a rail item renders that view alone; the status bar remains
  visible in all seven.
- A pending approval raises a count badge on the rail's Approvals item.
- Every interactive element shows a visible focus ring on keyboard traversal,
  and the rail is reachable by Tab.
- Run IDs, step IDs, digests, and refs render in the monospace stack.
- No new entry in `frontend/gui/package.json` `dependencies` or
  `devDependencies`.
- `npm --prefix frontend run build --workspaces` and
  `npm --prefix frontend test --workspaces` both pass.

## Consequences

- The desktop surface matches ADR-0024's "one coherent control-center view"
  criterion, which the shipped panel stack did not.
- System readiness and pending approvals are visible from every view.
- One token block governs the whole surface, so a colour or spacing change is
  a single edit.
- The GUI gains no dependency and no build configuration.
- The CLI and TUI remain at their current level; their alignment to ADR-0024
  is recorded separately.
