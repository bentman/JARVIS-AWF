# ADR-0011: one registry kind vocabulary, one layout owner, one loader shape

## Status

Implemented. Acceptance run: `pytest backend/tests` → 436 passed (up from
423 baseline, same 0 skips); all six `scripts/validate_backend.py` commands
returned exit 0; `awf registry validate` on a real shipped object resolves
its kind from the path with no `--kind` given, and produces the identical
result when `--kind mcp` is passed explicitly; a repo-wide grep confirms no
kind-to-layout mapping (`_object_path`/`DATA_ONLY_KINDS`) and no
`config/app_registry`/`data/registry` string literal survive outside
`registry/kinds.py`, and `data/artifacts` is spelled only in `paths.py`.

A follow-up pass converted `mcp_server.py`'s and `voice_profile.py`'s two
remaining hand-rolled enum checks onto `registry/schema.require_enum`, the
two loaders left out of the initial pass because the shared helper's message
format didn't obviously match either one's wording. `voice_profile.py`'s
`tts.fallback.mode` check already used the exact `"{context}: '{value}' not
in {allowed}"` shape, so that conversion is byte-for-byte unchanged.
`mcp_server.py`'s `type` check did not (`"type '{value}' not in {allowed}"`,
no colon) - converting it changes that one message to
`"type: '{value}' not in {allowed}"`, accepted as a deliberate format-
consistency fix since no test asserts the exact text. All six loaders now
share one enum-check shape with no exceptions.

Covers Task B (items 5–8) and Task C (item 9) of the registry cohesion review.
Task A and Task D are ADR-0012, which builds on this record.

Alignment update, 2026-08-14: the one-kind-vocabulary decision now covers
twelve registry kinds, including `hardware-voice-manifests` and `llm-servers`.
All kind-specific validation uses JSON Schema modules under
`awf.registry.schemas` plus one shared loader path for identity, path, and
version checks. Registry operations moved from `awf.cli.core_ops` into
`awf.ops.registry`; `awf.cli.core_ops` remains only a compatibility re-export
surface.

## Context

**Kind-to-layout knowledge is written three times.** `resolve._object_path`
maps `skills` to `<version>/SKILL.md`, `agents` to `<version>.md`, and every
other kind to `<version>.yaml`. `core_ops.op_registry_list` re-derives the
same mapping through `is_skill` / `is_agent` branches and three different
globs. `core_ops.op_registry_publish` re-derives it a third time as an
`extension` variable. Adding a kind means finding all three.

**Kind names are bare strings.** `"workflows"`, `"agents"`, `"capabilities"`,
`"mcp"`, `"skills"`, `"voice-profiles"`, and `"model-profiles"` appear as
literals at every call site. Nothing validates them, so a misspelled kind
resolves to `RegistryObjectNotFoundError` rather than to an error naming the
mistake.

**Object type is inferred from content shape.** `op_registry_validate` and
`op_registry_publish` both dispatch by duck-typing the parsed YAML:
`raw.get("kind") == "Workflow"`, then `"identity" in raw and "risk_class" in
raw`, then `"type" in raw and raw.get("type") in ("stdio", "http")`, then
`"candidates" in raw and "privacy" in raw`. Only Workflow carries a `kind`
discriminator. The order of those tests is load-bearing, and a Voice Profile
and a Model Profile are separated only by which sibling keys they happen to
carry.

**Six loaders repeat the same scaffolding.** `agent_manifest.py`, `skill.py`,
`mcp_server.py`, `voice_profile.py`, `model_profile.py`, and
`capability_record.py` each define their own `_require`;
`model_profile.py` and `capability_record.py` each define their own
`_require_enum`; `agent_manifest.py` and `skill.py` each define their own
`_split_frontmatter`, character for character. `workflow/definition.py`
defines a seventh `_require`.

**Error class names diverge.** Five modules name theirs
`<Kind>ValidationError`. `capability_record.py` names its
`RegistryValidationError` — the most general name in the package, on the
most specific kind.

**Two path literals survived ADR-0009.** `core_ops._artifacts_root` builds
`repo_root / "data" / "artifacts"`, and `core_ops._make_run_map_item` builds
`repo_root / "data" / "awf_db" / "awf.db"` instead of calling
`paths.db_path`. `paths.py` has no `artifacts_dir`.

## Decision

**One kind vocabulary.** `registry/kinds.py` declares every registry kind
once, with its on-disk layout and its object type, and every call site names
a member of that vocabulary instead of a string literal.

**One layout owner.** Resolution, listing, and publishing read the layout
from that vocabulary. None of the three derives it independently.

**One dispatch key.** An object's kind is determined by where it is published
or by an explicit argument, never by guessing from its content shape.

**One loader shape.** `registry/schema.py` holds the shared `_require`,
`_require_enum`, and `_split_frontmatter` helpers and the base validation
error. Each loader keeps its own error subclass and its own parse function.

**`paths.py` owns the remaining two locations.**

## Rationale

Every item above is one fact written more than once. The registry is about to
carry more weight — objects authored by the system rather than by hand — and
each duplicated fact is a place where a new kind can be half-added.

Dispatching on content shape is the one item that is a correctness risk
rather than a maintenance cost: two kinds distinguished only by which
optional keys they carry will eventually collide, and the failure is a
mis-parse rather than an error.

## Deviation recorded

None. This record changes internal structure only. Every on-disk layout,
schema, kind name, and public function signature that a workflow or an
operator depends on stays as it is.

## Mechanism

### Task B — one vocabulary, one layout, one loader shape

`backend/src/awf/registry/kinds.py`:

```python
@dataclass(frozen=True)
class RegistryKind:
    key: str            # directory name under both registry roots
    layout: str         # "yaml" | "markdown" | "directory"
    data_only: bool     # no config/app_registry/ counterpart

WORKFLOWS   = RegistryKind("workflows",      "yaml",      False)
AGENTS      = RegistryKind("agents",         "markdown",  False)
CAPABILITIES= RegistryKind("capabilities",   "yaml",      False)
MCP         = RegistryKind("mcp",            "yaml",      False)
SKILLS      = RegistryKind("skills",         "directory", False)
VOICE_PROFILES = RegistryKind("voice-profiles", "yaml",   False)
MODEL_PROFILES = RegistryKind("model-profiles", "yaml",   False)
PERSONAS = RegistryKind("personas", "yaml", False)
MEMORY_PROFILES = RegistryKind("memory-profiles", "yaml", False)
SEMANTIC_MEMORIES = RegistryKind("semantic-memories", "yaml", False)

KINDS: tuple[RegistryKind, ...]
by_key(key: str) -> RegistryKind          # raises UnknownRegistryKindError
object_path(base_dir: Path, kind: RegistryKind, version: str) -> Path
version_names(name_dir: Path, kind: RegistryKind) -> tuple[str, ...]
```

`object_path` is the single implementation of the three-way layout mapping:
`directory` returns `<version>/SKILL.md`, `markdown` returns
`<version>.md`, `yaml` returns `<version>.yaml`. `version_names` is its
inverse, used by listing.

`resolve.py` keeps its public signature — `resolve_registry_object(repo_root,
kind: str, name, version)` — and resolves the string through `by_key` on
entry, so no caller changes. `_object_path` and `DATA_ONLY_KINDS` are
removed; `data_only` on the kind replaces the tuple.

`core_ops.op_registry_list` replaces its `is_skill` / `is_agent` branches and
three globs with `version_names`.

`core_ops.op_registry_publish` and `op_registry_validate` take an explicit
kind rather than inferring one:

- `op_registry_validate(path, *, kind: str | None = None)` — when `kind` is
  given, the object is parsed as that kind and a mismatch is an error. When
  it is omitted, the kind is derived from the path's position under a
  registry root, which is unambiguous. Content-shape guessing is removed.
- `op_registry_publish(repo_root, conn, *, path, kind: str)` — the caller
  states the kind. `awf registry publish` gains a `--kind` argument.

`backend/src/awf/registry/schema.py`:

```python
class RegistryValidationError(ValueError): ...

require(mapping, key, context, *, error) -> object
require_enum(value, allowed, context, *, error) -> str
split_frontmatter(text, *, error) -> tuple[dict, str]
```

Each loader passes its own error class, so messages and exception types stay
exactly as they are today. `capability_record.RegistryValidationError` is
renamed `CapabilityRecordValidationError`, matching its five siblings, and the
general name is freed for the shared base.

`workflow/definition.py` keeps its own `_require`: it is not a
`registry/` module and imports nothing from that package today.

### Task C — the last two path literals

`paths.py` gains:

```python
def artifacts_dir(repo_root: Path) -> Path:
    return repo_root / "data" / "artifacts"
```

`core_ops._artifacts_root` is replaced by it. `core_ops._make_run_map_item`
calls `paths.db_path(repo_root)` instead of assembling the same path.

## Layout delta

```text
backend/src/awf/
  paths.py                      (artifacts_dir)
  registry/
    kinds.py                    (new: RegistryKind vocabulary and layout)
    schema.py                   (new: shared require/require_enum/split_frontmatter)
    resolve.py                  (layout and data-only from kinds.py)
    agent_manifest.py           (shared helpers)
    capability_record.py        (shared helpers; error renamed)
    mcp_server.py               (shared helpers)
    model_profile.py            (shared helpers)
    skill.py                    (shared helpers)
    voice_profile.py            (shared helpers)
  cli/
    core_ops.py                 (kinds.py for layout; explicit kind on validate/publish)
    main.py                     (`registry publish --kind`)
```

## The tradeoffs accepted

- `awf registry publish` gains a required `--kind` argument. Inference by
  content shape is what the argument replaces, and the shapes it inferred
  from were never distinct enough to rely on.
- Seven `_require` copies become one shared helper that each loader
  parameterizes with its own error class. The parameter exists so the
  exception types and message text stay unchanged; a single shared error
  class would have been smaller and would have changed what every caller
  catches.
- `kinds.py` is a new module that mostly holds constants. It replaces three
  independent derivations of the same mapping, so the count of places that
  must agree drops from three to one.

## Scope for implementation

1. Add `registry/kinds.py` with the seven kinds, `by_key`, `object_path`, and
   `version_names`.
2. Add `registry/schema.py` with the shared helpers and the base error.
3. Repoint `resolve.py` at `kinds.py`; remove `_object_path` and
   `DATA_ONLY_KINDS`.
4. Repoint the six `registry/` loaders at `schema.py`; rename
   `capability_record.RegistryValidationError` to
   `CapabilityRecordValidationError`.
5. Repoint `op_registry_list` at `version_names`.
6. Give `op_registry_validate` an optional `kind` and path-derived fallback;
   give `op_registry_publish` a required `kind`; remove both content-shape
   dispatch chains. Add `--kind` to `awf registry publish`.
7. Add `paths.artifacts_dir`; replace `core_ops._artifacts_root` and the
   inline database path in `_make_run_map_item`.
8. Tests: `by_key` raises on an unknown kind; `object_path` returns the
   documented path for all three layouts; `version_names` round-trips against
   `object_path`; publishing with a `kind` that does not match the parsed
   object is an error; every existing registry test passes unchanged.
9. Run all six `scripts/validate_backend.py` commands.

## Acceptance

- No module outside `registry/kinds.py` maps a kind to a file layout.
- No module outside `registry/kinds.py` contains a registry kind string
  literal, except `kinds.py`'s own declarations and the CLI's argument help.
- `op_registry_validate` and `op_registry_publish` contain no content-shape
  dispatch.
- Publishing each of the five currently supported kinds produces the same
  path, digest, and `registry_index` row as before this change.
- `_require`, `_require_enum`, and `_split_frontmatter` are defined once
  under `registry/`.
- Every existing validation error message and exception type is unchanged,
  except `RegistryValidationError` on capability records.
- No module under `backend/src/awf/` assembles `data/artifacts` or
  `data/awf_db/awf.db` from path segments except `paths.py`.
- `pytest backend/tests` matches or exceeds the pre-change pass count with the
  same or fewer skips.

## Consequences

- Adding a registry kind is one entry in `kinds.py` plus its loader.
- `data/registry/` scaffolding now includes `.gitkeep` roots for every
  declared kind, including `memory-profiles` and `semantic-memories`.
- A misspelled kind fails with an error naming the kind and listing the valid
  ones.
- An object's type comes from where it lives or from what the caller said,
  never from what its keys resemble.
- ADR-0012 can treat `kinds.py` as the enumeration it needs to index, publish,
  and trust every kind uniformly.
