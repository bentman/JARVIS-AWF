# ADR-0025: control-center look and usability

## Status

Implemented. Navigation superseded in part by ADR-0029, which reduces the view
set to Operate, Chat, and Library; the visual system in this record still
governs.

This record began as an AWF-GUI look-and-feel record and still treats
`frontend/gui/src/renderer/` as the source of truth for visual layout. Later
operator-usability work extended the same decision boundary into the shared
assistant path: backend response text, default workflow selection, and the
AWF-CLI plain-text assistant entry point. Where this record and the referenced
source files disagree, the code is correct.

Alignment update, 2026-08-30: ADR-0028 supersedes this record's earlier
"conversation first" navigation rule. The GUI now opens to Operate, a task-flow
control-center home view backed by `awf/control.summary`. Chat remains a normal
navigation entry and still uses the same transcript/composer behavior after the
operator chooses it.

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
area. ADR-0028 later moved the default page from Chat to Operate.

Constraints that held throughout: every panel carries `role` and `aria-label`,
the GUI tests query by accessible role and label, `frontend/gui/package.json`
has no CSS tooling and no UI library, and `esbuild` bundles
`src/renderer/index.tsx` so a CSS import in that entry point emits
`dist/renderer/index.css` with no loader configuration.

## Decision

**A top bar over one content area.** Brand, view navigation, live status, and
Refresh sit in a sticky `.topbar`. Below it, `.main` renders exactly one view.
There is no left rail and no multi-column console.

**Operate is the first page.** The `operate` view is the default home when
control-summary data is available. The `chat` view is always present as an
entry point for starting work. Status and diagnostics are shown inside Operate
and run detail instead of as the primary page.

**A navy palette on named tokens.** Canonical colours are declared once as
`--color-*` and the working shorthands derive from them, so every selector
reads a variable and a palette change is one edit.

**Four semantic state classes.** `state-ok`, `state-warn`, `state-danger`,
`state-idle`, produced by one exported function and applied to dots and chips.

**Chat renders as a messenger window.** Title bar, auto-scrolling bubble
stream with letter avatars, operator right and agent left, and a composer with
a mic button, workflow selector, message input, and a Send button. Typed chat
shows the useful core response in the transcript: `outputs.response_text`
first, then failure `reason`/`error`, with the Run id retained for traceability.
The backend accepts normal assistant input as `{ objective: "..." }` and maps it
onto strict single-string workflow schemas when needed, while preserving only
metadata fields that the workflow schema allows.

**The CLI also accepts plain assistant input.** A non-slash line starts the same
default workflow with `{ objective: text }` and prints the assistant-facing
response text plus the Run id. If `settings.defaultWorkflow` is configured, the
plain assistant path uses that workflow; otherwise it falls back to
`assistant-default@1.0.0`, a local deterministic workflow that requires no
external agent CLI. Slash commands remain available for explicit operator
actions.

**Inline SVG icons, no icon package.** One `makeIcon` factory over 24×24
stroke paths.

**No new dependency.**

## Deviation recorded

The renderer-only scope was intentionally widened for first-run usability. The
default assistant path now relies on a repo-tracked `assistant-default@1.0.0`
Workflow and `assistant_reply@1.0.0` Capability Record, plus backend support for
operator-visible `outputs.response_text`. No new protocol authority is added:
GUI, CLI, and JSON-RPC still call the existing Run-start path.

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
`operate | chat | runs | approvals | proposals | memory | registry`. `operate`
is first when control-summary callbacks are present; `chat` remains
unconditional. Every other view is included only when its callbacks are present.
`activeView` falls back to the first available view.

| View | Renders |
|---|---|
| Operate | `OperatorWorkQueue`, selected `RunTimeline`/`EvidencePanel`, and `Overview` |
| Chat | `Transcript` and, when voice callbacks exist, `VoiceActivation` |
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
monospace `.workflow-input` labelled `Workflow`, a `.composer-input` labelled
`Message`, and a `.btn-send` labelled `Send`, disabled until the draft is
non-empty. The workflow field defaults to `assistant-default@1.0.0` because
that shipped workflow accepts the chat payload's `objective` field and returns
operator-visible response text without requiring external agent CLIs; the
operator may still override it. When registry listing is available, known
workflow refs are offered as datalist suggestions rather than forcing exact
free-typed recall. If no workflow is supplied, typed chat keeps the draft and
reports a visible error. Successful typed submissions append the operator text
and the core response text to the same log; failed Runs append the returned
failure reason or error with the Run id. The core supplies a fallback
`outputs.response_text` for workflows that do not declare one, so the chat page
is not dependent on every workflow author remembering a GUI-specific output
field. The backend also adapts a chat `objective` to a workflow's single
required string input field, so shipped `topic` workflows can run from the same
chat composer.

`VoiceActivation` renders `.voice-bar` beneath the composer: a first
`.voice-row` with the session-state chip, the session id, and the five session
buttons; a second `.voice-row` with the workflow, voice-profile, and
recognized-text controls at fixed widths, plus the partial transcript and any
error. Its workflow field starts from the same chat workflow default and uses
the same registry-backed suggestions.

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
  OperatorWorkQueue.tsx   (backend-derived operating queue)
  RunTimeline.tsx         (run detail timeline)
  EvidencePanel.tsx       (artifact/evidence links and readouts)
  RegistryObjectSummary.tsx
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
- Operate is the landing page when control-summary callbacks are supplied; Chat
  remains present regardless of callbacks.
- Every colour outside the `:root` block is a `var(--…)` reference.
- Readiness dots, run status, approval risk class, and LLM state all derive
  their class from `stateClass`, and each also renders its state as text.
- The active navigation item carries `aria-current="page"`.
- A pending approval raises a `.rail-badge` count on the nav item that carries
  the approval queue (ADR-0029 moved that from Approvals to Operate).
- Every interactive element shows a visible accent focus ring on keyboard
  traversal.
- The chat log scrolls to its newest entry when entries change.
- Typed chat requires a workflow, starts a durable Run, and renders the core
  response or failure text in the shared transcript with the Run id.
- Workflow inputs offer registry-backed workflow refs when available, and
  voice starts with the same default workflow as typed chat.
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
- The CLI plain-text path now starts the same default assistant workflow as the
  GUI chat surface unless operator settings choose a different workflow.
