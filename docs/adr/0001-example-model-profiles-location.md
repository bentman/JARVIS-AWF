# ADR-0001: Example Model Profiles live under `config/app_registry/model-profiles/`

## Status

Accepted

## Context

Corrective update, 2026-08-12: this ADR's original data-only decision no
longer reflects repo truth. `model-profiles` now has the same two-root
resolution contract as other repo-default registry kinds:
`data/registry/model-profiles/` shadows operator-owned names, and
`config/app_registry/model-profiles/` supplies shipped defaults and examples
when no operator override is present.

The only committed example of the Model Profile shape lived at
`backend/tests/fixtures/model_profiles/local_ollama_r0.yaml`, hardcoding one
development machine's own WSL2 host-bridge IP address as `api_base` —
meaningless on any other machine — and demonstrating a single provider
(Ollama) despite Section 11 stating a profile "can point at any
LiteLLM-supported provider."

## Decision

Reference example Model Profiles — one per `purpose` value, spanning both
local and cloud providers — remain committed at
`config/app_registry/model-profiles/<name>/<version>.yaml`, alongside the
repository's other config-root defaults, each named with an `example-`
prefix. The repository also ships the default authoring profile at
`config/app_registry/model-profiles/resident-mind/1.0.0.yaml`, matching the
code default `resident-mind@1.0.0`.

`MODEL_PROFILES = RegistryKind("model-profiles", "yaml", False)`, so these
files are visible to `resolve_registry_object()` and `registry reindex`.
Operator profiles under `data/registry/model-profiles/` still take precedence
by name and version.

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
| `resident-mind` | general-reasoning | `openai` against loopback OpenAI-compatible endpoint | `Qwen3-4B-Q4_K_M.gguf` |

The judge/adversary pair deliberately resolves to two different cloud
provider families, matching Section 12.3's requirement that the
Adversary/Optimizer role route to a different model family than the
Builder.

## Consequences

- `config/app_registry/model-profiles/` is now a real config registry root.
  Fresh checkouts have a resolvable local-loopback `resident-mind@1.0.0`
  profile without requiring an operator-authored data object first.
- Tests exercise both direct `load_model_profile` parsing and
  `resolve_registry_object`/`registry reindex` behavior for shipped config
  profiles.
- Re-verify each cloud-provider example's `model` field against
  `litellm.model_cost` whenever the pinned `litellm` version changes — a
  provider MAY deprecate a model name over time.
- `op_registry_list` lists config model profiles, because they are real,
  resolvable defaults unless shadowed by operator data.
