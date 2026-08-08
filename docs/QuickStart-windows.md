# Quick Start — Windows

Sets up JARVIS-AWF on Windows x64 or ARM64. Run every command from PowerShell at the repository root. Do not install this project's Python packages globally.

## Prerequisites

- Windows PowerShell and Git
- Python `>=3.12,<3.15` through the Windows `py` launcher
- Node.js 26+ and npm, for the frontends
- Internet access for dependency and model acquisition

Optional, for accelerated speech: an NVIDIA GPU with a working driver (x64), an AMD or Intel GPU for DirectML, or a Qualcomm NPU on ARM64. CPU is the guaranteed floor on every host.

## Clone

```powershell
git clone https://github.com/bentman/JARVIS-AWF.git
Set-Location .\JARVIS-AWF
```

For an existing clone:

```powershell
Set-Location <REPO_ROOT_PATH>
git pull
```

## Setup sequence

```text
create venv -> install -> provision -> bootstrap -> acquire models -> validate
```

### 1. Create the backend environment

```powershell
py -3.12 -m venv backend\.venv
.\backend\.venv\Scripts\python -m pip install --upgrade pip
```

Python 3.13 or 3.14 work as well. Use `.\backend\.venv\Scripts\python` for every command below; the project is never installed into a system interpreter.

### 2. Install the base package

```powershell
.\backend\.venv\Scripts\python -m pip install -e ".[dev]"
```

This installs the core, the four console scripts (`awf`, `awf-setup`, `awf-secret`, `awf-speech`), and the test dependencies. The ONNX Runtime build is not part of the base set — the next step selects it.

### 3. Provision the hardware-appropriate ONNX Runtime

```powershell
.\backend\.venv\Scripts\awf-setup --provision
```

This probes the host and names one extra without installing anything:

| Extra | Selected when |
|---|---|
| `hw-ort-cuda` | x64 with an NVIDIA GPU and a CUDA driver |
| `hw-ort-directml` | Windows with an AMD or Intel GPU |
| `hw-ort-qnn` | Windows ARM64 with a Qualcomm NPU |
| `hw-ort-cpu` | everything else |

Install it, then confirm what resolution produced:

```powershell
.\backend\.venv\Scripts\awf-setup --install --verify
```

`--verify` reports the installed ONNX Runtime distribution and version, its available execution providers, and `pip check`. On any host with a non-CPU extra, `pip check` reports that `kokoro-onnx`, `openwakeword`, and `faster-whisper` require `onnxruntime` — expected, since those packages name the base distribution and have no way to express that an accelerator build satisfies it. `--verify` distinguishes that from a real failure.

### 4. Bootstrap local state

```powershell
.\backend\.venv\Scripts\awf-setup
```

With no flags this generates `.env` with a fresh secret key, creates `cache\sandbox\`, and creates `data\awf_db\awf.db`.

### 5. Acquire the speech models

```powershell
.\backend\.venv\Scripts\awf-speech models sync
.\backend\.venv\Scripts\awf-speech models verify
```

`sync` downloads the artifacts named in `config\voice\{stt,tts,vad,wake}.yaml` into `models\`, and warms the STT model for the host's resolved device. It is idempotent — a second run changes nothing. `verify` reports each expected artifact as `OK` or `MISSING`.

### 6. Validate

```powershell
.\backend\.venv\Scripts\python scripts\validate_backend.py profile
.\backend\.venv\Scripts\python scripts\validate_backend.py ci
```

`profile` writes a timestamped report to `reports\diagnostics\` naming the resolved hardware profile, the preflight tokens, and the per-function readiness results. `ci` runs everything except the tests marked `live`.

### 7. Frontends

```powershell
npm --prefix frontend install
npm --prefix frontend test
npm --prefix frontend run build
```

## Validation commands

```powershell
.\backend\.venv\Scripts\python scripts\validate_backend.py profile
.\backend\.venv\Scripts\python scripts\validate_backend.py unit
.\backend\.venv\Scripts\python scripts\validate_backend.py integration
.\backend\.venv\Scripts\python scripts\validate_backend.py runtime
.\backend\.venv\Scripts\python scripts\validate_backend.py regression
.\backend\.venv\Scripts\python scripts\validate_backend.py ci
```

Exit codes: `0` pass, `1` fail, `2` skipped, `3` environment unsatisfied. `runtime` runs only the tests marked `live`, which need real hardware and the acquired models; it returns `2` when the host cannot satisfy them.

`profile` and `regression` each write a timestamped report under `reports\`.

## Running AWF

```powershell
.\backend\.venv\Scripts\awf registry list --kind workflows
.\backend\.venv\Scripts\awf run start --workflow <name@version> --input '{}'
.\backend\.venv\Scripts\awf run status --run-id <run-id>
.\backend\.venv\Scripts\awf approval list
```

Store a provider API key by name, so it never appears in a registry file:

```powershell
.\backend\.venv\Scripts\awf-secret set OPENAI_API_KEY
```

A voice round trip takes a pre-recorded wake file and command file, and writes a spoken response:

```powershell
.\backend\.venv\Scripts\awf-speech round-trip <wake.wav> <command.wav> --response-audio-out <out.wav>
```

Omitting `--voice-id` uses the `narrator` Voice Profile's voice. Any other voice remains selectable by passing the flag.

## ARM64 notes

An ARM64 host selects `hw-ort-qnn`, which installs `onnxruntime-qnn` alongside the base `onnxruntime`. The two provide different import names and coexist; the profiler registers the QNN provider library at probe time.

Speech-to-text runs on CTranslate2, whose devices are CPU and CUDA only, so STT stays on CPU on ARM64 regardless of NPU availability. Text-to-speech and the wake word run on ONNX Runtime and can reach the QNN provider when it loads. `profile` reports which of them did.

## Repository rules that matter

- `pyproject.toml` is the only place Python dependencies are declared.
- Install through `awf-setup --install` rather than by hand, so the ONNX Runtime distribution stays consistent with the host.
- `models\`, `data\`, `cache\`, and `reports\` are local state and stay out of commits.
- Record validation claims with the command output that produced them.

## Common diagnostics

Python version rejected — install 3.12, 3.13, or 3.14 and recreate `backend\.venv`.

Wrong ONNX Runtime installed, or providers missing:

```powershell
.\backend\.venv\Scripts\awf-setup --provision
.\backend\.venv\Scripts\awf-setup --install --verify
```

Speech models missing:

```powershell
.\backend\.venv\Scripts\awf-speech models verify
.\backend\.venv\Scripts\awf-speech models sync
```

Accelerator detected but not selected — run `profile` and read the readiness reasons; each names the hardware fact and the runtime token it required:

```powershell
.\backend\.venv\Scripts\python scripts\validate_backend.py profile
```

STT and TTS resolve their devices independently. STT runs on CTranslate2 and asks it directly for CUDA devices; TTS runs on ONNX Runtime and needs the matching execution provider. One reaching `cuda` while the other stays on `cpu` is a normal outcome, not an error.
