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

Chat:

- sends text into the default workflow, usually `assistant-default@1.0.0`;
- uses the resident model profile, so it needs a reachable local LLM endpoint;
- shows conversation turns and pending errors.

Status:

- shows operator readiness, system readiness, LLM status, recent runs,
  approvals, and registry counts;
- use Refresh when local runtime state changed outside the GUI.

Runs:

- lists active and recent durable workflow runs;
- opens run detail, step outputs, current node state, artifacts, and terminal
  outcome.

Approvals:

- shows pending approval records;
- displays the exact action digest and preview when available;
- approval applies only to that exact action.

Proposals:

- shows drafted registry proposals;
- use it for authored workflows, memories, and other proposal-backed objects.

Memory:

- searches durable memory and session-adjacent context;
- publishing semantic memory remains explicit.

Registry:

- browses repo defaults under `config/app_registry/` and operator objects under
  `data/registry/`;
- data-root objects shadow config-root defaults by normal registry precedence.

## Chat And LLM

There are two different local LLM shapes:

- Managed `llama-server`: AWF owns the sidecar binary under
  `runtimes/llama.cpp/<profile-id>/`.
- Operator-run OpenAI-compatible server: you run the server, AWF only probes and
  calls it.

Check status:

```bash
awf llm servers
awf llm models
awf llm serve status
```

Acquire a managed llama.cpp runtime:

```bash
awf llm acquire
```

Select an operator-run OpenAI-compatible server instead:

```bash
awf llm select openai-compatible --model "Qwen/Qwen3-8B-GGUF:Q5_K_M"
```

Managed `llama-server` also needs a local `.gguf` under `models/llm/<name>/`
before it can start. Operator-run servers keep their own model store.

## TUI

Start the terminal UI after the frontend has been built:

```bash
awf-cli
```

Use `/help` inside the TUI for the current slash-command list. Plain text starts
the default assistant workflow, so it has the same LLM requirement as GUI chat.

## Core CLI

Common commands:

```bash
awf doctor
awf readiness
awf run assistant-default@1.0.0 --objective "check the system"
awf runs
awf status <run-id>
awf artifacts <run-id>
awf approvals
```

Most commands print readable summaries. Use `--json` where the command exposes
it and you need raw payloads for automation.

## Runs

A Run is one durable workflow execution. AWF records steps, events, artifacts,
approvals, and final outcome in `data/awf_db/awf.db`.

Useful flow:

```bash
awf run <workflow>@<version> --objective "describe the work"
awf runs
awf status <run-id>
awf artifacts <run-id>
awf resume
```

## Approvals

AWF proposes, you approve. Higher-risk activity nodes and agent nodes park the
run until an approval is resolved.

Approval flow:

```bash
awf approvals
awf approve <approval-id>
awf reject <approval-id> --reason "explain why"
```

Inspect approval detail and action preview in the GUI Approvals view or the TUI
approval slash command.

An approval is bound to an action digest. If the action changes, the old
approval no longer applies. Voice alone cannot approve risky actions.

## Voice

Voice in the GUI is push-to-talk plus typed fallback. Browser speech recognition
availability is host-dependent; the typed final text path remains reliable.

Debug file-based voice from the CLI:

```bash
awf-speech round-trip <wake.wav> <command.wav> --response-audio-out <out.wav>
awf-speech models verify
```

## Memory

Session context is temporary conversation state. Semantic memory is durable and
proposal-backed.

Useful commands:

```bash
awf session start --title "today"
awf session show <session-id>
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
awf readiness
awf llm servers
awf llm serve status
awf-speech models verify
```

GUI opens but Status is empty or stale:

- restart the GUI so it starts a fresh AWF backend;
- confirm your terminal is at the repo root;
- reload the session helper for your platform.

Chat fails while Status loads:

- confirm the resident model profile points at the intended server;
- use `awf llm select openai-compatible --model <name>` for an operator-run
  OpenAI-compatible endpoint;
- use `awf llm acquire`, local GGUF placement, `awf llm select llama-server`,
  then `awf llm serve start` for a managed sidecar.

Setup, dependency repair, and first-install validation belong in the QuickStart
docs, not this guide.
