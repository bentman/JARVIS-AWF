# AWF Operator's Guide

Use this after setup. The setup source of truth is:

- `docs/QuickStart-windows.md`
- `docs/QuickStart-linux.md`

AWF has three operator surfaces over the same backend and database:

- GUI: desktop control center, chat, voice, approvals, runs, memory, registry.
- TUI: terminal chat and slash-command operator console.
- Core CLI: direct commands for scripts, diagnostics, and precise actions.

The backend command is installed in the repo venv, not globally. On Windows use
`.\backend\.venv\Scripts\awf.exe`; on Linux/WSL use `backend/.venv/bin/awf`.
Plain `awf` works only if your shell has that venv on `PATH`.

## Start The App

From the repo root:

```bash
npm --prefix frontend run dev
```

That builds the frontend workspaces and starts the Electron GUI. The GUI starts
`awf serve --stdio` from `backend/.venv` automatically.

If you launch from another directory, set `AWF_REPO_ROOT` first.

Windows PowerShell:

```powershell
$env:AWF_REPO_ROOT = "E:\WORK\CODE\REPO\JARVIS-AWF"
npm --prefix frontend run dev
```

Linux/WSL:

```bash
AWF_REPO_ROOT=/path/to/JARVIS-AWF npm --prefix frontend run dev
```

If backend resolution is wrong, set `AWF_CORE_COMMAND`.

Windows PowerShell:

```powershell
$env:AWF_CORE_COMMAND = "E:\WORK\CODE\REPO\JARVIS-AWF\backend\.venv\Scripts\awf.exe"
npm --prefix frontend run dev
```

Linux/WSL:

```bash
AWF_CORE_COMMAND=/path/to/JARVIS-AWF/backend/.venv/bin/awf npm --prefix frontend run dev
```

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

Windows PowerShell:

```powershell
.\backend\.venv\Scripts\awf.exe llm servers
.\backend\.venv\Scripts\awf.exe llm models
.\backend\.venv\Scripts\awf.exe llm serve status
```

Linux/WSL:

```bash
backend/.venv/bin/awf llm servers
backend/.venv/bin/awf llm models
backend/.venv/bin/awf llm serve status
```

Acquire a managed llama.cpp runtime:

```powershell
.\backend\.venv\Scripts\awf.exe llm acquire
```

```bash
backend/.venv/bin/awf llm acquire
```

Select an operator-run OpenAI-compatible server instead:

```powershell
.\backend\.venv\Scripts\awf.exe llm select openai-compatible --model "Qwen/Qwen3-8B-GGUF:Q5_K_M"
```

```bash
backend/.venv/bin/awf llm select openai-compatible --model "Qwen/Qwen3-8B-GGUF:Q5_K_M"
```

Managed `llama-server` also needs a local `.gguf` under `models/llm/<name>/`
before it can start. Operator-run servers keep their own model store.

## TUI

Start the terminal UI after the frontend has been built:

```bash
node frontend/cli/dist/cli.js
```

Use `/help` inside the TUI for the current slash-command list. Plain text starts
the default assistant workflow, so it has the same LLM requirement as GUI chat.

## Core CLI

Common Windows commands:

```powershell
.\backend\.venv\Scripts\awf.exe doctor
.\backend\.venv\Scripts\awf.exe readiness
.\backend\.venv\Scripts\awf.exe run assistant-default@1.0.0 --objective "check the system"
.\backend\.venv\Scripts\awf.exe runs
.\backend\.venv\Scripts\awf.exe status <run-id>
.\backend\.venv\Scripts\awf.exe artifacts <run-id>
.\backend\.venv\Scripts\awf.exe approvals
```

Common Linux/WSL commands:

```bash
backend/.venv/bin/awf doctor
backend/.venv/bin/awf readiness
backend/.venv/bin/awf run assistant-default@1.0.0 --objective "check the system"
backend/.venv/bin/awf runs
backend/.venv/bin/awf status <run-id>
backend/.venv/bin/awf artifacts <run-id>
backend/.venv/bin/awf approvals
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

Use the repo-local venv path for `awf` unless your shell has an alias or `PATH`
entry.

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

Use the venv-local `awf-speech` path when it is not on `PATH`.

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

- restart the GUI so it starts a fresh `awf serve --stdio` backend;
- check `AWF_REPO_ROOT` if launched outside the repo;
- check `AWF_CORE_COMMAND` if the wrong backend venv is being used.

Chat fails while Status loads:

- confirm the resident model profile points at the intended server;
- use `awf llm select openai-compatible --model <name>` for an operator-run
  OpenAI-compatible endpoint;
- use `awf llm acquire`, local GGUF placement, `awf llm select llama-server`,
  then `awf llm serve start` for a managed sidecar.

Setup, dependency repair, and first-install validation belong in the QuickStart
docs, not this guide.
