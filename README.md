# JARVIS-AWF

JARVIS-AWF is an implementation of the Agentic Workflow Fabric: a local-first
control system for running explicit, versioned workflow definitions. Workflows
can call local activities or drive AI coding and research agents. The project
is built around one operator running it on their own machines.

A Run is one execution of a versioned Workflow. AWF records run state, step
state, events, approvals, and artifacts in local storage so work can be
inspected and resumed.

## Quick Start

Use the platform guide for setup:

- [Linux / WSL2](docs/QuickStart-linux.md)
- [Windows x64 / ARM64](docs/QuickStart-windows.md)

Bootstrap from the repo root:

```bash
bash scripts/bootstrap.sh
```

```powershell
.\scripts\bootstrap.ps1
```

Then load the repo-local command helper for your shell:

```bash
source scripts/use-awf.sh
```

```powershell
. .\scripts\use-awf.ps1
```

The helper is session-local. It does not install global commands, edit shell
profiles, or change `PATH`.

First check:

```bash
awf doctor
awf run assistant-default@1.0.0 --objective "check the system"
```

Normal operation is covered in [docs/OperatorsGuide.md](docs/OperatorsGuide.md).

## Architecture

- Durable state lives under `data/`, with SQLite for run state and
  content-addressed files for artifacts.
- Repository defaults live under `config/app_registry/`; operator registry
  objects and overrides live under `data/registry/`; operator interface
  preferences persist in `.awf/settings.json`.
- The Capability Guard checks requested actions against declared capabilities,
  risk classes, and allowlists before execution.
- Mutating runs use an isolated Git worktree and scratch space.
- The core CLI, terminal UI, and GUI use the same JSON-RPC protocol surface.
- Speech and local LLM runtimes are operator-managed local assets under
  `models/` and `runtimes/`.

The design target is documented in
[docs/AGENTIC_WORKFLOW_FABRIC_SPEC.md](docs/AGENTIC_WORKFLOW_FABRIC_SPEC.md).
Decision records and deviations are under [docs/adr](docs/adr).

## Interfaces

- `awf`: core CLI for runs, approvals, registry actions, diagnostics, memory,
  and LLM/runtime commands.
- `awf-gui`: desktop GUI for chat, runs, approvals, readiness, registry,
  memory, and voice navigation, with global shortcuts (`Ctrl+1/2/3`, `Ctrl+K`, `Escape`) and operator theme settings.
- `awf-cli`: terminal UI with chat, slash commands, input history, and Tab autocompletion.
- `awf-speech`: speech model checks, wake word testing, and file-based voice diagnostics (`awf-speech wake <audio.wav>`).

## Platform

Supported targets are Linux, WSL2, Windows x64, and Windows ARM64. CPU is the
baseline runtime path. CUDA, DirectML, QNN, and Adreno/OpenCL paths are used
only when setup probes verify the required host runtime.

Python dependencies are installed into `backend/.venv`. Frontends use the
Node.js workspace under `frontend/`.

## Status

This is an active personal project. The local bootstrap path, core CLI,
registry, workflow runtime, protocol client, GUI, TUI, speech setup, and local
LLM server management are implemented. Some optional extension points remain
documented but not built, including container isolation and broader remote
agent integration.

## Contributions

Ideas, feedback, and bug reports are welcome through issues or comments. The
project is not ready for fork/branch contribution work or pull-request review
flows yet.

## License

Apache License 2.0. Voice components, LLM model usage, and coding agents driven
by adapters remain under their own upstream licenses.
