# ADR-0017: the resident mind — local LLM server selection, acquisition, and lifecycle

## Status

Implemented.

Acceptance run: `scripts/validate_backend.py lint` passed; `scripts/validate_backend.py runtime` -> 17 passed, 1 skipped; `scripts/validate_backend.py ci` -> 509 passed, 18 deselected. `awf-setup --verify` reports the installed Ruff dev-tooling floor and `pip_check: OK`.

Corrective update: `awf llm serve start` now detaches managed `llama-server`
processes so later CLI invocations can observe and stop them through persisted
sidecar state. Managed LLM startup and readiness use the host accelerator
artifact when present and fall back to the matching CPU artifact when the
accelerator artifact is unavailable. Loopback OpenAI-compatible endpoints get
a local placeholder API key in the Model Gateway so LiteLLM/OpenAI client setup
does not reject local llama.cpp before the request reaches the server.

## Context

The Model Gateway calls `litellm.completion` in-process.
`gateway/client.complete(profile, messages, *, conn=None, secret_key=None)`
walks `profile.enabled_candidates_by_priority()`, builds
`{"model": f"{provider}/{model}", "messages": ..., "max_tokens":
profile.limits.max_output_tokens_per_call}`, adds `api_base` when the
candidate declares one and `api_key` when its `api_key_secret_name` resolves
through the secrets store, and returns
`response.choices[0].message.content`. That is the whole of AWF's model
access, and it is enough to reach any OpenAI-compatible endpoint that is
already running.

Nothing starts one. No module in the package spawns, probes, or stops a model
server process, and no command reports whether one is reachable.

Model Profiles are data-only: `registry/kinds.py` declares
`MODEL_PROFILES = RegistryKind("model-profiles", "yaml", True)`, and
`resolve_registry_object` refuses to resolve a `data_only` kind from
`config/app_registry/`. The five profiles under
`config/app_registry/model-profiles/` are reference examples a Run never
resolves. Two already name a local endpoint — `example-ollama-general` with
`api_base: "http://localhost:11434"` and `example-llamacpp-coding` with
`api_base: "http://127.0.0.1:8080/v1"` — so the shape for reaching a local
server exists and has never been driven.

`models/llm/` was removed by ADR-0010, since nothing used it. `runtimes/` has
never existed. `.gitignore` globally excludes `**/*.exe`, `**/*.dll`,
`**/*.gguf`, and `**/*.bin`, and gates `models/` with a per-directory
allowlist (`/models/stt/*` and `!/models/stt/.gitkeep`, and the same for
`tts`, `vad`, `wake`). `runtimes/` is not gated at all, so an extensionless
Linux binary placed there today would be committable.

`hardware/readiness.py` exports `Readiness(device, ready, reason)` and four
functions — `derive_stt_readiness`, `derive_tts_readiness`,
`derive_vad_readiness`, `derive_wake_readiness` — each granting a device above
`cpu` only when a hardware fact and a runtime token agree. There is no `llm`
function. The evidence an LLM accelerator decision needs is already produced
under the names it would use:

| Source | Field or token |
|---|---|
| `profiler.collect_inventory()` | `gpu_vendor`, `gpu_available`, `cuda_available`, `npu_vendor`, `npu_available` |
| `preflight.collect_preflight_tokens()` | `ep:CUDAExecutionProvider`, `ep:QNNExecutionProvider`, `dll:QnnHtp`, `opencl:adreno` |

`profiler.run_hardware_profiler(conn, *, repo_root=None, refresh=False)`
resolves one canonical profile ID from those readiness results and writes
`hardware_profile_resolved` with `profile_id`, `inventory`, `tokens`, and
`readiness`.

`speech/models.sync_models` is the working shape for artifact acquisition:
resolve what is expected, skip what is present, download the rest, and return
one result row per artifact.

## Decision

**Three server backends, declared once.** `config/llm/servers.yaml` names
`llama-server`, `ollama`, and `openai-compatible`, with how to reach each and
— for `llama-server` only — how to acquire and launch it.

**Only `llama-server` is managed.** AWF acquires its binary, starts it, probes
it, and stops it. `ollama` and `openai-compatible` are operator-run: AWF
probes them and never starts or stops them. `openai-compatible` is the entry
for `llama.app` and any other server exposing `/v1/chat/completions`.

**Selection is an operator act recorded in the registry.** `awf llm select`
writes a `resident-mind` Model Profile into `data/registry/model-profiles/`
through the existing publish path. Resolution, the Gateway, and the Guard are
unchanged.

**`models/llm/<model-name>/<files>` returns.** Discovery scans it; a model is
selectable when its directory holds at least one `.gguf`. AWF never acquires a
model.

**Acquisition covers declared llama.cpp runtime artifacts.** Official CPU and
Vulkan release archives are acquired on request into
`runtimes/llama.cpp/<profile-id>/`. Windows x64 CUDA uses the upstream
llama.cpp CUDA 12.4 release archive. Linux CUDA, Snapdragon Hexagon/QNN, and
Adreno OpenCL entries may be declared as `archive: manual`, meaning the
operator must place a compatible build under that same runtime directory.
Helper scripts under `docs/helpers/` document and automate the currently
known manual build/staging paths for Linux x64 CUDA, Windows ARM64 Adreno
OpenCL, and Windows ARM64 QNN/Hexagon.

**`derive_llm_readiness` resolves the full accelerator ladder.** CUDA, QNN,
Vulkan, and Adreno OpenCL are each decided from inventory facts and preflight
tokens, and each additionally requires a declared artifact and an extracted
binary. The server config declares every canonical profile ID; manual artifacts
are usable as soon as the operator-provided runtime directory exists.

**Each turn is isolated.** Whatever a profile's launch block says, the sidecar
starts with no reusable prompt cache, one slot, and continuous batching off.

## Rationale

AWF can already talk to all three backends. What is missing is the operator's
ability to say which one, the lifecycle for the one AWF owns, and the
acquisition of its binary. Framing the selector as a Model Profile keeps all
three inside machinery that already exists: resolution precedence, operator
override, versioning, and the `registry_index` digest and trust columns apply
with no new kind.

Managing only `llama-server` follows from ownership. An Ollama daemon and a
desktop application are the operator's processes with their own lifecycles and
model stores; probing them is honest, stopping them is not.

The accelerator ladder is written in full rather than stubbed because its
inputs already exist under the same names, and because a ladder first written
when an accelerated artifact is declared is a ladder that has never run.
Writing it now means declaring an artifact exercises a path CPU hosts have
been running against all along.

Turn isolation is what makes two identical turns comparable. A prompt cache
carried between turns makes a Step's result depend on what ran before it,
which the durability contract does not admit.

## Deviation recorded

| Requirement | Deviation | Compensating control |
|---|---|---|
| Section 7 repository layout | adds `runtimes/llama.cpp/<profile-id>/` and `config/llm/`, and reinstates `models/llm/` | `runtimes/` is gitignored in full and holds only acquired binaries; `config/llm/servers.yaml` follows the `config/voice/*.yaml` shape already in use; `models/llm/` returns under the same per-directory allowlist as the four speech directories |
| ADR-0010 Task B, which removed `models/llm/` as a directory for a function this repository does not have | reinstated | the function now exists: `models/llm/<model-name>/` is where the operator places the GGUF weights `llama-server` loads |

Section 11's Model Profile schema, the Gateway, resolution precedence, and the
Capability Guard are unchanged.

## Mechanism

### Part A — `config/llm/servers.yaml`

```yaml
default_server: llama-server

servers:
  llama-server:
    managed: true
    base_url: http://127.0.0.1:8080
    openai_base_path: /v1
    provider: openai
    health_paths: [/health, /v1/models]
    artifacts:
      linux-x64-cpu:
        url: https://github.com/ggml-org/llama.cpp/releases/download/b9704/llama-b9704-bin-ubuntu-x64.tar.gz
        archive: tar_gz
        binary: llama-server
        accelerator: cpu
      linux-arm64-cpu:
        url: https://github.com/ggml-org/llama.cpp/releases/download/b9704/llama-b9704-bin-ubuntu-arm64.tar.gz
        archive: tar_gz
        binary: llama-server
        accelerator: cpu
      windows-x64-cpu:
        url: https://github.com/ggml-org/llama.cpp/releases/download/b9704/llama-b9704-bin-win-cpu-x64.zip
        archive: zip
        binary: llama-server.exe
        accelerator: cpu
      windows-arm64-cpu:
        url: https://github.com/ggml-org/llama.cpp/releases/download/b9704/llama-b9704-bin-win-cpu-arm64.zip
        archive: zip
        binary: llama-server.exe
        accelerator: cpu
    launch:
      ctx_size: 4096
      batch_size: 512
      ubatch_size: 128
      gpu_layers: 0
      cache_type_k: q8_0
      cache_type_v: q8_0

  ollama:
    managed: false
    base_url: http://127.0.0.1:11434
    openai_base_path: /v1
    provider: ollama
    health_paths: [/api/tags]

  openai-compatible:
    managed: false
    base_url: http://127.0.0.1:8080
    openai_base_path: /v1
    provider: openai
    health_paths: [/v1/models]
    api_key_secret_name: null
```

Schema, exhaustive:

| Key | Where | Meaning |
|---|---|---|
| `default_server` | manifest | server id used when `awf llm select` is given none |
| `managed` | server | AWF starts and stops it |
| `base_url` | server | scheme, host, port; no trailing slash |
| `openai_base_path` | server | appended to `base_url` for the Model Profile candidate's `api_base` |
| `provider` | server | litellm provider prefix for the candidate |
| `health_paths` | server | probed in order; the first that answers 2xx wins |
| `api_key_secret_name` | server | optional; the candidate's `api_key_secret_name` |
| `artifacts.<profile-id>` | managed server | one entry per canonical profile ID |
| `artifacts.*.url` | artifact | release archive |
| `artifacts.*.archive` | artifact | `tar_gz` or `zip` |
| `artifacts.*.binary` | artifact | file name to locate inside the archive |
| `artifacts.*.accelerator` | artifact | `cpu`, `gpu.cuda`, `npu.qnn`, or `gpu.opencl.adreno` |
| `artifacts.*.launch` | artifact | optional per-artifact launch overrides, merged over the server's `launch` |
| `launch` | managed server | base launch keys for every artifact |

An artifact key must be a member of `profiler.CANONICAL_PROFILES`; anything
else fails to load, naming the key. The four `*-cpu` keys are declared and the
eight accelerated keys are absent. Declaring one is a YAML edit.

### Part B — `awf/llm/servers.py`

```python
class LlmServerError(ValueError): ...

@dataclass(frozen=True)
class Artifact:
    profile_id: str
    url: str
    archive: str          # "tar_gz" | "zip"
    binary: str
    accelerator: str
    launch: dict

@dataclass(frozen=True)
class LlmServer:
    id: str
    managed: bool
    base_url: str
    openai_base_path: str
    provider: str
    health_paths: tuple[str, ...]
    artifacts: dict[str, Artifact]
    launch: dict
    api_key_secret_name: str | None

    @property
    def api_base(self) -> str:        # base_url + openai_base_path

load_servers(repo_root) -> tuple[str, dict[str, LlmServer]]   # (default_id, by_id)
artifact_for(server, profile_id) -> Artifact | None
```

Parsing uses `registry/schema.require` and `require_enum` bound to
`LlmServerError`, matching every other loader in the package.
`artifact_for` returns `None` for an undeclared profile ID; callers turn that
into their own reason string rather than raising here.

### Part C — `awf/llm/discovery.py`

```python
@dataclass(frozen=True)
class LocalModel:
    name: str             # models/llm/<name>
    files: tuple[Path, ...]   # *.gguf, sorted
    primary: Path         # the largest .gguf

local_models(repo_root) -> tuple[LocalModel, ...]
model_by_name(repo_root, name) -> LocalModel        # raises when absent or has no .gguf
binary_path(repo_root, profile_id, artifact) -> Path
acquire_binary(repo_root, profile_id, artifact) -> dict
```

`binary_path` returns `runtimes/llama.cpp/<profile-id>/<artifact.binary>`
whether or not it exists.

`acquire_binary` is idempotent and returns
`{"profile_id", "status", "path", "url"}` with `status` in `PRESENT`,
`ACQUIRED`:

1. return `PRESENT` when `binary_path(...)` is a file of non-zero size;
2. download `artifact.url` to `cache/llm/<profile-id>/<basename>`;
3. extract to a sibling scratch directory — `tarfile` for `tar_gz`,
   `zipfile` for `zip`;
4. locate `artifact.binary` by recursive search of the extracted tree; when it
   is not found, raise naming the archive and the expected name;
5. copy every file in the directory that contains it into
   `runtimes/llama.cpp/<profile-id>/`, flat. Release archives place the
   binary alongside the shared libraries it loads, so the containing
   directory is the unit that must move together;
6. set the executable bit on the binary on non-Windows hosts;
7. remove the scratch directory and return `ACQUIRED`.

The caller supplies the artifact, so `acquire_binary` never decides which host
it is running on.

### Part D — `awf/llm/sidecar.py`

```python
HEALTH_TIMEOUT_SECONDS = 60.0
HEALTH_POLL_SECONDS = 0.5
STOP_TIMEOUT_SECONDS = 5.0

@dataclass(frozen=True)
class Health:
    reachable: bool
    reason: str

@dataclass(frozen=True)
class Command:
    argv: tuple[str, ...]
    warnings: tuple[str, ...]

@dataclass(frozen=True)
class SidecarStatus:
    state: str            # "running" | "adopted" | "stopped" | "degraded"
    server_id: str | None
    base_url: str | None
    model_path: str | None
    profile_id: str | None
    pid: int | None
    adopted: bool
    warnings: tuple[str, ...]
    reason: str | None

probe(server) -> Health
build_command(binary, model_path, base_url, launch) -> Command
start(repo_root, server, artifact, model) -> SidecarStatus
stop() -> SidecarStatus
status(server) -> SidecarStatus
```

`probe` issues a GET against each entry of `server.health_paths` in order,
with a two-second timeout, and returns on the first 2xx with
`f"{path} reachable"`. When none answers it returns the last failure as the
reason. It uses `urllib.request` from the standard library; no new dependency
is added.

`build_command` produces:

```text
<binary> --model <model_path> --host <host> --port <port> <translated launch flags> <turn isolation>
```

`host` and `port` come from `urllib.parse.urlparse(base_url)`, defaulting to
port 8080. Launch keys translate through one table:

| Launch key | Flag | Value form |
|---|---|---|
| `ctx_size` | `--ctx-size` | integer |
| `threads` | `--threads` | integer, or `-1` for `auto` |
| `threads_batch` | `--threads-batch` | integer, or `-1` for `auto` |
| `batch_size` | `--batch-size` | integer |
| `ubatch_size` | `--ubatch-size` | integer |
| `gpu_layers` | `--gpu-layers` | integer, or `all` |
| `cache_type_k` | `--cache-type-k` | string |
| `cache_type_v` | `--cache-type-v` | string |
| `split_mode` | `--split-mode` | string |
| `main_gpu` | `--main-gpu` | integer |
| `flash_attn` | `--flash-attn` | string |
| `device` | `--device` | string |
| `parallel` | `--parallel` | integer |
| `cont_batching` | `--cont-batching` / `--no-cont-batching` | boolean |
| `warmup` | `--warmup` / `--no-warmup` | boolean |

Then, appended last and not configurable:

```text
--cache-ram 0 --parallel 1 --no-cont-batching
```

`cache_ram_mb`, `parallel`, and `cont_batching` are dropped from the profile's
own keys before translation, each producing the warning
`"launch key '<key>' is overridden by turn isolation"`. An unrecognized key
produces `"unsupported launch key: <key>"`; a value that cannot be translated
produces `"unsupported launch value: <key>=<value!r>"`. Both are warnings on
the returned `Command`, never silent drops, and both are carried into the
`llm_server_started` event.

`start`:

1. `probe(server)` — when reachable, record the adoption, set
   `state="adopted"`, `adopted=True`, `pid=None`, and return without
   launching anything;
2. build the command; when the binary or the model file is missing, return
   `state="degraded"` with `reason` set to `Degraded-no-sidecar-binary` or
   `Degraded-no-local-model-artifact`;
3. `subprocess.Popen(argv, cwd=binary.parent)` — `cwd` is the binary's own
   directory so it resolves the shared libraries copied alongside it;
4. poll `probe` every `HEALTH_POLL_SECONDS` until reachable or
   `HEALTH_TIMEOUT_SECONDS` elapses; on timeout, terminate the process and
   return `state="degraded"` with `reason="Degraded-health-timeout"`;
5. return `state="running"`, `adopted=False`, with the pid.

`stop` terminates only a process this module started: when the recorded state
is `adopted`, it clears the adoption and returns `state="stopped"` without
signalling anything. Otherwise it calls `terminate()`, waits
`STOP_TIMEOUT_SECONDS`, then `kill()` and waits again. There is no port
reclamation and no process scanning — AWF does not signal processes it did not
start.

The module holds the started process in a module-level variable, the same
process-lifetime shape `profiler` uses for its inventory cache.

### Part E — readiness

`hardware/readiness.py` gains, matching the four existing signatures:

```python
def derive_llm_readiness(
    inventory: "HardwareInventory",
    tokens: list[str],
    *,
    server: LlmServer,
    profile_id: str,
    model_path: Path | None,
) -> Readiness
```

The ladder, first match wins. Each rung requires its hardware fact, its
runtime token where one applies, a declared artifact for `profile_id` whose
`accelerator` matches the rung, and a binary present at
`binary_path(repo_root, profile_id, artifact)`:

| Device | Hardware | Tokens | Artifact accelerator |
|---|---|---|---|
| `gpu.cuda` | `gpu_vendor == "nvidia"`, `cuda_available` | `ep:CUDAExecutionProvider` | `gpu.cuda` |
| `npu.qnn` | `npu_vendor == "qualcomm"`, `npu_available` | `ep:QNNExecutionProvider`, `dll:QnnHtp` | `npu.qnn` |
| `gpu.opencl.adreno` | `gpu_vendor == "qualcomm"`, `gpu_available` | `opencl:adreno` | `gpu.opencl.adreno` |
| `cpu` | — | — | `cpu` |

Reason strings, in the order they are reached:

| Condition | `ready` | `reason` |
|---|---|---|
| server is unmanaged | `True` | `"<server.id> is operator-run; device is the server's own concern"` |
| a rung's hardware and tokens agree but no artifact declares that accelerator | falls through | `"Degraded-accelerator-unavailable: no <accelerator> artifact declared for <profile_id>"` |
| an artifact is declared but its binary is absent | `False` | `"Degraded-no-sidecar-binary: <path>"` |
| `model_path` is `None` or not a file | `False` | `"Degraded-no-local-model-artifact: <model_path>"` |
| a rung fully satisfied | `True` | `"<hardware facts>, <tokens>, <accelerator> artifact declared"` |
| nothing above `cpu` satisfied | `True` | `"no verified accelerator artifact; running on cpu"` |

On an NVIDIA host with only CPU artifacts declared, the CUDA rung's hardware
and token both hold and the artifact does not, so the result is `cpu` with a
reason naming the absent declaration rather than absent hardware.

`profiler.run_hardware_profiler` adds `"llm"` to its `readiness` mapping, so
`hardware_profile_resolved` carries five entries. It resolves the selected
server and model through `awf/llm/selector.current_selection`, and when no
`resident-mind` profile is published yet it uses `default_server` with
`model_path=None`.

### Part F — selection

`awf/llm/selector.py`:

```python
RESIDENT_MIND_NAME = "resident-mind"
RESIDENT_MIND_VERSION = "1.0.0"

current_selection(repo_root) -> Selection | None   # parsed from the published profile
select(repo_root, conn, *, server_id, model=None, allow_remote=False) -> dict
```

`select` builds a Model Profile and publishes it through
`core_ops.op_registry_publish`, so it is indexed, digested, and trust-marked
like any other object:

```yaml
name: resident-mind
version: 1.0.0
purpose: general-reasoning
privacy: {maximum_data_class: internal, local_only: true}
candidates:
  - {provider: openai, model: Qwen3-4B-Q4_K_M.gguf, priority: 1, enabled: true,
     api_base: "http://127.0.0.1:8080/v1"}
fallback: {mode: none, allow_quality_degrade: false}
limits: {max_input_tokens_per_call: 8192, max_output_tokens_per_call: 1024, max_cost_usd_per_call: 0.0}
```

- `provider` and `api_base` come from the server (`server.provider`,
  `server.api_base`).
- `model` is the primary GGUF's file name for `llama-server`, and the
  operator-supplied `--model` string for `ollama` and `openai-compatible`.
- `api_key_secret_name` is written only when the server declares one.
- `local_only` is `True` when `urlparse(server.base_url).hostname` is
  `127.0.0.1`, `::1`, or `localhost`, and `False` otherwise. A `False` result
  without `allow_remote=True` raises, naming the host.

`current_selection` resolves `resident-mind@1.0.0` through
`resolve_registry_object` and returns `None` when it is not published.

The repository ships
`config/app_registry/model-profiles/example-resident-mind/1.0.0.yaml` as a
sixth reference example. It is never resolved, matching ADR-0001.

### Part G — activity, events, and CLI

`workflow/activities.py` registers `llm_server_ensure`: resolve the current
selection, probe, and start the managed sidecar when unreachable. It returns
the `SidecarStatus` as a mapping. Its Capability Record ships at
`config/app_registry/capabilities/llm_server_ensure/1.0.0.yaml` —
`type: activity`, `provider: awf`, `name: llm_server_ensure`,
`version: 1.0.0`, `operation: execute`, `risk_class: R1`, `approval: never` —
so an activity node that starts a process passes the Guard like every other
activity (ADR-0009).

`start` and `stop` write events against `profiler.SYSTEM_RUN_ID` through
`events.writer.write_event`:

| reason_code | payload |
|---|---|
| `llm_server_started` | `server_id`, `base_url`, `model_path`, `profile_id`, `adopted`, `pid`, `argv`, `warnings`, `readiness` |
| `llm_server_stopped` | `server_id`, `base_url`, `adopted`, `reason` |

CLI:

```text
awf llm servers                     # each backend: managed, reachable/why, binary and model presence, current selection
awf llm models                      # models/llm/<name>/*.gguf; plus ollama's own list when it is reachable
awf llm acquire                     # the declared archive for this host's profile ID
awf llm select <server-id> [--model <name>] [--allow-remote]
awf llm serve start | stop | status
```

## Layout delta

```text
config/
  llm/servers.yaml                                  (new)
  app_registry/
    capabilities/llm_server_ensure/1.0.0.yaml       (new)
    model-profiles/example-resident-mind/1.0.0.yaml (new)
models/
  llm/.gitkeep                                      (reinstated)
runtimes/
  llama.cpp/.gitkeep                                (new)
cache/
  llm/                                              (scratch for downloads; gitignored by /cache/*)
backend/src/awf/
  llm/{__init__,servers,discovery,sidecar,selector}.py   (new)
  paths.py                                          (config_llm_dir, llm_models_dir, runtimes_dir)
  hardware/readiness.py                             (derive_llm_readiness)
  hardware/profiler.py                              (fifth readiness entry)
  workflow/activities.py                            (llm_server_ensure)
  cli/{main,core_ops}.py                            (awf llm ...)
.gitignore                                          (/models/llm/*, !/models/llm/.gitkeep, /runtimes/*, !/runtimes/.gitkeep)
```

## The tradeoffs accepted

- Pinning one llama.cpp release means the acquired binary ages with the
  manifest rather than with upstream. The pin is one line per host, and
  `awf llm acquire` reports the URL it fetched.
- Adopting an already-running endpoint means AWF may serve through a process
  it did not configure. The alternative — reclaiming the port — signals
  processes AWF does not own. Adoption is recorded in the status and the
  event, so the ambiguity is visible rather than silent.
- Turn isolation costs throughput. A prompt cache and continuous batching are
  what make a server fast across many turns, and giving them up is what makes
  one turn independent of the last.
- The `resident-mind` profile is written by a command, so an operator who
  hand-edits the file and then re-runs `awf llm select` loses those edits. The
  file is versioned in the registry and the command reports what it wrote.
- Three of the ladder's four rungs are exercised only by tests until an
  accelerated artifact is declared. Those tests drive synthesized inventories,
  tokens, and artifact maps, which is how the four speech readiness functions
  are already covered.

## Scope for implementation

1. Add `paths.config_llm_dir`, `paths.llm_models_dir`, `paths.runtimes_dir`.
2. Add `config/llm/servers.yaml` with the three servers and the four CPU
   artifacts.
3. Add `awf/llm/servers.py`: dataclasses, loader, canonical-profile-ID
   validation of artifact keys, `artifact_for`.
4. Add `awf/llm/discovery.py`: `local_models`, `model_by_name`,
   `binary_path`, `acquire_binary` with the seven-step algorithm.
5. Add `awf/llm/sidecar.py`: `probe`, `build_command` with the flag table,
   turn-isolation overrides and warnings, adopt-or-spawn `start`, health
   polling, `stop` that never signals an adopted endpoint.
6. Add `awf/llm/selector.py`: `current_selection`, `select` with the loopback
   rule, publishing through `op_registry_publish`.
7. Add `derive_llm_readiness` with the ladder and the reason table; add the
   fifth entry to the profiler payload.
8. Register `llm_server_ensure` and ship its Capability Record.
9. Ship `example-resident-mind`.
10. Add the `awf llm` command group and the two event writes.
11. Reinstate `models/llm/`, add `runtimes/llama.cpp/`, and their `.gitignore`
    rules.
12. Tests: the manifest parses and an artifact key outside
    `CANONICAL_PROFILES` fails naming the key; `artifact_for` returns `None`
    for an undeclared host; `build_command` covers every flag-table row,
    appends the three isolation flags last, warns for an unknown key, warns
    when a profile sets `parallel`/`cont_batching`/`cache_ram_mb`, and warns
    on an untranslatable value; `acquire_binary` returns `PRESENT` for an
    existing binary and copies the containing directory flat from a
    synthesized archive; `start` adopts a reachable endpoint without spawning
    and `stop` leaves it running; `select` refuses a non-loopback host without
    `allow_remote` and writes `local_only: false` with it;
    `derive_llm_readiness` returns each of the four devices over synthesized
    inputs and returns `cpu` with the artifact-absent reason when hardware and
    tokens agree but no artifact declares that accelerator.
13. Run all six `scripts/validate_backend.py` commands.

## Acceptance

- `awf llm servers` reports all three backends with a reachability reason on a
  host with none of them running.
- `awf llm acquire` places a `llama-server` binary and its sibling libraries
  under `runtimes/llama.cpp/<profile-id>/`, and a second run reports
  `PRESENT` without downloading.
- On a host whose profile ID has no declared artifact, `awf llm acquire`
  refuses with a message naming the profile ID; on a host whose artifact is
  declared `manual`, it refuses with the runtime directory the operator must
  populate.
- With a GGUF under `models/llm/<name>/`, `awf llm models` lists it and
  `awf llm select llama-server --model <name>` writes a `resident-mind`
  profile that `resolve_registry_object` resolves from
  `data/registry/model-profiles/`.
- `awf llm serve start` launches the binary, reaches health within the
  timeout, and writes `llm_server_started` whose `argv` ends with
  `--cache-ram 0 --parallel 1 --no-cont-batching`; a `gateway.complete` call
  through the `resident-mind` profile returns text from the local model.
- With a server already listening at the configured base URL,
  `awf llm serve start` returns `state="adopted"` with `pid=None`, and
  `awf llm serve stop` leaves it running.
- `awf llm select ollama` against a running Ollama produces a profile that
  completes without AWF starting any process.
- `awf llm select openai-compatible` against a non-loopback base URL without
  `--allow-remote` is refused naming the host; with the flag the written
  profile carries `local_only: false`.
- On a NVIDIA host with a declared CUDA artifact but no local model selected,
  `derive_llm_readiness` reports the CUDA device and
  `Degraded-no-local-model-artifact`; with the model and binary present it
  returns `gpu.cuda`.
- The `hardware_profile_resolved` payload carries five readiness entries.
- `pytest backend/tests` matches or exceeds the pre-change pass count with the
  same or fewer skips.

## Consequences

- AWF has a model it can reach without an operator starting anything by hand,
  on a host where only the CPU binary and one GGUF are present.
- Which backend serves the resident mind is a registry object with a version,
  a digest, and a trust status, changed by one command and readable by any
  frontend.
- `models/llm/` holds operator-supplied weights, and no acquisition path
  reaches into it.
- Enabling an accelerated llama.cpp build is a YAML edit against a resolution
  path CPU hosts have already been running, and its absence is reported by
  name rather than inferred from silence.
- Two identical turns run against the same server state.
- Reaching a non-loopback endpoint requires an explicit flag and is recorded
  in the profile's `local_only` field.
