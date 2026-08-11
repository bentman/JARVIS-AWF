# ADR-0008: profile, provision, preflight, readiness

## Status

Implemented.

Separately, `scripts/validate_backend.py`'s `profile` command called
`resolve_hardware_profile_id()` with no arguments — a stale call site missed
when this ADR added the required `repo_root` parameter to that function's
signature (every other call site, including this module's own
`run_hardware_profiler` and the integration tests, was updated). Fixed to
pass the script's own `REPO_ROOT`; it now resolves `linux-x64-cuda` on this
host with full inventory/tokens/readiness evidence, consistent with this
ADR's acceptance criteria above.

A later validation pass found four residual gaps against the "single source
of truth" and test-coverage claims below, all fixed:
`backend/src/awf/adapters/codex_cli.py` still derived the repo root by
counting path parents, uncounted by this ADR's own baseline — repointed at
`awf.paths.REPO_ROOT`; `server/stdio.py` and `cli/core_ops.py` each
hardcoded `data/awf_db/awf.db` instead of calling `awf.paths.db_path()` —
repointed at it; `HardwareInventory`'s docstring still described the
pre-ADR design where the profile ID came from execution-provider
verification — reworded to describe the readiness roll-up; and
`test_hardware_readiness.py`'s directml/qualcomm/no-accelerator cases were
not parametrized across both architectures as Scope item 10 states, though
`readiness.py` never reads `inventory.arch` — parametrization added for
literal coverage.

A later operator bootstrap pass found the speech dependency surface was still
too coarse for the supported host classes. `faster-whisper`/CTranslate2 has
no Windows ARM64 wheel, while Linux OpenWakeWord's metadata can require a
`tflite-runtime` wheel that is not available even though OpenWakeWord works
through its ONNX path. Provisioning now selects `speech` and `wake-word`
alongside the `hw-ort-*` extra. On Linux, `awf-setup --install` installs the
editable project without dependencies, installs every selected requirement
except OpenWakeWord normally, including OpenWakeWord's usable sibling
dependencies (`requests`, `scikit-learn`, `scipy`), then installs
`openwakeword==0.6.0` with `--no-deps`; `awf-setup --verify` waives only the
known `tflite-runtime` metadata line when `openwakeword` and `onnxruntime`
actually import. STT
readiness accepts the ONNX STT runtimes for the CPU floor, with Faster
Whisper reserved for CUDA when CTranslate2 reports devices.

A later ARM64 cross-host pass found the QNN provisioning rule was still
Windows-shaped even though the resolver is intended to be host-symmetric.
Windows ARM64 still selects `hw-ort-qnn` from a Qualcomm NPU inventory fact.
Linux ARM64 now selects `hw-ort-qnn` as a host-class candidate so the QNN
package family is present before preflight tries to prove the provider.
Linux/WSL inventory remains Linux-native: it does not query Windows CIM/PnP
through interop. QNN runtime use is still gated by readiness tokens
(`ep:QNNExecutionProvider` and `dll:QnnHtp`), so a Linux host may install the
QNN packages while speech continues to select CPU until the runtime actually
proves available. Adreno/OpenCL is treated as a separate ARM64 GPU path and
is reported only from Linux-visible OpenCL/sysfs evidence.

## Context

`pyproject.toml` declares `onnxruntime>=1.28` among the base dependencies.
`onnxruntime`, `onnxruntime-gpu`, and `onnxruntime-directml` are separate
PyPI distributions that all provide the same `onnxruntime` import name, so
exactly one of the three can be installed in an environment. The declared
distribution publishes the CPU execution provider. `onnxruntime-qnn`
provides a distinct `onnxruntime_qnn` import name and installs alongside
`onnxruntime`, which is what `profiler.activate_qnn_execution_provider`
already assumes: it imports `onnxruntime_qnn`, locates that package's
provider library, and registers the library into `onnxruntime`.

`hardware/profiler.py` decides the canonical profile ID inside
`_probe_evidence`, which sets `cuda_verified`, `gpu_verified`, and
`qnn_verified` from `onnxruntime.get_available_providers()` plus a session
construction against the named provider. `collect_inventory()` already
gathers `gpu_vendor`, `gpu_available`, `cuda_available`, `cuda_version`,
`npu_available`, and `npu_vendor` from `nvidia-smi`, `nvcc`, Windows CIM, and
Linux DRM sysfs. `_probe_evidence` reads one inventory field,
`gpu_vendor`, and only for the arm64 OpenCL branch; `cuda_available` and
`npu_vendor` reach the event payload and no decision.

Together those two facts determine the outcome on every host: with the
declared dependency set, `CUDAExecutionProvider`, `DmlExecutionProvider`, and
`QNNExecutionProvider` are absent from `get_available_providers()`,
`_verify_provider_loads` returns `False` for each, and
`resolve_hardware_profile_id()` returns a `*-cpu` profile. A host with an
NVIDIA GPU and a working CUDA driver produces the same profile ID as a host
with no GPU, and the two are indistinguishable from `cuda_verified: False`.

One profile ID currently serves all four speech functions.
`speech/models.stt_runtime` keys `config/voice/stt.yaml`'s `classes` by the
final segment of that ID. The three other adapters take no execution
provider: `tts_kokoro.synthesize` constructs `Kokoro(model_path,
voices_path)`, `vad_silero.speech_probabilities` constructs
`ort.InferenceSession(str(model_path))`, and
`wake_openwakeword.detect_wake_word` constructs `Model(...)` with artifact
paths.

STT does not run on ONNX Runtime. `stt_whisper.transcribe` constructs
`faster_whisper.WhisperModel`, which runs on CTranslate2, whose devices are
`cpu` and `cuda` and whose CUDA availability is reported by
`ctranslate2.get_cuda_device_count()`. An ONNX Runtime execution-provider
probe answers a different question than the one STT device selection asks.

`vad_silero.speech_probabilities` feeds the input names `input`, `sr`, `h`,
and `c`. `pyproject.toml` declares `silero-vad>=6`, and
`speech/models.sync_models` copies the ONNX artifact bundled in whichever
version of that distribution is installed. Whether the artifact and the
adapter agree on input names is a property of the installed artifact.

`kokoro-onnx` and `openwakeword` declare their own runtime dependencies, so
which ONNX Runtime distribution survives an install is determined by
resolution across all declared requirements rather than by the project's
direct dependency alone.

`awf-setup` creates the directory skeleton, `.env`, and the database. No
command installs a hardware-specific dependency set.

## Decision

Four stages, each with one input, one output, and one module.

| Stage | Module | Input | Output |
|---|---|---|---|
| Profile | `hardware/profiler.py` | host probes | `HardwareInventory` — hardware facts only |
| Provision | `hardware/provisioning.py` | `HardwareInventory` | exactly one `hw-ort-*` extra |
| Preflight | `hardware/preflight.py` | the installed environment | tokens |
| Readiness | `hardware/readiness.py` | inventory + tokens | `(device, ready, reason)` per function |

**The profile stage stops probing execution providers.** `collect_inventory`
is its whole output. `_probe_evidence` and its `cuda_verified` /
`gpu_verified` / `qnn_verified` keys are replaced by preflight tokens.

**The ONNX Runtime distribution moves from base dependencies to extras**, one
extra per mutually exclusive wheel, selected by the provision stage from
inventory facts.

**Device selection is per function.** Four readiness functions replace the
single suffix as the selector. Each returns the device, whether the function
can run, and the reason that decision was reached.

**The canonical profile ID remains, as a summary.** It is the strongest
device any function's readiness selected, mapped onto the Section 16.4 enum,
and it keeps the `*64-cpu` floor. It is written to the `events` table with
the inventory, the tokens, and the four readiness results.

**Evidence must agree.** A device above `cpu` is selected only when the
hardware fact and the runtime token both say so; either alone resolves to
`cpu` with a reason naming what was missing.

## Rationale

`cuda_verified: False` previously meant "ONNX Runtime cannot use CUDA" and
was read as "this host has no CUDA." Separating the
stages makes the two statements separate values: `inventory.cuda_available`
answers the first, `ep:CUDAExecutionProvider` answers the second, and their
conjunction is what selects a device. AGENTS.md's Platform Contract requires
every hardware claim to come from a capability probe; a probe of the
installed wheel is a claim about the wheel.

The four functions run on three different runtimes — CTranslate2 for STT,
ONNX Runtime for TTS and VAD, openWakeWord's own loader for wake. One device
string cannot describe them, and a host where STT runs on CUDA while TTS runs
on CPU is an ordinary outcome rather than an error.

Extras follow from the wheels: since one import name is provided by three
distributions, the choice must be made before installation, from facts the
profile stage already collects.

## Deviation recorded

| Requirement | Deviation | Compensating control |
|---|---|---|
| Section 16.4: the Hardware Profiler "resolves the host to exactly one profile ID", and the execution provider is chosen from it | one profile ID is still resolved and recorded; the execution provider each function uses comes from that function's readiness result | the profile ID is computed from the readiness results, so it names the strongest device actually selected, and the `*64-cpu` floor and the "valid only when the execution provider actually loads" rule both hold through the token requirement |
| Section 16.4: "A profile above `-cpu` is valid only when the Profiler verifies its execution provider actually loads" | the verification additionally requires the corresponding hardware fact from the inventory | strictly narrower than the stated rule: every profile it grants also satisfies the original |
| Section 16.4's "verifies its execution provider actually loads": a prior version of this design verified this by constructing an ONNX Runtime session per candidate provider | `ep:<provider>` reads `onnxruntime.get_available_providers()` only; no session is constructed in `preflight` or `readiness` | on a host with `onnxruntime-gpu` installed alongside a CUDA 13.x toolchain (arriving transitively through `torch`, `silero-vad`'s own dependency), constructing a `CUDAExecutionProvider` session crashed the process - a native ABI mismatch, not a Python exception, uncatchable by any `try`/`except` in this codebase. Provider availability plus the corresponding hardware fact is what selects a device; the provider's own library loading its actual backend happens at first real use, by the adapter that made the call, which reports its own failure rather than the profiler's |

Installation gains a hardware-selected extra. Section 16.4's hardware-aware
acquisition step governs model artifacts; package selection is a new,
adjacent step and contradicts no stated requirement.

## Mechanism

### Part A — provision

`pyproject.toml`, base dependencies with `onnxruntime` removed, plus:

```toml
[project.optional-dependencies]
dev = ["pytest>=8"]
hw-ort-cpu = ["onnxruntime>=1.28"]
hw-ort-cuda = ["onnxruntime-gpu>=1.28"]
hw-ort-directml = ["onnxruntime-directml>=1.28; sys_platform=='win32'"]
hw-ort-qnn = [
  "onnxruntime>=1.28; ((platform_machine=='ARM64' or platform_machine=='arm64') and sys_platform=='win32') or ((platform_machine=='aarch64' or platform_machine=='arm64') and sys_platform=='linux')",
  "onnxruntime-qnn>=2.3; ((platform_machine=='ARM64' or platform_machine=='arm64') and sys_platform=='win32') or ((platform_machine=='aarch64' or platform_machine=='arm64') and sys_platform=='linux')",
]
```

`hardware/provisioning.py`:

```python
ORT_EXTRAS = ("hw-ort-cpu", "hw-ort-cuda", "hw-ort-directml", "hw-ort-qnn")

resolve_ort_extra(inventory) -> str     # exactly one
explain_ort_extra(inventory) -> tuple[str, str]   # (extra, reason)
```

Selection, in order, first match wins:

| Condition on `HardwareInventory` | Extra |
|---|---|
| `arch == "x64"` and `gpu_vendor == "nvidia"` and `cuda_available` | `hw-ort-cuda` |
| `os_name == "linux"` and `arch == "arm64"` | `hw-ort-qnn` |
| `os_name == "windows"` and `arch == "arm64"` and `npu_vendor == "qualcomm"` | `hw-ort-qnn` |
| `os_name == "windows"` and `gpu_available` and `gpu_vendor in {"amd", "intel"}` | `hw-ort-directml` |
| otherwise | `hw-ort-cpu` |

`awf-setup` gains `--provision`, which prints the selected extra, its reason,
and the `pip install -e .[<extra>,dev]` command; `--install` runs it; and
`--verify` reports the installed ONNX Runtime distribution name and version
from `importlib.metadata`, `onnxruntime.get_available_providers()`, and the
result of `python -m pip check`. Verification is a report of what resolution
produced, since other declared requirements participate in it.

The selected install command includes speech and wake by default:
`pip install -e .[<hw-ort-extra>,speech,wake-word,dev]`. Linux installation
uses a split sequence for OpenWakeWord: install the editable project with
`--no-deps`, install all selected requirements except OpenWakeWord normally,
then install OpenWakeWord with `--no-deps`. This matches the sibling
JARVISv7 host-class approach and avoids the unavailable Linux
`tflite-runtime` metadata dependency while still requiring the actual
`openwakeword` import at readiness time.

Re-running with an unchanged inventory selects the same extra and installs
nothing new.

### Part B — preflight

`hardware/preflight.py` produces a sorted token list from the installed
environment. Tokens are the only value readiness consumes.

| Token | Meaning |
|---|---|
| `import:<module>` / `import:<module>:MISSING` | one per module in `onnxruntime`, `ctranslate2`, `faster_whisper`, `kokoro_onnx`, `openwakeword`, `silero_vad` |
| `ep:<provider>` | one per entry in `onnxruntime.get_available_providers()`, plus QNN plugin EP success from `onnxruntime.get_ep_devices()` after registration |
| `ep_device:<provider>` | one per plugin EP device name from `onnxruntime.get_ep_devices()` after QNN activation |
| `dll:QnnHtp` / `dll:QnnHtp:MISSING` | `resolve_qnn_backend_path()` result |
| `qnn:provider_library:<path>` | QNN EP plugin path discovered from `onnxruntime_qnn` |
| `qnn:backend_path:<path>` | QNN HTP backend path discovered from `onnxruntime_qnn`, `onnxruntime`, or `QAIRT_SDK_PATH` |
| `qnn:provider_library_registered` | QNN EP registration succeeded before provider enumeration; Linux does not manually preload QNN DSP-side shared libraries |
| `qnn:provider_activation_error:<reason>` | QNN EP registration failed before provider enumeration |
| `opencl:adreno` | a Qualcomm/Adreno OpenCL platform is visible, or an OpenCL platform exists while inventory reports `gpu_vendor == "qualcomm"` |
| `ct2:cuda:<n>` | `ctranslate2.get_cuda_device_count()` |

`ep:` is a list read: `onnxruntime.get_available_providers()` and nothing
else. No token here constructs an ONNX Runtime session. A provider that is
merely available but whose native backend is absent or mismatched (missing
CUDA/cuDNN, a driver too old, an incompatible build) is not distinguished
from one that fully works - that distinction is left to the provider's own
library at first real use, by the adapter that made the call, which reports
its own failure. See Deviation recorded.

`GPU_PROVIDER_CANDIDATES` and `_verify_gpu_provider` are deleted rather than
moved. Their `linux-x64` entries name `ROCMExecutionProvider`,
`MIGraphXExecutionProvider`, and `OpenVINOExecutionProvider`, and no
`hw-ort-*` extra installs a distribution that offers any of them, so the
table can no longer match a provisioned host. The arm64 `-gpu` path does not
depend on it: that path resolves through `opencl:adreno`, a ctypes probe of
OpenCL platform enumeration, not through an execution provider.

`activate_qnn_execution_provider`, `resolve_qnn_backend_path`, and
`_opencl_platform_count` move from `profiler.py` into this module unchanged.
QNN provider-library registration builds no session - it loads a library
into ONNX Runtime's own registry, which carries none of session
construction's native-crash risk. Results are cached per process alongside
the inventory cache, and `reset_preflight_cache()` clears them.

### Part C — readiness

`hardware/readiness.py`, one function per speech function, each returning
`Readiness(device, ready, reason)`:

```python
derive_stt_readiness(inventory, tokens) -> Readiness
derive_tts_readiness(inventory, tokens) -> Readiness
derive_vad_readiness(inventory, tokens, artifact_path) -> Readiness
derive_wake_readiness(inventory, tokens, artifact_paths) -> Readiness
```

**STT** — `cuda` when `gpu_vendor == "nvidia"` and `cuda_available` and
`ct2:cuda:<n>` with `n > 0`; otherwise `cpu`. CUDA ready requires
`import:faster_whisper`; the CPU floor is ready when an ONNX STT runtime such
as `onnx_asr` or `sherpa_onnx` is importable. This keeps Windows ARM64 and
CPU-only hosts usable without the CTranslate2 wheel.

**TTS** — `cuda` when `gpu_vendor == "nvidia"` and `cuda_available` and
`ep:CUDAExecutionProvider`; else `directml` when `os_name == "windows"`
and `gpu_available` and `ep:DmlExecutionProvider`; else `qnn` when
`npu_vendor == "qualcomm"` and `ep:QNNExecutionProvider` and
`dll:QnnHtp`; else `cpu`. Ready requires `import:kokoro_onnx`.

**VAD** — `cpu`. Ready requires `import:onnxruntime`, the artifact present,
and the artifact's session input names to cover the names the adapter feeds
(`input`, `sr`, `h`, `c`); a mismatch is `ready=False` with a reason naming
the input names found. Silero VAD is a ~2 MB model; no accelerator branch is
built for it.

**Wake** — `cpu`. Ready requires `import:openwakeword` and all three
artifacts present. The wake adapter selects no execution provider.

`hardware/profiler.py` resolves the profile ID from these results:

```
suffix = qnn   if any readiness device == "qnn"
         cuda  elif any readiness device == "cuda"
         gpu   elif any readiness device == "directml", or opencl:adreno present
         cpu   otherwise
```

VAD and wake readiness need artifact paths, so the profiler needs a
repository root:

```python
run_hardware_profiler(conn, *, repo_root: Path | None = None, refresh: bool = False) -> str
```

`repo_root` defaults to `awf.paths.REPO_ROOT`. This is not a signature change
for existing callers: `refresh` is already keyword-only with a default, and
`repo_root` is added the same way. `speech/pipeline.run_voice_round_trip`
passes the `repo_root` it already holds; `workflow/activities._hardware_probe`
passes nothing. The reason code, the `profile_id` payload key, and the
sentinel Run anchoring are unchanged; the payload carries `inventory`,
`tokens`, and all four `readiness` results in place of `evidence`.

### Part D — one repository root

The repository root is currently derived in five places, at four different
depths: `cli/main.py` and `speech/cli.py` at `parents[4]`, `setup.py` at
`parents[3]`, `scripts/validate_backend.py` at `parents[1]`, and
`backend/tests/conftest.py` at `parents[2]`.

`awf/paths.py` holds one definition:

```python
REPO_ROOT: Path                            # derived once from this module's location
db_path(repo_root) -> Path                 # data/awf_db/awf.db
models_dir(repo_root, function) -> Path    # models/<function>
```

`cli/main.py`, `secrets/cli.py`, `speech/cli.py`, and `setup.py` take their
root and their database path from it, and their local `_repo_root` and
`_db_path` helpers are removed. `scripts/validate_backend.py` and
`backend/tests/conftest.py` keep deriving their own: both must work before
the package is importable. The net change is four derivations removed.

`artifact_paths` moves from `speech/models.py` into
`registry/hardware_voice_manifest.py`, which already owns the manifest and
its loader; `speech/models.py` calls it there. VAD and wake readiness reach
artifact paths through `registry/`, so `hardware/` imports `registry/` and
never `speech/`.

### Part E — adapters

`stt_whisper.transcribe` already takes `device` and `compute_type`;
`speech/models.stt_runtime(repo_root, device)` selects the
`config/voice/stt.yaml` class by the STT readiness device rather than by the
profile suffix. The manifest's existing `cpu` and `cuda` class keys are
unchanged.

`tts_kokoro.synthesize` gains a `device` parameter. For `cpu` it constructs
`Kokoro(model_path, voices_path)` as it does now; otherwise it constructs
`ort.InferenceSession(model_path, providers=[<provider>, "CPUExecutionProvider"])`
and `Kokoro.from_session(session, voices_path)`.

`vad_silero` and `wake_openwakeword` are unchanged.

`speech/pipeline.run_voice_round_trip` resolves readiness once, passes each
function its device, and writes the readiness results alongside the existing
`pinned_model_verification` event.

## Layout delta

```text
backend/src/awf/
  paths.py           (new: REPO_ROOT, db_path, models_dir)
  hardware/
    profiler.py      (inventory + profile ID from readiness; repo_root parameter)
    provisioning.py  (new)
    preflight.py     (new)
    readiness.py     (new)
    gpu_sampler.py
  registry/
    hardware_voice_manifest.py   (gains artifact_paths)
  speech/
    models.py        (stt class by readiness device; artifact_paths re-exported from registry)
    pipeline.py      (resolves readiness once, passes devices and repo_root)
    tts_kokoro.py    (device parameter)
    cli.py           (root and db path from paths.py)
  cli/main.py        (root and db path from paths.py)
  secrets/cli.py     (db path from paths.py)
  setup.py           (root from paths.py; --provision/--install/--verify)

pyproject.toml       (onnxruntime moves to hw-ort-* extras)
```

## The tradeoffs accepted

- A bare `pip install -e .` installs no ONNX Runtime.
  `awf-setup --provision --install` is the single command that completes an
  environment, and `--verify` reports what resolution actually produced.
- The three distributions providing the `onnxruntime` import name are
  mutually exclusive, so changing accelerators is an uninstall and
  reinstall. The resolver names exactly one extra per host, so which one is
  intended is never ambiguous.
- Requiring both a hardware fact and a runtime token means a host whose
  vendor tooling is absent resolves to `cpu` while its accelerator sits idle.
  The reason string names the missing side, which is the input to fixing it.
- Four readiness results are more state than one profile ID. The profile ID
  survives as their summary, so existing consumers and the event payload key
  keep working.
- `hw-ort-cuda` carries no platform marker. Whether that wheel exists for a
  given platform is reported by `--verify` on the host rather than asserted
  in advance.

## Scope for implementation

1. Add `awf/paths.py`; repoint `cli/main.py`, `secrets/cli.py`,
   `speech/cli.py`, and `setup.py` at it; delete their local `_repo_root` and
   `_db_path` helpers.
2. Move `artifact_paths` from `speech/models.py` to
   `registry/hardware_voice_manifest.py`; have `speech/models.py` call it
   there.
3. Add `hardware/preflight.py`; move `activate_qnn_execution_provider`,
   `resolve_qnn_backend_path`, and `_opencl_platform_count` into it; add the
   token set and the cache. Delete `GPU_PROVIDER_CANDIDATES` and
   `_verify_gpu_provider`.
4. Add `hardware/readiness.py` with the four functions.
5. Add `hardware/provisioning.py` with `resolve_ort_extra` and
   `explain_ort_extra`.
6. Move `onnxruntime` out of base dependencies into the four `hw-ort-*`
   extras.
7. Add `--provision`, `--install`, and `--verify` to `awf-setup`.
8. Remove `_probe_evidence` from `profiler.py`; add the keyword-only
   `repo_root` parameter to `run_hardware_profiler`; resolve the profile ID
   from readiness; carry `inventory`, `tokens`, and all four `readiness`
   results in the `hardware_profile_resolved` payload.
9. Give `tts_kokoro.synthesize` a `device` parameter; key
   `speech/models.stt_runtime` by the STT readiness device; resolve readiness
   once in `speech/pipeline.run_voice_round_trip`, passing its `repo_root`
   to `run_hardware_profiler`.
10. Update `test_phase12_hardware_profiler.py` for the new payload and
    resolution path; add unit tests driving all four readiness functions over
    synthesized inventory and token inputs, covering nvidia, amd, intel,
    qualcomm, and no accelerator, on both architectures.
11. Run all six `scripts/validate_backend.py` commands, and
    `awf-setup --provision --verify`.

## Acceptance

- `resolve_ort_extra` returns exactly one extra for every synthesized
  inventory, and the same extra for the same inventory.
- On this host, `awf-setup --provision` names the extra and reason;
  `--install` applies it; a second `--install` changes nothing; `--verify`
  reports the installed ONNX Runtime distribution name, its version,
  `get_available_providers()`, and a passing `pip check`.
- With `hw-ort-cpu` installed on a host whose inventory reports
  `gpu_vendor: nvidia` and `cuda_available: true`, STT readiness is `cuda`
  and TTS readiness is `cpu`, each with a reason. This is the case the fused
  design could not express.
- With `hw-ort-cuda` installed on that host, both are `cuda`, and the
  resolved profile ID ends in `-cuda`.
- On a host with no accelerator, every readiness device is `cpu`, every
  reason is non-empty, and the profile ID ends in `-cpu`.
- VAD readiness reports `ready=False` with a reason naming the artifact's
  input names when they do not cover `input`, `sr`, `h`, `c`.
- The `hardware_profile_resolved` payload carries `profile_id`, `inventory`,
  `tokens`, and all four `readiness` results, and `ct2:cuda:<n>` appears
  among the tokens.
- No `preflight` or `readiness` function constructs an ONNX Runtime session.
- `workflow/activities._hardware_probe` calls `run_hardware_profiler(conn)`
  with no additional arguments and still produces the four readiness results.
- No module under `backend/src/awf/` derives the repository root by counting
  path parents except `awf/paths.py`, and no module there spells
  `data/awf_db/awf.db` except `awf/paths.py`.
- No module under `backend/src/awf/hardware/` imports from
  `backend/src/awf/speech/`.
- The voice round trip runs end to end and records the four readiness
  results.
- `pytest backend/tests` matches or exceeds the pre-change pass count with
  the same or fewer skips.

## Consequences

- A hardware fact and a runtime capability are separate recorded values, so
  an unused accelerator is distinguishable from an absent one.
- Each speech function runs on the device its own runtime can reach.
- The profile ID above `*-cpu` becomes reachable, since the accelerator
  wheels are installable through a named extra.
- Installing the project is a two-step operation: install, then provision.
- The event record carries the full chain — facts, tokens, per-function
  decisions, and the summary ID — so a later reader can see which stage
  produced a given outcome.
