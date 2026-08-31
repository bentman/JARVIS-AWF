# Quick Start - Windows

Set up JARVIS-AWF on Windows x64 or ARM64. Run commands from PowerShell at the
repository root. Do not install this project's Python packages globally.

## Prerequisites

- Git
- Python `>=3.12,<3.15` through the Windows `py` launcher
- Node.js 24 LTS `>=24.15.0` and npm
- Internet access for dependencies and model files

CPU is the supported floor. NVIDIA CUDA, DirectML, and Qualcomm QNN paths are
selected only when setup can verify the required runtime.

## Setup

```powershell
git clone https://github.com/bentman/JARVIS-AWF.git
Set-Location .\JARVIS-AWF
.\scripts\bootstrap.ps1
```

The bootstrap script creates `backend\.venv`, installs the repo package and
host-selected runtime dependencies (including speech, wake-word, model-gateway,
and accelerator packages), initializes local state, acquires speech models,
installs frontend dependencies when npm is available, runs `awf doctor`, and
writes a transcript to `reports\diagnostics\`.

Load the repo-local command helper in the same terminal:

```powershell
. .\scripts\use-awf.ps1
```

The helper is session-local. It does not edit your profile, install global
commands, or change `PATH`.

## First Check

```powershell
awf control
awf doctor
awf system readiness
```

`awf control` is the primary operating view in the CLI. It shows the same
backend-derived operator queue that the GUI opens on: blocked approvals, active
or failed runs, ready proposals, readiness/LLM configuration, and the next
operator action. Every item names the exact command that resolves it.

There are eight top-level commands - `run`, `status`, `control`, `doctor`,
`review`, `registry`, `memory`, and `system`. `awf --help` lists them with a
one-line description each, and `awf <command> --help` explains its arguments and
subcommands. If a command you know from an older build reports `invalid choice`,
it moved: see Commands That Moved in `docs\OperatorsGuide.md`.

Start the GUI:

```powershell
awf-gui
```

The GUI has three destinations and opens on the first:

- **Operate** - the work queue, Start work, run detail and evidence, approvals,
  proposed changes, run history, and system overview;
- **Chat** - typed conversation with the default assistant workflow;
- **Library** - registry browsing and memory curation.

Use Operate's Start work panel to choose a trusted workflow, fill the
schema-derived inputs, start the run, then resolve any Needs action cards from
the same view.

Start the terminal UI:

```powershell
awf-cli
```

Type `/help` inside it for the slash-command list, grouped by task. `/review`,
`/memory`, and `/system` take the same subcommands as their `awf` counterparts.

## LLM Runtime

The default assistant workflow routes model calls through a local
OpenAI-compatible endpoint (e.g. `http://127.0.0.1:8080/v1`).

To have AWF manage a local `llama-server`, acquire the runtime and provide a
`.gguf` model under `models\llm\<model-name>\`:

```powershell
awf system llm acquire
awf system llm select llama-server
awf system llm serve start
```

For an existing operator-run OpenAI-compatible server (e.g. Ollama, LM Studio, or vLLM):

```powershell
awf system llm select openai-compatible --model "<server-model-name>"
```

Run the assistant workflow once an LLM server is active:

```powershell
awf run assistant-default@1.0.0 --objective "check the system"
```

The same workflow is available in the GUI from Operate > Start work. Workflow
rows in Library also have a Run handoff that returns to the same start form.

## Useful Checks

```powershell
awf system llm servers
awf system llm serve status
awf-speech models sync
awf-speech models verify
```

Speech models are operator-managed local artifacts under `models\`. Runtime STT
uses local files only; if the selected STT artifact is incomplete, transcription
returns a clear local-model error instead of downloading implicitly.

Use `docs\OperatorsGuide.md` after setup for normal operation,
troubleshooting, and validation commands.
