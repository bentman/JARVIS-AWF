# Quick Start — Linux / WSL2

Sets up JARVIS-AWF on Linux or WSL2. Run every command from the repository root. Do not install this project's Python packages globally.

## Prerequisites

- Bash and Git
- Python `>=3.12,<3.15` with `venv` support
- Node.js and npm, for the frontends
- Internet access for dependency and model acquisition

WSL2 reports itself as Linux and resolves as a Linux host. It needs no separate handling here.

Optional, for accelerated speech: an NVIDIA GPU with a working driver. CPU is the guaranteed floor on every host.

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

## Setup sequence

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

This installs the core, the four console scripts (`awf`, `awf-setup`, `awf-secret`, `awf-speech`), and the test dependencies. The ONNX Runtime build is not part of the base set — the next step selects it.

### 3. Provision the hardware-appropriate ONNX Runtime

```bash
backend/.venv/bin/awf-setup --provision
```

This probes the host and names one extra without installing anything:

| Extra | Selected when |
|---|---|
| `hw-ort-cuda` | x64 with an NVIDIA GPU and a CUDA driver |
| `hw-ort-directml` | Windows with an AMD or Intel GPU |
| `hw-ort-qnn` | Windows ARM64 with a Qualcomm NPU |
| `hw-ort-cpu` | everything else |

Install it, then confirm what resolution produced:

```bash
backend/.venv/bin/awf-setup --install --verify
```

`--verify` reports the installed ONNX Runtime distribution and version, its available execution providers, and `pip check`. On any host with a non-CPU extra, `pip check` reports that `kokoro-onnx`, `openwakeword`, and `faster-whisper` require `onnxruntime` — expected, since those packages name the base distribution and have no way to express that an accelerator build satisfies it. `--verify` distinguishes that from a real failure.

### 4. Bootstrap local state

```bash
backend/.venv/bin/awf-setup
```

With no flags this generates `.env` with a fresh secret key, creates `cache/sandbox/`, and creates `data/awf_db/awf.db`.

### 5. Acquire the speech models

```bash
backend/.venv/bin/awf-speech models sync
backend/.venv/bin/awf-speech models verify
```

`sync` downloads the artifacts named in `config/voice/{stt,tts,vad,wake}.yaml` into `models/`, and warms the STT model for the host's resolved device. It is idempotent — a second run changes nothing. `verify` reports each expected artifact as `OK` or `MISSING`.

### 6. Validate

```bash
backend/.venv/bin/python scripts/validate_backend.py profile
backend/.venv/bin/python scripts/validate_backend.py ci
```

`profile` writes a timestamped report to `reports/diagnostics/` naming the resolved hardware profile, the preflight tokens, and the per-function readiness results. `ci` runs everything except the tests marked `live`.

### 7. Frontends

```bash
npm --prefix frontend install
npm --prefix frontend test
npm --prefix frontend run build
```

## Validation commands

```bash
backend/.venv/bin/python scripts/validate_backend.py profile
backend/.venv/bin/python scripts/validate_backend.py unit
backend/.venv/bin/python scripts/validate_backend.py integration
backend/.venv/bin/python scripts/validate_backend.py runtime
backend/.venv/bin/python scripts/validate_backend.py regression
backend/.venv/bin/python scripts/validate_backend.py ci
```

Exit codes: `0` pass, `1` fail, `2` skipped, `3` environment unsatisfied. `runtime` runs only the tests marked `live`, which need real hardware and the acquired models; it returns `2` when the host cannot satisfy them.

`profile` and `regression` each write a timestamped report under `reports/`.

## Running AWF

```bash
backend/.venv/bin/awf registry list --kind workflows
backend/.venv/bin/awf run start --workflow <name@version> --input '{}'
backend/.venv/bin/awf run status --run-id <run-id>
backend/.venv/bin/awf approval list
```

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

Speech models missing:

```bash
backend/.venv/bin/awf-speech models verify
backend/.venv/bin/awf-speech models sync
```

Accelerator detected but not selected — run `profile` and read the readiness reasons; each names the hardware fact and the runtime token it required:

```bash
backend/.venv/bin/python scripts/validate_backend.py profile
```

STT and TTS resolve their devices independently. STT runs on CTranslate2 and asks it directly for CUDA devices; TTS runs on ONNX Runtime and needs the matching execution provider. One reaching `cuda` while the other stays on `cpu` is a normal outcome, not an error.
