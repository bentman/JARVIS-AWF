# Quick Start - Linux / WSL2

Set up JARVIS-AWF on Linux or WSL2. Run commands from Bash at the repository
root. Do not install this project's Python packages globally.

## Prerequisites

- Git
- Python `>=3.12,<3.15` with `venv` support
- Node.js 24 LTS `>=24.15.0` and npm
- Internet access for dependencies and model files

WSL2 resolves as a Linux host. CPU is the supported floor; CUDA, QNN, and
Adreno/OpenCL paths are selected only when setup can verify the required
runtime.

## Setup

```bash
git clone https://github.com/bentman/JARVIS-AWF.git
cd JARVIS-AWF
bash scripts/bootstrap.sh
```

The bootstrap script creates `backend/.venv`, installs the repo package and
host-selected runtime dependencies (including speech, wake-word, model-gateway,
and accelerator packages), initializes local state, acquires speech models,
installs frontend dependencies when npm is available, runs `awf doctor`, and
writes a transcript to `reports/diagnostics/`.

Load the repo-local command helper in the same terminal:

```bash
source scripts/use-awf.sh
```

The helper is session-local. It does not edit your shell startup files, install
global commands, or change `PATH`.

## First Check

```bash
awf doctor
awf readiness
```

Start the GUI:

```bash
awf-gui
```

Start the terminal UI:

```bash
awf-cli
```

## LLM Runtime

The default assistant workflow routes model calls through a local
OpenAI-compatible endpoint (e.g. `http://127.0.0.1:8080/v1`).

To have AWF manage a local `llama-server`, acquire the runtime and provide a
`.gguf` model under `models/llm/<model-name>/`:

```bash
awf llm acquire
awf llm select llama-server
awf llm serve start
```

For an existing operator-run OpenAI-compatible server (e.g. Ollama, LM Studio, or vLLM):

```bash
awf llm select openai-compatible --model "<server-model-name>"
```

Run the assistant workflow once an LLM server is active:

```bash
awf run assistant-default@1.0.0 --objective "check the system"
```

## Useful Checks

```bash
awf llm servers
awf llm serve status
awf-speech models verify
```

Use `docs/OperatorsGuide.md` after setup for normal operation,
troubleshooting, and validation commands.
