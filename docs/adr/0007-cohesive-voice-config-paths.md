# ADR-0007: one voice manifest per function, with model selection keyed to the hardware profile

## Status

Implemented. Amended in part by ADR-0008 and ADR-0016.

Alignment update, 2026-08-14: the four voice manifests remain one object per
function, but they now use the registry layout:
`config/app_registry/hardware-voice-manifests/{stt,tts,vad,wake}/1.0.0.yaml`
with operator overrides under
`data/registry/hardware-voice-manifests/{name}/{version}.yaml`. The obsolete
`config/voice/` directory was removed. References below to `config/voice/*.yaml`
record the historical ADR-0007 implementation shape, not the active path.

## Amended by ADR-0016

`sync_models` no longer leaves artifacts that a current manifest does not
select. After all requested acquisitions succeed, it reconciles each
config-owned `models/<function>/` directory and reports every removal. The
manifest remains the sole authority for retained artifacts.

## Amended by ADR-0008

ADR-0008 made device selection per speech function, so the STT class key comes
from a readiness result rather than from the profile ID's final segment.
Everything not listed stands, including the four-file manifest shape, the
artifact sourcing, the `stt.yaml` class entries, the wake three-artifact load,
and the `silero-vad` declaration.

| Stated here | Current |
|---|---|
| resolution keys on the final segment of the canonical profile ID (Decision; Rationale) | keys on `hardware.readiness.derive_stt_readiness(...).device` |
| `ACCELERATION_CLASSES` and `acceleration_class(profile_id)` in `speech/models.py` (Part B) | not present. STT resolves `cpu` or `cuda`, the two devices CTranslate2 offers |
| `artifact_paths` in `speech/models.py` (Part B; Part C) | lives in `registry/hardware_voice_manifest.py`; `speech/models.py` calls it there, so `hardware/` imports `registry/` and never `speech/` |
| `stt_runtime(repo_root, profile_id)`, `sync_models(repo_root, profile_id)`, `verify_models(repo_root, profile_id)` (Part B) | `stt_runtime(repo_root, device)`, `sync_models(repo_root, stt_device)`, `verify_models(repo_root)` |
| TTS, VAD, and wake vary by neither artifact nor device (Context; Rationale) | artifacts still do not vary. TTS device varies through `derive_tts_readiness`, and `tts_kokoro.synthesize` takes a `device` parameter |
| Acceptance: a `-cuda` profile resolves STT to the turbo model; all twelve profile IDs resolve to an `SttRuntime` | an STT readiness device of `cuda` resolves to `deepdml/faster-whisper-large-v3-turbo-ct2` with `device=cuda`, `compute_type=float16`; any other device resolves to `small` with `device=cpu`, `compute_type=int8` |
| `pip install -e .[dev]` (Scope step 7) | `pip install -e .[dev,<hw-ort-extra>]`; ONNX Runtime is a hardware extra, named for the host by `awf-setup --provision` |

## Context

`config/voice/{stt,tts,vad,wake}/` holds 48 manifests — one per canonical
profile ID per function. Their content:

| Function | Distinct payloads across the 12 profiles |
|---|---|
| `tts` | 1 (all twelve byte-identical) |
| `vad` | 1 (all twelve byte-identical) |
| `wake` | 1 (all twelve byte-identical) |
| `stt` | 3 (`small` on eight cpu/gpu profiles, `large-v3-turbo` on two cuda, `fallback_to` stub on two qnn) |

Six payloads occupy 48 files.

The parsed schema carries `acquisition`, `target_relative_path`, `sha256`,
`url`, `repo_id`, `revision`, `package`, and `notes`. `verify_pinned_files`
reads `target_relative_path` and `sha256`. `acquisition` is checked against an
enum. `url`, `repo_id`, `revision`, `package`, and `notes` have no reader, and
no command in the repository acquires an artifact.

Model file paths are literals in two places: `speech/cli.py` passes
`models/wake/hey_jarvis_v0.1.onnx`, `models/vad/silero_vad.onnx`,
`models/tts/kokoro-v1.0.onnx`, and `models/tts/voices-v1.0.bin`;
`test_phase12_speech_adapters.py` repeats the same four in
`_MODEL_RELATIVE_PATHS`.

STT model selection and STT device selection sit in different files and do not
meet. `pipeline.run_voice_round_trip` passes `stt_model_size="small"` on every
profile and varies only device and compute type through
`_stt_device_for_profile`; the `large-v3-turbo` entry in the cuda manifests is
never reached.

`stt/*-qnn.yaml` declares `fallback_to` its arch's cpu profile, and
`verify_profile_models` implements a single fallback hop to support it.

Runtime facts the manifests must agree with:

- STT runs on faster-whisper (CTranslate2), whose devices are `cpu` and
  `cuda`. GPU execution requires NVIDIA libraries. DirectML and QNN are not
  CTranslate2 backends, so the `gpu` and `qnn` classes reach no STT
  acceleration.
- TTS, VAD, and wake run on ONNX Runtime through `kokoro-onnx`, a direct
  `InferenceSession`, and `openwakeword`. Their artifacts are the same bytes
  on every profile.
- `vad_silero.speech_probabilities` binds the input names `input`, `sr`, `h`,
  and `c`, and its ONNX file is sourced from the `silero-vad` PyPI package,
  which `pyproject.toml` does not declare as a dependency.
- `wake_openwakeword.detect_wake_word` constructs `Model(wakeword_model_paths=[...])`
  with one path. `models/wake/` holds three artifacts, because openWakeWord
  runs a melspectrogram model and a shared embedding model ahead of the
  wake-word classifier.

## Decision

**One manifest per function.** `config/voice/{stt,tts,vad,wake}.yaml`.

**Resolution keys on acceleration class.** The class is the final segment of
the canonical profile ID: `cpu`, `gpu`, `cuda`, or `qnn`. A class with no
entry resolves to `cpu`, which is the floor every profile already falls back
to. This replaces `fallback_to` and its resolution hop.

**Artifacts are named, not pinned.** A file entry declares a `name` and a
`url`, or a `name` and the `package` that supplies it. The artifact lands at
`models/<function>/<name>`. Package versions live in `pyproject.toml`;
URL-sourced artifacts carry their release tag in the URL.

**One module resolves and acquires.** `awf/speech/models.py` maps a profile ID
to artifact paths and to STT runtime parameters, acquires what is missing, and
verifies what is present. `speech/cli.py`, `speech/pipeline.py`, and the
speech tests read from it.

**`notes` states a required action or is absent.**

**`silero-vad` is declared in `pyproject.toml`.**

## Rationale

Three of the four functions have no per-profile variation, and the fourth
varies by accelerator only. Twelve files per function encode a matrix whose
other two axes — OS and architecture — no speech artifact uses.

Model selection and device selection are one decision made per acceleration
class. Holding them in one entry means a cuda host runs the model chosen for
cuda, which is the behavior the split currently prevents.

A hash and a revision pin the bytes of an operator-downloaded model on a
single-operator project. The artifacts are addressed by tagged release URL or
by installed package, both of which already identify a version, and package
versions belong in the dependency declaration rather than in a second file
that can disagree with it.

## Deviation recorded

| Requirement | Deviation | Compensating control |
|---|---|---|
| Section 16.4: manifests are "one YAML per canonical profile ID per function (`<profile-id>.yaml`)", and "profiles that pin identical artifacts repeat the pin" | one YAML per function, with class entries where a class differs | a test resolves every one of the twelve canonical profile IDs to a non-empty artifact set for every function |
| Section 16.4: manifests "pin the exact artifact URL and SHA-256 digest for every speech model and are the authority for bytes" | tagged release URL or supplying package; no digest | `awf-speech models verify` reports every expected artifact as `OK` or `MISSING`; package versions are pinned in `pyproject.toml` |
| Section 7 layout: `config/voice/{stt,tts,vad,wake}/` as directories | four files under `config/voice/` | filenames keep the function names |

The canonical profile enum, the resolution order, and the `*64-cpu` floor are
unchanged. Class resolution implements the floor: an absent class resolves to
`cpu`.

## Mechanism

### Part A — manifest shape

`config/voice/tts.yaml`:

```yaml
function: tts
files:
  - name: kokoro-v1.0.onnx
    url: https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx
  - name: voices-v1.0.bin
    url: https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin
```

`config/voice/wake.yaml`:

```yaml
function: wake
files:
  - name: hey_jarvis_v0.1.onnx
    url: https://github.com/dscripka/openWakeWord/releases/download/v0.5.1/hey_jarvis_v0.1.onnx
  - name: melspectrogram.onnx
    url: https://github.com/dscripka/openWakeWord/releases/download/v0.5.1/melspectrogram.onnx
  - name: embedding_model.onnx
    url: https://github.com/dscripka/openWakeWord/releases/download/v0.5.1/embedding_model.onnx
```

`config/voice/vad.yaml`:

```yaml
function: vad
files:
  - name: silero_vad.onnx
    package: silero-vad
```

`config/voice/stt.yaml`:

```yaml
function: stt
classes:
  cpu:
    model: small
    device: cpu
    compute_type: int8
  cuda:
    model: deepdml/faster-whisper-large-v3-turbo-ct2
    device: cuda
    compute_type: float16
```

Schema, exhaustive:

| Key | Where | Meaning |
|---|---|---|
| `function` | manifest | one of `stt`, `tts`, `vad`, `wake`; matches the filename stem |
| `files[].name` | manifest | artifact filename under `models/<function>/` |
| `files[].url` | file entry | download source; exactly one of `url` or `package` |
| `files[].package` | file entry | PyPI distribution that supplies the artifact |
| `classes.<class>.model` | `stt` | passed to `WhisperModel` as a size name or repository id |
| `classes.<class>.device` | `stt` | `cpu` or `cuda` |
| `classes.<class>.compute_type` | `stt` | CTranslate2 compute type |
| `notes` | manifest or file entry | an action a maintainer must take; omitted otherwise |

The `gpu` and `qnn` classes have no `stt` entry: CTranslate2 offers no
DirectML or QNN backend, so both resolve to `cpu`.

### Part B — `awf/speech/models.py`

```python
ACCELERATION_CLASSES = ("cpu", "gpu", "cuda", "qnn")

acceleration_class(profile_id: str) -> str
load_voice_manifest(repo_root: Path, function: str) -> VoiceManifest
artifact_paths(repo_root: Path, function: str) -> dict[str, Path]
stt_runtime(repo_root: Path, profile_id: str) -> SttRuntime
sync_models(repo_root: Path, profile_id: str) -> list[dict]
verify_models(repo_root: Path, profile_id: str) -> list[dict]
```

`acceleration_class` takes the segment after the last `-` and raises when it
is outside `ACCELERATION_CLASSES`. `stt_runtime` reads `classes[class]`,
falling back to `classes["cpu"]`, and returns `(model, device, compute_type)`.

`sync_models` is idempotent: an artifact already at
`models/<function>/<name>` is left untouched. `url` entries download to that
path. `package` entries locate the file inside the installed distribution
through `importlib.resources` and copy it, so the in-package layout stays
where the package defines it. STT has no file entries — `sync_models` warms
`models/stt/` by constructing `WhisperModel(model, download_root=models/stt)`
once for the resolved class and discarding it.

`verify_models` reports `{name, path, status}` with `status` in `OK` and
`MISSING`, one entry per expected artifact.

`awf-speech` gains `models sync` and `models verify`, each resolving the
profile through the Hardware Profiler.

### Part C — consumers

`speech/cli.py` builds its four paths from `artifact_paths`.

`speech/pipeline.py` takes model, device, and compute type from
`stt_runtime`, and `_stt_device_for_profile` and `ACCELERATED_STT_DEVICES` are
removed. `_verify_and_log_pinned_models` calls `verify_models` and keeps
writing the `pinned_model_verification` event, which stays advisory: a
`MISSING` artifact is recorded, and the failure surfaces at the adapter that
needs it.

`wake_openwakeword.detect_wake_word` takes all three wake artifacts and
constructs `Model(wakeword_model_paths=[...], melspec_onnx_model_path=...,
embedding_onnx_model_path=...)` - the installed `openwakeword` version's real
constructor and `AudioFeatures` kwarg names, which differ from this
mechanism's original pseudocode (`wakeword_models`, `inference_framework`,
`melspec_model_path`, `embedding_model_path`: none of these exist on the
installed version). Every wake artifact the manifest names is an artifact the
adapter loads, which is the property this mechanism exists for; the exact
kwarg names are an implementation detail of the installed library version.

`test_phase12_speech_adapters.py` takes its required paths from
`artifact_paths`. `test_baseline_hardware_voice_manifest.py` covers: the four
manifests parse; every canonical profile ID resolves to a non-empty artifact
set for each function; each of the twelve resolves to an `SttRuntime`; the
`gpu` and `qnn` classes resolve to the `cpu` entry; an unknown class raises.

`registry/hardware_voice_manifest.py` holds the per-function schema, its
parser, and `verify_models`; `fallback_to` and its resolution hop are removed.

### Part D — dependency declaration

`pyproject.toml` gains `silero-vad` alongside the other speech dependencies,
which puts the VAD package version in the same place as every other package
version.

## Layout delta

```text
config/voice/
  stt.yaml          (replaces stt/<12 files>)
  tts.yaml          (replaces tts/<12 files>)
  vad.yaml          (replaces vad/<12 files>)
  wake.yaml         (replaces wake/<12 files>)

backend/src/awf/speech/
  models.py         (new: resolution, acquisition, verification)
  cli.py            (paths from models.py; models sync | models verify)
  pipeline.py       (STT runtime from models.py)
  wake_openwakeword.py  (loads all three wake artifacts)

backend/src/awf/registry/
  hardware_voice_manifest.py  (per-function schema)

pyproject.toml      (silero-vad declared)
models/{stt,tts,vad,wake}/    (unchanged)
```

## The tradeoffs accepted

- A tagged release URL admits an upstream retag. `awf-speech models verify`
  reports presence, and an operator who needs byte-level certainty keeps a
  copy of `models/`, which is already outside version control.
- Class keys cover accelerator variation. An artifact that varies by OS or
  architecture would need a second key, added when such an artifact exists.
- Removing `fallback_to` moves the fallback from data into the resolution
  rule. The rule is the same one Section 16.4 states for profiles, so it holds
  for classes the manifest never mentions.
- `sync_models` warms STT by loading a model once, which downloads on a host
  that has no copy. That is the same download the first transcription would
  perform, moved to a command that can be run deliberately.

## Scope for implementation

1. Write the four `config/voice/*.yaml` files; delete the four directories.
2. Rewrite `registry/hardware_voice_manifest.py` for the per-function schema;
   remove `fallback_to` handling.
3. Add `awf/speech/models.py`.
4. Point `speech/cli.py` and `speech/pipeline.py` at it; remove
   `_stt_device_for_profile` and `ACCELERATED_STT_DEVICES`.
5. Update `wake_openwakeword.detect_wake_word` to load all three artifacts.
6. Add `awf-speech models sync` and `awf-speech models verify`.
7. Declare `silero-vad` in `pyproject.toml`; reinstall with
   `pip install -e .[dev]`.
8. Update `test_baseline_hardware_voice_manifest.py` and
   `test_phase12_speech_adapters.py` per Part C.
9. Run all six `scripts/validate_backend.py` commands.

## Acceptance

- `config/voice/` holds four files and no directories.
- All twelve canonical profile IDs resolve to a non-empty artifact set for
  each of the four functions, and to an `SttRuntime`.
- A `-cuda` profile resolves STT to
  `deepdml/faster-whisper-large-v3-turbo-ct2` with `device=cuda`,
  `compute_type=float16`. A `-cpu`, `-gpu`, or `-qnn` profile resolves to
  `small` with `device=cpu`, `compute_type=int8`.
- `awf-speech models verify` on a host with models present reports `OK` for
  every artifact, and the paths it reports are the four `speech/cli.py`
  previously held as literals, plus `melspectrogram.onnx` and
  `embedding_model.onnx`.
- `awf-speech models sync` populates an empty `models/` tree, and a second run
  changes no file.
- The voice round trip runs end to end and writes its
  `pinned_model_verification` event with every result `OK`.
- No manifest key is parsed without a reader.
- `pytest backend/tests` matches or exceeds the pre-change pass count with the
  same or fewer skips.

## Consequences

- An artifact change is one edit; a new canonical profile ID adds no file.
- A cuda host runs the model selected for cuda.
- `models/` is populated by a command, which makes the model-gated `live`
  tests reachable on a host that has not downloaded them by hand.
- The wake artifacts the manifest names are the artifacts the wake adapter
  loads.
- Every speech package version is declared in one file.
