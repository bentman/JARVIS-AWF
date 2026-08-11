# ADR-0025: control-center look and usability (chat-forward, navy)

## Status

Implemented. Scope is AWF-GUI only; the CLI and TUI reach their own ADR-0024
targets in a separate record.

## Context

ADR-0024 delivered the control-center data path: `awf/control.summary`,
`awf/control.runDetail`, `awf/system.readiness`, and `awf/llm.*` reach the
renderer through narrow IPC, and the panels display real protocol data —
readiness rows, LLM state and model catalog, hardware tokens/inventory, a
registry browse-then-act flow, an artifact/diff viewer, run timeline, and
improvement proposals. That substance is real, implemented, and covered by
the GUI test suite.

This record resolves how the desktop window presents that substance. AWF is
voice-first by design — every capability flows through the speech stack
(STT/TTS/VAD/wake) — so the home surface is built around talking to the agent
and reading its reply back as text. The intended long-term shape is a single
conversation stream shared by both voice and typed chat; fusing them is a
back-end concern and is explicitly out of scope here, so the renderer keeps
one visible chat stream that both voice turns and typed messages land in,
rendered together. The visual language follows the read-only `../JARVISvX2`
prototype-demo — overall layout, interface sequencing, and glass surfaces —
tuned to the navy token set: a polished chat-messenger with deep-sky-blue
accent glows and rounded panels, with no orb and no new dependency. Two
earlier shapes were considered and rejected: a left-side vertical rail, and
a three-column always-visible console. A single active view with a sticky
top header is the right shape for a compact one-operator desktop window;
and, unlike a diagnostic-first home, the operator's most frequent surface is
talking to the agent, so the first page is the chat + voice surface alone —
status and diagnostics wait behind their own nav button.

## Decision

**The window is chat-forward with one active view.** `App.tsx` keeps the
`activeView` model; a sticky top header holds brand, view navigation, and
status. The first (default) view is **Chat** — the voice/chat surface by
itself; system status and diagnostics render only in the **Status** view,
opened from its own nav button.

- **The first page is a chat window-panel.** At launch, `Transcript` renders
  a titled chat window that fills the viewport below the top bar: an
  auto-scrolling bubble stream that follows the newest entry (`role="log"`),
  operator messages right-aligned with an avatar and agent messages
  left-aligned on glass, plus a composer bar with a mic (voice) button, a
  text input, and a Send button. Send appends the typed text to the same
  visible stream locally (text-first); the mic button drives the existing
  push-to-talk flow.
- **Voice and typed chat share one stream.** Voice (STT/TTS) turns and typed
  messages converge in the same conversation stream and render together in
  the one chat log; unifying them into one back-end stream is deferred (see
  Context) and is not a renderer concern. When voice handlers are absent,
  the page renders appropriately to what is available: the chat window takes
  the full width and the mic button is disabled.
- **Status/diagnostics sit behind a button.** The System readiness / LLM /
  Registry / Recent-verdicts cards never render below the chat; they live in
  the Status view reached from its top-nav button, matching the reference
  prototype's "talk first, inspect on demand" sequencing.
- **Voice is a simple button — not an orb.** There is no canvas, no particle
  visualization, no pulsing animation anywhere in the renderer.
  `VoiceActivation` presents a plain push-to-talk button plus a status chip
  in a compact column beside the chat window (ADR-0023's text-first invariant
  already makes voice state legible as a chip and transcript).
- **The control-center grammar applies app-wide.** Every view shares the
  command-center design language: a `.view-header` (uppercase mono kicker
  with an inline-SVG icon + a big light title), glass `.card` panels with
  16px corners and a hover accent border, `.stat-grid` of
  `.stat-card`s for health metrics, and refined `.chip`/`.list`/`.row`
  surfaces. A small shared inline-SVG icon set (`icons.tsx`) is used across
  the nav, view headers, status, and composer. No dependency is added — the
  icons are hand-rolled stroke SVGs that inherit `currentColor`.
- **Controls and status sit across the top** (mirroring the reference shell):
  brand badge + a system pill left, view navigation centre, status pills
  (profile id, readiness, LLM state, pending approvals) + Refresh right, on
  a navy-glass `backdrop-filter: blur()` surface with soft accent glows on
  the active nav item and primary button.
- **Look-and-feel reference.** The read-only `../JARVISvX2` prototype-demo
  supplies the overall layout, interface sequencing, and glass/accent
  treatment; AWF keeps its own navy token set (deep-sky-blue `#00bfff`
  accent, not vX2's cyan) and its own data substance.
- **Navy palette, declared once as names.** `:root` defines the canonical
  tokens; legacy shorthands derive from them so existing selectors are
  untouched:
  - `--color-bg-base: #070b12` (deep navy background)
  - `--color-panel: #111827` (card / panel surface)
  - `--color-elevated: #172033` (inputs, code, raised blocks)
  - `--color-accent: #00bfff` (deep sky blue — **not** cyan `#22d3ee`)
  - `--color-ready: #00ff99`
  - `--color-not-ready: #e0115f` (ruby)
  - `--color-warn: #fbbf24`
  - text: `#e2e8f0` / `#94a3b8` / `#64748b`; Inter / JetBrains Mono.
- **No new dependency.** The GUI keeps its existing React + plain-CSS stack;
  there is no icon library and no animation library.

## Mechanism

- **Top bar** (`.topbar`): `position: sticky; top: 0; z-index: 10`, navy
  translucent surface (no `backdrop-filter` — software compositors on WSLg
  mis-render blurred surfaces), `border-bottom`, flex layout with a `.brand`
  (accent `.brand-badge` tile + name + `.system-pill` + mono tagline),
  `.nav-list`/`.nav-item` (the active item gets an accent-tinted fill, a
  ring, and soft glow, plus the pending-approvals badge), and a
  right-aligned `.status-bar` of `.chip`s and the Refresh button.
- **Chat page** (`.chat-page`/`.chat-frame`): `.shell` is a fixed `100vh`
  flex column and `.main` a flex column with padding removed while the chat
  page is active, so a centered `max-width: 1152px` conversation frame with
  hairline side edges fills the viewport under the top bar, demo-style.
  Inside it, `.chat-window` (`flex: 1`) holds the title bar, the scrollable
  bubble stream, and the composer; the voice action bar (`.voice-bar`) sits
  under the composer. The Status view's diagnostics never render here.
- **Chat window** (`.chat-window`/`.chat-title`/`.chat-scroll`): a
  flex-column messenger with a fixed header row (ready `.chat-dot` + title),
  a `flex:1; overflow-y:auto` bubble stream bounded by the viewport (no
  fixed max-height), and a fixed composer bar (`.composer`) with `.btn-mic`,
  `.composer-input`, `.btn-send`. Sender alignment and letter avatars come
  from `.bubble-user`/`.bubble-agent`/`.avatar`. `Transcript` auto-scrolls
  to `scrollHeight` when entries change.
- **Voice** (`.voice-bar`, `.voice-ptt`): the existing `VoiceActivation`
  group is restyled into a two-row action bar under the composer — status
  chip + session id + start/push-to-talk/stop/submit/interrupt buttons on
  the first row, workflow/profile/recognized-text fields on the second —
  with a prominent accent push-to-talk button; all IPC wiring, session
  flow, and accessible names are unchanged.
- **Composer → voice**: the chat composer's mic button calls a ref-exposed
  `togglePushToTalk()` on `VoiceActivation` to drive the same push-to-talk
  session as the card's own button.
- **Window chrome** (`main.ts`): `BrowserWindow` `backgroundColor` is the
  navy base `#070b12` (a near-black navy that avoids plain `#0a0a0b`),
  `minWidth: 960`, `minHeight: 640`.

## Scope for implementation

1. `src/renderer/styles.css` — canonical `--color-*` tokens; viewport-height
   `.shell`/`.main` flex column (`.main:has(.chat-page)` padding-free);
   centered demo-style `.chat-page`/`.chat-frame` column with hairline side
   edges; `.chat-window` flex-fills the frame; `.voice-bar` action rows;
   `.brand-badge`/`.brand-text`/`.brand-tag` and `.chat-dot`; navy `.topbar`
   with soft shadow; body cyber-grid + radial glows; card/panel surfaces
   with hover accent; `.view-header`/`.view-kicker`/`.view-title`;
   `.stat-grid`/`.stat-card`; refined `.list`, `.row`, `.btn-*`,
   `.pre-scroll`, `.chip`; `.system-pill`, `.chat-title`/`.chat-scroll`,
   `.voice-ptt`, `.bubble*`, `.composer`, `.btn-mic`/`.btn-send`.
2. `src/renderer/icons.tsx` — inline stroke-SVG icon set (nav, view
   headers, status, composer) with no dependency; `ChatIcon` marks the
   first-page nav item.
3. `src/renderer/App.tsx` — brand badge + name/pill + tagline; nav items
   carry an icon; the views list always leads with Chat, followed by Status
   when status data is available; the Chat arm renders the centered
   conversation frame (chat window + voice action bar when voice handlers
   exist); the Status arm renders the `.view-header` ("Control center")
   above the Overview diagnostics.
4. `src/renderer/Overview.tsx` — System readiness rendered as `.stat-grid` of
   `.stat-card`s (device value, ready/not-ready with the ruby/green tokens).
5. `src/renderer/Transcript.tsx` — chat-messenger: bubble stream with
   avatars/sender alignment, empty state, ready `.chat-dot` in the title,
   and a composer bar (mic + input + Send); `onSend` appends locally,
   `onMic` drives the push-to-talk flow; voice turns and typed messages
   render in the same bubble log.
6. `src/renderer/VoiceActivation.tsx` — a `voice-ptt` class and a
   ref-exposed `togglePushToTalk()` for the composer's mic; rendered as the
   chat page's voice action bar, buttons only.
7. `src/main/main.ts` — `backgroundColor` `#070b12`.
8. Tests — `tests/App.rail.test.tsx` renamed to `tests/App.nav.test.tsx`;
   first-page tests (launch on Chat, diagnostics hidden until the Status
   button, voice + typed in one shared stream, composer); Transcript
   bubble/composer/mic/Send tests; `role="log"`, voice flow, and the
   no-orb/canvas invariant maintained.

## Acceptance

- `npm --prefix frontend run build --workspaces` and
  `npm --prefix frontend test --workspaces` pass (GUI: 13 files, 57 tests;
  shared: 1 file, 12 tests; CLI: 3 files, 41 tests).
- `grep` on the renderer confirms no `orb|pulse|canvas|@keyframes|particle`.
- The window shows a sticky top bar with brand badge + system pill,
  horizontal nav, and status pills — no rail, no three-column console.
- The default view at launch is Chat: a centered full-height conversation
  column (scrollable stream, composer, voice action bar) and nothing else.
  The System readiness / LLM / Registry / Recent-verdicts cards render only
  after clicking the Status nav button.
- Voice turns and typed messages render together in the same chat log; when
  voice handlers are absent, the chat window takes the full width and the
  mic button is disabled.
- The chat window is a scrollable bubble stream that auto-follows new
  entries, with a composer (mic + input + Send); voice is a push-to-talk
  button with a status chip; there is no orb/canvas.
- The control-center grammar is applied across all views: `.view-header`
  (kicker + title), glass `rounded-2xl` cards with hover accent borders, and
  `.stat-grid`/`.stat-card` for health metrics; icons are inline SVGs (no
  dependency added).
- Exactly one view renders at a time, switched by a top nav button.
- No new entry in `frontend/gui/package.json` dependencies or devDependencies.

## Consequences

- The desktop surface keeps ADR-0024's full data substance and the
  one-active-view model, re-sequenced like the reference prototype: the
  operator talks to the agent immediately on launch, and status/diagnostics
  wait one button away.
- The navy token set is a single named source of truth (`--color-*`), so a
  future theme change is one block in `:root` rather than a scatter of hex
  values.
- Voice and typed chat intentionally share one visible stream today; fusing
  them into a single back-end conversation is deferred and out of this
  record's scope.
