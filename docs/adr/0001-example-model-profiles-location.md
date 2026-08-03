# ADR-0001: Example Model Profiles live under `config/app_registry/model-profiles/`

## Status

Accepted

## Context

Section 9.3 establishes `model-profiles` as the one registry kind with no
`config/app_registry/` counterpart: a Model Profile names a specific
provider account and budget, so it is always operator-specific.
`registry/resolve.py::DATA_ONLY_KINDS` enforces this — `resolve_registry_object()`
never consults `config/app_registry/model-profiles/` for a real Run.

The only committed example of the Model Profile shape lived at
`backend/tests/fixtures/model_profiles/local_ollama_r0.yaml`, hardcoding one
development machine's own WSL2 host-bridge IP address as `api_base` —
meaningless on any other machine — and demonstrating a single provider
(Ollama) despite Section 11 stating a profile "can point at any
LiteLLM-supported provider."

## Decision

Reference example Model Profiles — one per `purpose` value, spanning both
local and cloud providers — are committed at
`config/app_registry/model-profiles/<name>/<version>.yaml`, alongside the
repository's other config-root defaults, each named with an `example-`
prefix and carrying a header comment stating it is not an operator's real
registry entry.

`registry/resolve.py::DATA_ONLY_KINDS` is unchanged by this decision — these
files are never read through `resolve_registry_object()` for kind
`model-profiles` during a real Run. Tests load them directly by file path.

Each example's `model` field is checked against a real, currently-existing
target at authoring time: for a cloud provider, against LiteLLM's own
bundled `litellm.model_cost` registry (the same registry the Model Gateway
routes through); for a local provider, against a real model actually
pulled/loaded and, where a live instance was reachable, a real completion
call through the Model Gateway itself (`example-ollama-general`,
`example-llamacpp-coding`). `example-lmstudio-embedding` had no live LM
Studio instance to verify against, so its `model` stays a label pending
that verification. `api_base` values use each provider's documented default
port, never a machine-specific address.

| Example | Purpose | Provider | Model |
|---|---|---|---|
| `example-ollama-general` | general-reasoning | `ollama` (local) | `phi4-mini:latest` |
| `example-llamacpp-coding` | coding | `llamafile` (local) | `Qwen3-8B-Q5_K_M.gguf` — verified live against a real llama-server instance (`/v1/models`), and a full completion round trip through the Model Gateway |
| `example-lmstudio-embedding` | embedding | `lm_studio` (local) | label only — no LM Studio instance available to verify against; a server's loaded model is whatever the operator started it with, not a fixed catalog |
| `example-anthropic-judge` | judge | `anthropic` (cloud) | `claude-haiku-4-5` |
| `example-openai-adversary` | adversary | `openai` (cloud) | `gpt-4o-mini` |

The judge/adversary pair deliberately resolves to two different cloud
provider families, matching Section 12.3's requirement that the
Adversary/Optimizer role route to a different model family than the
Builder.

## Consequences

- `config/app_registry/model-profiles/` is the one config-root directory a
  real Run's registry lookup never reads — a Run resolving a Model Profile
  by name still only ever finds `data/registry/model-profiles/`, matching
  Section 9.3 exactly.
- Tests exercising `load_model_profile`'s on-disk YAML-parsing path load
  these files directly by path, not through `resolve_registry_object`.
- Re-verify each cloud-provider example's `model` field against
  `litellm.model_cost` whenever the pinned `litellm` version changes — a
  provider MAY deprecate a model name over time.
- `op_registry_list` did not originally share `resolve_registry_object`'s
  `DATA_ONLY_KINDS` restriction — it walked both roots for every kind, so it
  would have listed these examples as if they were real, resolvable
  registry objects. Fixed alongside this ADR: `op_registry_list` now skips
  the config root entirely for any kind in `DATA_ONLY_KINDS`.
