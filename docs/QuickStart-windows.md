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

`awf --help` lists every command with a one-line description, and
`awf <command> --help` explains its arguments.

`awf control` is the primary operating view in the CLI. It shows the same
backend-derived operator queue that the GUI opens on: blocked approvals, active
or failed runs, ready proposals, readiness/LLM configuration, and the next
operator action.

Start the GUI:

```powershell
awf-gui
```

The GUI opens to Operate, the control-center home view (Operate, Chat, and
Library are the three destinations). Chat remains available
for starting work. Use Operate's Start work panel to choose a trusted workflow,
fill the schema-derived inputs, start the run, and then resolve any Needs action
cards from the same view.

Start the terminal UI:

```powershell
awf-cli
```

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

The same workflow is available in the GUI from Operate > Start work. Registry
workflow rows also have a Run handoff that returns to the same start form.

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
