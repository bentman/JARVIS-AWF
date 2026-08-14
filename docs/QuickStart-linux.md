# Quick Start — Linux / WSL2

Sets up JARVIS-AWF on Linux or WSL2. Run every command from the repository root. Do not install this project's Python packages globally.

## Prerequisites

- Bash and Git
- Python `>=3.12,<3.15` with `venv` support
- Node.js 24 LTS `>=24.15.0` and npm, for the frontends
- Internet access for dependency and model acquisition

WSL2 reports itself as Linux and resolves as a Linux host. It needs no separate handling here.

Optional, for accelerated speech: an NVIDIA GPU with a working driver, a Linux-visible Qualcomm ARM64 NPU with the QNN runtime artifacts, or a Linux-visible Qualcomm/Adreno OpenCL runtime. CPU is the guaranteed floor on every host.

## Clone

```bash
git clone https://github.com/bentman/JARVIS-AWF.git
cd JARVIS-AWF
```

For an existing clone:

```bash
cd <REPO_ROOT_PATH>
git pull
```

## Recommended setup

```bash
bash scripts/bootstrap.sh
```

The wrapper creates `backend/.venv` when needed, installs AWF through the repo venv, installs the hardware-selected backend dependencies, bootstraps local state, acquires and verifies speech models, installs frontend dependencies when npm is available, runs `awf doctor`, and prints the first assistant run command. It writes the full transcript to `reports/diagnostics/<datetime>-bootstrap.txt`, including `--provision`, `--install`, `--verify`, model, and doctor output. Use `--skip-speech` only when diagnosing a dependency or model-acquisition outage.

The wrapper does not add `awf` to your shell `PATH`. Use `backend/.venv/bin/awf` unless you activate the venv or create your own shell alias.

The wrapper also does not acquire the managed LLM sidecar runtime. Run `backend/.venv/bin/awf llm acquire` after bootstrap when you want AWF to manage `llama-server` itself.

## Manual setup sequence

```text
create venv -> install -> provision -> bootstrap -> acquire models -> validate
```

### 1. Create the backend environment

```bash
python3.12 -m venv backend/.venv
backend/.venv/bin/python -m pip install --upgrade pip
```

Python 3.13 or 3.14 work as well. Use `backend/.venv/bin/python` for every command below; the project is never installed into a system interpreter.

### 2. Install the base package

```bash
backend/.venv/bin/python -m pip install -e ".[dev]"
```

This installs the core, the four console scripts (`awf`, `awf-setup`, `awf-secret`, `awf-speech`), and the dev tooling needed by validation, including pytest and Ruff. The scripts are created inside `backend/.venv/bin`; setup does not install global commands or modify your shell profile. Speech packages and the ONNX Runtime build are not part of the base set.

### 3. Provision the hardware-appropriate ONNX Runtime

```bash
backend/.venv/bin/awf-setup --provision
```

This probes the host and names one extra without installing anything:

| Extra | Selected when |
|---|---|
| `hw-ort-cuda` | x64 with an NVIDIA GPU and a CUDA driver |
| `hw-ort-directml` | Windows with an AMD or Intel GPU |
| `hw-ort-qnn` | Linux ARM64 as a QNN candidate, or Windows ARM64 with a Qualcomm NPU |
| `hw-ort-cpu` | everything else |

Install it, then confirm what resolution produced:

```bash
backend/.venv/bin/awf-setup --install --verify
```

`--verify` reports the installed ONNX Runtime distribution and version, its available execution providers, the installed Ruff version, and `pip check`. On any host with a non-CPU extra, `pip check` reports that `kokoro-onnx`, `openwakeword`, and `faster-whisper` require `onnxruntime` — expected, since those packages name the base distribution and have no way to express that an accelerator build satisfies it. `--verify` distinguishes that from a real failure.

### 4. Bootstrap local state

```bash
backend/.venv/bin/awf-setup
```

With no flags this generates `.env` with a fresh secret key, creates `cache/sandbox/`, and creates `data/awf_db/awf.db`.

### 5. Acquire the speech models

Speech packages are installed by `awf-setup --install` through the host-selected dependency extras.

```bash
backend/.venv/bin/awf-speech models sync
backend/.venv/bin/awf-speech models verify
```

`sync` downloads the artifacts named in `config/voice/{stt,tts,vad,wake}.yaml` into `models/`, and warms the STT model for the host's resolved device. It is idempotent — a second run changes nothing. `verify` reports each expected artifact as `OK` or `MISSING`.

On Linux/WSL x64 with CUDA, STT can use Faster Whisper when CTranslate2 reports CUDA devices. On Linux/WSL ARM64, setup installs the QNN package family as a candidate so runtime preflight can prove or reject it; STT can use the QNN Whisper artifact under `models/stt/whisper-qualcomm-qnn` only when the QNN provider/backend tokens are present. Adreno/OpenCL is tracked as a separate GPU path for LLM readiness. CPU remains the floor through ONNX Whisper. OpenWakeWord is installed using the sibling-project pattern: AWF installs its usable sibling dependencies (`requests`, `scikit-learn`, `scipy`) with the rest of the selected requirements, then installs `openwakeword` with `--no-deps` to avoid the unavailable `tflite-runtime` metadata dependency and verifies that `openwakeword` and `onnxruntime` actually import.

### 6. Acquire the managed LLM runtime, when needed

If you want AWF to start and stop its own `llama-server`, acquire the runtime declared for this host in `config/llm/servers.yaml`:

```bash
backend/.venv/bin/awf llm acquire
```

For Linux x64 CPU this populates:

```text
runtimes/llama.cpp/linux-x64-cpu/llama-server
```

Some accelerator entries are declared as manual in `config/llm/servers.yaml`; for those, `llm acquire` reports the runtime directory the operator must populate.

This does not download GGUF model weights. Managed `llama-server` expects operator-provided `.gguf` files under `models/llm/<model-name>/`.

Skip this step when you use an operator-run endpoint such as Ollama or another OpenAI-compatible server. Select that server instead:

```bash
backend/.venv/bin/awf llm select openai-compatible --model "<server-model-name>"
```

### 7. Validate

```bash
backend/.venv/bin/python scripts/validate_backend.py profile
backend/.venv/bin/python scripts/validate_backend.py lint
backend/.venv/bin/python scripts/validate_backend.py ci
```

`profile` writes a timestamped report to `reports/diagnostics/` naming the resolved hardware profile, the preflight tokens, and the per-function readiness results. `lint` runs Ruff format/check in read-only mode. `ci` runs `lint` first, then everything except the tests marked `live`, and writes its own validation report.

### 8. Frontends

```bash
npm --prefix frontend install
npm --prefix frontend test
npm --prefix frontend run dev
# npm --prefix frontend run build
```

## Validation commands

```bash
backend/.venv/bin/python scripts/validate_backend.py profile
backend/.venv/bin/python scripts/validate_backend.py lint
backend/.venv/bin/python scripts/validate_backend.py unit
backend/.venv/bin/python scripts/validate_backend.py integration
backend/.venv/bin/python scripts/validate_backend.py runtime
backend/.venv/bin/python scripts/validate_backend.py regression
backend/.venv/bin/python scripts/validate_backend.py ci
```

Exit codes: `0` pass, `1` fail, `2` skipped, `3` environment unsatisfied. `runtime` runs only the tests marked `live`, which need real hardware and the acquired models; it returns `2` when the host cannot satisfy them.

`profile` writes to `reports/diagnostics/`; every validation command writes one timestamped report to `reports/validation/`. Test commands stream each test's name, progress, and result, then end with pass/fail/skip/warning counts.

## Running AWF

```bash
backend/.venv/bin/awf run assistant-default@1.0.0 --objective "check the system"
backend/.venv/bin/awf runs
backend/.venv/bin/awf status <run-id>
backend/.venv/bin/awf artifacts <run-id>
backend/.venv/bin/awf approvals
backend/.venv/bin/awf doctor
```

`assistant-default@1.0.0` is the local first-run workflow. It verifies that AWF can accept a request, create a durable Run, and return response text without requiring an external coding-agent CLI. Use implementation workflows after the relevant agent CLIs are installed and authenticated.

The run, status, runs, resume, approvals, artifacts, readiness, and doctor commands print operator-readable summaries by default. Add `--json` when automation needs the raw payload.

Store a provider API key by name, so it never appears in a registry file:

```bash
backend/.venv/bin/awf-secret set OPENAI_API_KEY
```

A voice round trip takes a pre-recorded wake file and command file, and writes a spoken response:

```bash
backend/.venv/bin/awf-speech round-trip <wake.wav> <command.wav> --response-audio-out <out.wav>
```

Omitting `--voice-id` uses the `narrator` Voice Profile's voice. Any other voice remains selectable by passing the flag.

## Repository rules that matter

- `pyproject.toml` is the only place Python dependencies are declared.
- Install through `awf-setup --install` rather than by hand, so the ONNX Runtime distribution stays consistent with the host.
- `models/`, `data/`, `cache/`, and `reports/` are local state and stay out of commits.
- Record validation claims with the command output that produced them.

## Common diagnostics

Python version rejected — install 3.12, 3.13, or 3.14 with venv support and recreate `backend/.venv`.

Wrong ONNX Runtime installed, or providers missing:

```bash
backend/.venv/bin/awf-setup --provision
backend/.venv/bin/awf-setup --install --verify
```

Install or setup state unclear:

```bash
backend/.venv/bin/awf doctor
```

Speech models missing:

```bash
backend/.venv/bin/awf-speech models verify
backend/.venv/bin/awf-speech models sync
```

Accelerator detected but not selected — run `profile` and read the readiness reasons; each names the hardware fact and the runtime token it required:

```bash
backend/.venv/bin/python scripts/validate_backend.py profile
```

STT and TTS resolve their devices independently. STT uses Faster Whisper/CTranslate2 for verified CUDA acceleration and ONNX Whisper for the CPU floor; TTS runs on ONNX Runtime and needs the matching execution provider. One reaching `cuda` while the other stays on `cpu` is a normal outcome, not an error.
