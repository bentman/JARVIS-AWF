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
host-selected runtime dependencies, initializes local state, acquires speech
models, installs frontend dependencies when npm is available, runs `awf doctor`,
and writes a transcript to `reports\diagnostics\`.

Load the repo-local command helper in the same terminal:

```powershell
. .\scripts\use-awf.ps1
```

The helper is session-local. It does not edit your profile, install global
commands, or change `PATH`.

## First Check

```powershell
awf doctor
awf run assistant-default@1.0.0 --objective "check the system"
```

Start the GUI:

```powershell
awf-gui
```

Start the terminal UI after the frontend has been built:

```powershell
awf-cli
```

## Optional LLM Runtime

If AWF should manage its own `llama-server`, acquire the runtime and provide a
local `.gguf` model under `models\llm\<model-name>\`:

```powershell
awf llm acquire
awf llm select llama-server
awf llm serve start
```

For an operator-run OpenAI-compatible server, select it instead:

```powershell
awf llm select openai-compatible --model "<server-model-name>"
```

## Useful Checks

```powershell
awf readiness
awf llm servers
awf llm serve status
awf-speech models verify
```

Use `docs\OperatorsGuide.md` after setup for normal operation,
troubleshooting, and validation commands.
