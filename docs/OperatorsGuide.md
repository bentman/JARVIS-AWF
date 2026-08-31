# AWF Operator's Guide

Use this after setup. The setup source of truth is:

- `docs/QuickStart-windows.md`
- `docs/QuickStart-linux.md`

AWF has three operator surfaces over the same backend and database:

- GUI: desktop control center, chat, voice, approvals, runs, memory, registry.
- TUI: terminal chat and slash-command operator console.
- Core CLI: direct commands for scripts, diagnostics, and precise actions.

## Start A Shell Session

From the repo root, load the repo-local command helpers once per shell session.
They do not edit your shell profile, install global commands, or change your
system `PATH`. They only define functions in the current terminal that call the
AWF executables inside `backend/.venv`.

Windows PowerShell:

```powershell
. .\scripts\use-awf.ps1
```

Linux/WSL:

```bash
source scripts/use-awf.sh
```

After that, use `awf`, `awf-speech`, `awf-gui`, and `awf-cli` from the repo
root. Open a new terminal or reload the helper when you want a fresh session.

## Start The App

Start the desktop GUI:

```bash
awf-gui
```

The helper runs the frontend from the repo root. The GUI starts the AWF core
from the repo venv automatically, so operators do not need to set backend
environment variables before launch.

## GUI Map

Operate:

- is the default control-center home view;
- shows a Start work panel backed by trusted workflow registry entries;
- renders workflow inputs from the workflow input schema, with advanced JSON
  input available for unsupported shapes;
- groups backend-derived work items into Start work, Needs action, Running, and
  Review / close out lanes;
- is fed by `awf/control.summary`; the GUI does not derive a separate
  frontend-only operating state;
- opens actionable run detail, approval review, proposal review, or readiness
  actions from the relevant card;
- keeps raw event data behind an advanced disclosure.

Chat:

- sends text into the default workflow, usually `assistant-default@1.0.0`;
- uses the resident model profile, so it needs a reachable local LLM endpoint;
- shows conversation turns, started run IDs, pending errors, and the next action
  returned by the run outcome.

Operate diagnostics:

- shows operator readiness, system readiness, LLM status, recent runs,
  approvals, and registry counts;
- use Refresh when local runtime state changed outside the GUI.

Operate also carries, in urgency order below the queue:

- pending approvals, with the exact action digest and preview when available;
  an approval applies only to that exact action;
- drafted registry proposals and proposed code changes, with their review
  actions;
- run history, which opens run detail with status, steps, approvals, artifacts,
  verdicts, failures, proposal follow-ups, and next actions in one operational
  timeline, fed by `awf/control.runDetail`;
- system readiness, LLM status, and registry counts.

Library:

- browses repo defaults under `config/app_registry/` and operator objects under
  `data/registry/`;
- shows source and trust badges plus a selected-object summary;
- surfaces workflow input schemas and a Run handoff that opens the Operate
  start flow for that workflow;
- data-root objects shadow config-root defaults by normal registry precedence;
- searches durable memory and session-adjacent context; publishing semantic
  memory remains explicit.

## Operating Loop

Normal operation starts at Operate:

```bash
awf control
```

1. Start work from the Operate Start work panel, Chat, the Library Run handoff,
   or `awf run <workflow>@<version>`.
2. Watch the linked run in Operate or `awf status <run-id>`.
3. Resolve the highest-priority Needs action card: approval, failed run,
   readiness check, LLM configuration item, or doctor item.
4. Review evidence, verdict artifacts, failed steps, and proposal context from
   the selected run detail.
5. Approve, reject with a reason, request merge approval, merge, or reject a
   proposal from the same context where the evidence appears.
6. Close out when Review / close out is empty or every remaining item has been
   inspected.

## Chat And LLM

There are two different local LLM shapes:

- Managed `llama-server`: AWF owns the sidecar binary under
  `runtimes/llama.cpp/<profile-id>/`.
- Operator-run OpenAI-compatible server: you run the server, AWF only probes and
  calls it.

Check status:

```bash
awf system llm servers
awf system llm models
awf system llm serve status
```

Acquire a managed llama.cpp runtime:

```bash
awf system llm acquire
```

Select an operator-run OpenAI-compatible server instead:

```bash
awf system llm select openai-compatible --model "Qwen/Qwen3-8B-GGUF:Q5_K_M"
```

Managed `llama-server` also needs a local `.gguf` under `models/llm/<name>/`
before it can start. Operator-run servers keep their own model store.

## TUI

Start the terminal UI after the frontend has been built:

```bash
awf-cli
```

Use `/help` inside the TUI for the current slash-command list, grouped by task
with a Start here section. `/review` and `/memory` take the same subcommands as
`awf review` and `awf memory`. Plain text starts the default assistant workflow,
so it has the same LLM requirement as GUI chat.

## Core CLI

Common commands:

```bash
awf control
awf doctor
awf system readiness
awf run assistant-default@1.0.0 --objective "check the system"
awf status
awf status <run-id>
awf status <run-id> --artifacts
awf review list
```

`awf --help` lists every command with a one-line description, and
`awf <command> --help` explains its arguments. There are eight commands:
`run`, `status`, `control`, `doctor`, `review` (decisions), `registry`
(published objects), `memory` (what the system remembers), and `system`
(readiness, resume, llm, secret, serve).

ADR-0029 replaced the older spellings rather than aliasing them, so
`awf approvals`, `awf runs`, `awf artifacts`, `awf improvement ...`,
`awf proposal ...`, `awf session ...`, and the rest are now errors. The table in
that ADR names the replacement for each.

Most commands print readable summaries. Use `--json` where the command exposes
it and you need raw payloads for automation - `awf system readiness --json`
carries the raw capability probe tokens behind the per-function summary.

## Runs

A Run is one durable workflow execution. AWF records steps, events, artifacts,
approvals, and final outcome in `data/awf_db/awf.db`.

Useful flow:

```bash
awf run <workflow>@<version> --objective "describe the work"
awf status
awf status <run-id>
awf status <run-id> --artifacts
awf system resume
```

## Approvals

AWF proposes, you approve. Higher-risk activity nodes and agent nodes park the
run until an approval is resolved.

Approval flow:

```bash
awf review list
awf review show <id>
awf review approve <id>
awf review reject <id> --reason "explain why"
```

`awf review` takes any id an operator can act on - a pending approval, a
proposed code change, or a drafted registry object - and resolves which one it
names. `awf review list` shows everything waiting at once.

Inspect approval detail and action preview in the GUI Operate view or with
`/review show <id>` in the TUI.

An approval is bound to an action digest. If the action changes, the old
approval no longer applies. Voice alone cannot approve risky actions.

## Voice

Voice in the GUI is push-to-talk plus typed fallback. Browser speech recognition
availability is host-dependent; the typed final text path remains reliable.

Debug file-based voice from the CLI:

```bash
awf-speech round-trip <wake.wav> <command.wav> --response-audio-out <out.wav>
awf-speech transcribe <command.wav>
awf-speech models sync
awf-speech models verify
```

Speech models are local operator artifacts under `models/`. Use
`awf-speech models sync` to acquire them and `awf-speech models verify` to check
presence. Runtime STT uses local files only; a missing or incomplete STT model
returns a structured local-model error instead of downloading during
transcription. CPU TTS pins the CPU ONNX Runtime provider, so a broken
accelerator provider does not prevent CPU synthesis.

## Memory

Session context is temporary conversation state. Semantic memory is durable and
proposal-backed.

Useful commands:

```bash
awf memory session-start --title "today"
awf memory session-show <session-id>
awf memory search <query>
awf memory get <name>@<version>
awf memory propose --file <path>
awf memory publish <proposal-id> --digest <digest>
awf memory reject <proposal-id> --reason "not true"
```

Models may propose memory; operators publish it.

## Registry

Registry roots:

- `config/app_registry/`: repo-tracked defaults.
- `data/registry/`: operator-owned objects and overrides.

Browse through the GUI Registry tab or the TUI slash commands. Core actions:

```bash
awf registry validate <file> --kind <kind>
awf registry publish <file> --kind <kind>
awf registry reindex
awf registry trust <kind> <name> <version> --status trusted
awf registry retire <kind> <name> <version>
```

Quarantined or blocked objects do not run.

## Agent CLIs

Implementation workflows may call external agent CLIs such as Claude Code,
Codex CLI, GitHub Copilot CLI, Antigravity CLI, or Cline CLI. AWF does not
install or authenticate those tools. `awf doctor` reports which are visible.

MCP use is currently fail-closed for adapters without a pre-tool Guard hook.

## Local State

Keep:

- `data/`: database, registry overrides, proposals, artifacts;
- `.env`: local encryption key;
- `models/`: operator/downloaded models;
- `runtimes/`: acquired or manually staged sidecar binaries.

Usually safe to delete:

- `cache/`: scratch state and temporary worktrees;
- `reports/`: diagnostics and validation evidence after saving what matters.

## Troubleshooting

Install state unclear:

```bash
awf doctor
```

Hardware or runtime state unclear:

```bash
awf system readiness
awf system llm servers
awf system llm serve status
awf-speech models sync
awf-speech models verify
```

GUI opens but Operate is empty or stale:

- restart the GUI so it starts a fresh AWF backend;
- confirm your terminal is at the repo root;
- reload the session helper for your platform.

Chat fails while Operate loads:

- confirm the resident model profile points at the intended server;
- use `awf system llm select openai-compatible --model <name>` for an operator-run
  OpenAI-compatible endpoint;
- use `awf system llm acquire`, local GGUF placement, `awf system llm select llama-server`,
  then `awf system llm serve start` for a managed sidecar.

A command failed with a message you want to trace:

```bash
AWF_DEBUG=1 awf <command>
```

The CLI reports failures as `error: <message>` and exits non-zero. `AWF_DEBUG=1`
raises the underlying traceback instead.

Setup, dependency repair, and first-install validation belong in the QuickStart
docs, not this guide.
