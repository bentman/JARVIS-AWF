# ADR-0012: the registry index earns its keep — integrity, trust, and lifecycle

## Status

Implemented. Acceptance run: `pytest backend/tests` → 460 passed (up from
436 baseline, same 0 skips); all six `scripts/validate_backend.py` commands
returned exit 0. Manually verified end to end: `awf registry reindex`
indexes an object, mutating its file then resolving with a connection
raises `RegistryIntegrityError` naming both digests; `awf registry retire`
then resolving raises `RegistryBlockedError`; `awf registry trust ...
--status local` restores the row's status but resolution still raises
`RegistryIntegrityError` until a fresh `reindex` accepts the mutated
content; publishing a Voice Profile through `awf registry publish --kind
voice-profiles` round-trips; `awf run demo` (no `@version`) resolves and
records `demo@1.0.0` in `runs.workflow_ref`.

One deviation from this record's own prose: `awf run start --workflow
<name>` doesn't exist as written — the real CLI is the pre-existing `awf run
<workflow>` positional, no `run start` subcommand. Rather than restructure
`run`/`status`/`resume` into a subcommand group this record doesn't
otherwise specify, the existing positional now accepts a bare name in
addition to `name@version`, reaching the same latest-version resolution the
Acceptance criteria describe with no CLI surface change and no test broken.

Covers Task A (items 1–4) and Task D (items 10–12) of the registry cohesion
review. Depends on ADR-0011, which gives this record the kind vocabulary it
indexes over.

## Context

**`registry_index` is an integrity and trust ledger.** The table carries
`kind`, `name`, `version`, `digest`, `source`, `path`, `trust_status`, and
`indexed_at`, keyed on `(kind, name, version)`. Current writers are
`core_ops.op_registry_publish` and `registry reindex`. Resolution walks the
filesystem, then verifies an indexed row when a connection is supplied or the
repo DB already exists. Historical consequences from the pre-ADR state were:

- `digest` is computed at publish and compared against nothing afterward.
- `trust_status` is written as the literal `'local'` at every publish. The
  schema admits `'trusted'`, `'quarantined'`, and `'blocked'`; nothing
  produces or reads them.
- `source` is always `'data'`, because a `config/app_registry/` object is
  never indexed.
- `op_registry_list` re-walks both roots rather than querying the table.

**A stray file locks resolution.** `resolve_registry_object` treats
`data_dir.is_dir() and any(data_dir.iterdir())` as "this name is operator-
owned," and from there `config/app_registry/` is not consulted for that name.
Any file satisfies `any()` — a `.gitkeep`, an editor swap file, a partial
download. The resulting error says the name is present in `data/`, which is
true and unhelpful.

**Publishing covers five kinds of seven.** Workflows, capabilities, MCP
servers, agent manifests, and skills carry their own `name` and `version` in
content. Voice Profiles and Model Profiles do not — both derive name and
version entirely from their path — so `op_registry_publish` raises rather
than publish them. An operator adds a voice or a model profile by writing
files.

**Every reference must name an exact version.** `resolve_registry_object`
takes `version` and there is no way to ask for the newest. A second version of
a workflow is invisible until every caller is edited.

**Publishing is one-way.** There is no unpublish, no delete, and no way to
retire a version.

**`op_registry_get` returns raw text.** `{"kind", "name", "version",
"source", "content"}` where `content` is `path.read_text()`. A caller that
wants structure re-parses.

**A workflow declares a self-digest.** `WorkflowMetadata` requires `digest`,
and current `op_registry_validate` / `op_registry_publish` compare it against
the SHA-256 of the normalized Workflow YAML with `metadata.digest` blanked.
The registry index still records the SHA-256 of the final file bytes.

## Decision

**The index becomes a catalog and an integrity check, not the resolver.** The
filesystem stays the resolution source of truth. The index gains a rebuild
that covers both roots, and resolution verifies a resolved file against its
indexed digest when a row exists.

**`trust_status` gets a producer and one consumer.** Repository defaults
index as `trusted`; operator publishes index as `local`; an operator command
sets `quarantined` or `blocked`. Resolution refuses a `blocked` object.

**A name is operator-owned when it holds a real object, not a file.**
Shadowing keys on at least one resolvable version, not on directory
non-emptiness.

**Every kind publishes.** Voice Profiles and Model Profiles gain `name` and
`version` fields, so all seven kinds are self-describing and one publish path
serves them all.

**Latest-version resolution is available and never implicit.** A caller may
ask for the newest version of a name; what it receives is a concrete version
that it then uses everywhere, so nothing durable records an unpinned
reference.

**Retirement is a status, not a deletion.** `awf registry retire` marks a
version `blocked`; the file stays for audit.

**`op_registry_get` returns the parsed object alongside the raw text.**

**Workflow declared digests are enforced at validate/publish time.** A
Workflow whose `metadata.digest` does not match its normalized payload is
rejected before it can be published. This is distinct from the registry index
digest, which pins the exact bytes stored on disk after publication.

Corrective update, 2026-08-12: a present-but-malformed Workflow
`metadata.digest` is now rejected. Missing digest remains a Workflow schema
error; a present value must be a `sha256:<hex>` string before normalized
self-digest comparison runs.

## Rationale

The index is the shape a catalog needs and currently performs no function.
Two of its columns describe properties — content integrity and trust — that
the system claims elsewhere to care about, and neither is checked. Giving
each one a producer and a consumer is what converts the table from a record of
publishes into part of the resolution path.

Making the index a cache in front of the filesystem was the alternative, and
it trades a real problem for a harder one: a stale cache resolves an object
that is no longer there. Verification does not have that failure mode — an
absent row means no check, a present row means a check, and neither can
resolve something the filesystem does not hold.

Version pinning stays absolute where it matters. A Run records the exact
version it executed, so resume is deterministic; latest-version lookup happens
before the Run exists and produces the pin.

## Deviation recorded

| Requirement | Deviation | Compensating control |
|---|---|---|
| Section 11, Model Profile schema; Section 16.5, Voice Profile schema | both gain required `name` and `version` fields | the values MUST match the object's publish path, checked on load; every other registry kind already carries its own identity in content, so this removes the exception rather than adding one |
| Section 9.3: registry resolution reads `data/registry/` then `config/app_registry/` | resolution additionally refuses an object whose indexed `trust_status` is `blocked` | refusal is an explicit operator act recorded in the index and reported by name; an unindexed object is resolved exactly as it is today |

## Mechanism

### Task A — integrity, shadowing, coverage, and version lookup

**Reindex.** `registry/index.py`:

```python
reindex(repo_root, conn) -> dict          # counts by kind and source
index_row(conn, kind, name, version) -> dict | None
set_trust_status(conn, kind, name, version, status) -> dict
```

`reindex` walks both registry roots over `kinds.KINDS`, computes each
object's digest, and upserts one row per object. `source` is `config` or
`data` as found. `trust_status` defaults to `trusted` for `config` rows and
`local` for `data` rows, and an existing non-default status is preserved
across a rebuild. For a skill, the digest is `skill.directory_digest`; for
every other kind it is the SHA-256 of the file bytes, matching what
`op_registry_publish` already computes.

`awf registry reindex` exposes it. `op_registry_publish` keeps writing its own
row, so a publish never requires a rebuild.

**Integrity on resolution.** `resolve_registry_object` has an optional
connection. When one is supplied, or when none is supplied but the repository
DB already exists, and a row exists for the resolved `(kind, name, version)`,
the file's digest is recomputed and compared:

- match — resolution proceeds;
- mismatch — `RegistryIntegrityError`, naming both digests and the path;
- `trust_status == "blocked"` — `RegistryBlockedError`, naming the object;
- no row — resolution proceeds unchecked, preserving bootstrap/fresh-checkout
  behavior before the object is indexed.

Callers that already hold a connection pass it. Conn-less callers still get
index enforcement whenever `data/awf_db/awf.db` exists.

**Shadowing on objects, not files.** The `any(data_dir.iterdir())` test
becomes `any(version_names(data_dir, kind))` — a name is operator-owned when
`data/registry/<kind>/<name>/` holds at least one file matching that kind's
layout. A directory holding only a `.gitkeep` or a partial download falls
through to `config/app_registry/` as it should.

**Seven publishable kinds.** Voice Profile and Model Profile YAML gain
top-level `name` and `version`:

```yaml
name: narrator
version: 1.0.0
persona:
  ...
```

`parse_voice_profile` and `parse_model_profile` require them and expose
`ref`, matching the other five. `load_*` verifies that the parsed `name` and
`version` match the file's own path, which is the rule `load_skill` already
applies to `SKILL.md`. The four shipped Voice Profiles and five example Model
Profiles gain the two fields. `op_registry_publish` then handles all seven
kinds through one path, keyed on `kinds.by_key`.

**Latest-version lookup.**

```python
latest_version(repo_root, kind, name) -> str
```

Versions are compared as dotted integer tuples, highest wins; a version that
does not parse as dotted integers sorts below every one that does. Lookup
searches `data/registry/` first and falls back to `config/app_registry/`,
matching resolution's own precedence.

`awf run start --workflow <name>` without `@version` resolves the latest and
records the concrete `name@version` in `runs.workflow_ref`. Nothing durable
stores an unpinned ref, so `awf run resume` re-resolves the exact version it
ran, unaffected by a later publish.

### Task D — lifecycle, structure, and trust

**Retire.** `op_registry_retire(repo_root, conn, *, kind, name, version)` sets
that row's `trust_status` to `blocked` and returns the row. The file is not
removed: an audit trail that deletes its own evidence is not one. A retired
version fails resolution with `RegistryBlockedError`; `op_registry_list`
shows it with its status. `op_registry_trust(..., status)` sets any of the
four values, so retirement is reversible by the same command.

`awf registry retire <kind> <name> <version>` and
`awf registry trust <kind> <name> <version> --status <status>` expose both.

**Structured get.** `op_registry_get` returns its current keys plus
`digest`, `trust_status`, and `object` — the parsed dataclass rendered as a
mapping, by way of the kind's own loader. `content` stays, so no existing
caller breaks.

**Trust in listing.** `op_registry_list` keeps walking the filesystem, which
is the only view that cannot go stale, and joins `trust_status` and `digest`
from the index per row. A row absent from the index reports
`trust_status: null`, which is the signal to run `reindex`.

## Layout delta

```text
backend/src/awf/
  registry/
    index.py            (new: reindex, index_row, set_trust_status, latest_version)
    resolve.py          (optional conn; digest check; blocked refusal; object-based shadowing)
    voice_profile.py    (name/version required; ref; path agreement)
    model_profile.py    (name/version required; ref; path agreement)
  cli/
    core_ops.py         (publish all seven kinds; retire; trust; structured get; list joins index)
    main.py             (`registry reindex`, `registry retire`, `registry trust`; `run start` without @version)

config/app_registry/
  voice-profiles/*/1.0.0.yaml    (name/version added)
  model-profiles/*/1.0.0.yaml    (name/version added)
```

## The tradeoffs accepted

- The digest check costs one file read and one hash per indexed resolution
  with a supplied or auto-opened connection. Registry objects are small, and
  the check is skipped entirely when no row exists or no repo DB exists yet.
- Two shipped schemas gain required fields, so an existing operator-authored
  Voice Profile or Model Profile fails to load until the two lines are added.
  The failure names the missing field and the file.
- Latest-version lookup introduces a second way to name an object. It is
  confined to the moment before a Run exists; every durable reference stays
  pinned, and resume behavior does not change.
- Retirement leaves the file in place, so a blocked object still occupies its
  path and still appears in a listing. That is the point — the record of what
  was withdrawn is the reason to withdraw it through the index rather than
  with `rm`.

## Scope for implementation

1. Add `registry/index.py` with `reindex`, `index_row`, `set_trust_status`,
   and `latest_version`.
2. Add the optional connection, digest verification, blocked refusal, and
   object-based shadowing to `resolve_registry_object`; add
   `RegistryIntegrityError` and `RegistryBlockedError`.
3. Add required `name` and `version` to the Voice Profile and Model Profile
   schemas, with path agreement on load and a `ref` property; update the four
   shipped Voice Profiles and five example Model Profiles.
4. Extend `op_registry_publish` to all seven kinds through `kinds.by_key`.
5. Add `op_registry_retire` and `op_registry_trust`; add `digest`,
   `trust_status`, and `object` to `op_registry_get`; join the index into
   `op_registry_list`.
6. Add `awf registry reindex`, `awf registry retire`, and
   `awf registry trust`; accept `--workflow <name>` without a version on
   `awf run start` and record the resolved pin.
7. Tests: reindex covers both roots and every kind; a mutated file fails
   resolution with a digest mismatch; a blocked object fails resolution; a
   `.gitkeep`-only data directory falls through to config; each of the seven
   kinds publishes and round-trips; `latest_version` orders dotted integers
   and tolerates a non-numeric version; a Run started without a version
   records a pinned ref and resumes to the same version after a newer one is
   published; retire then trust restores resolution.
8. Run all six `scripts/validate_backend.py` commands.

## Acceptance

- `awf registry reindex` writes one row per object across both roots, with
  `source` reflecting where each was found.
- A file edited after publish fails resolution with an error naming both
  digests; reindexing accepts the new content.
- An object marked `blocked` fails resolution; marking it `local` or
  `trusted` restores it.
- `data/registry/<kind>/<name>/` containing only a `.gitkeep` resolves to the
  `config/app_registry/` object for that name.
- All seven kinds publish through `awf registry publish`, and a published
  Voice Profile resolves and drives a voice round trip.
- `awf run start --workflow <name>` with no version starts the newest and
  records `name@version` in `runs.workflow_ref`; publishing a newer version
  afterward does not change what `awf run resume` executes.
- `op_registry_get` returns `digest`, `trust_status`, and a parsed `object`
  alongside `content`.
- `op_registry_list` reports `trust_status` per row, and `null` for an object
  the index has not seen.
- `pytest backend/tests` matches or exceeds the pre-change pass count with the
  same or fewer skips.

## Consequences

- The digest recorded at publish is checked at use.
- `trust_status` becomes an operator control with an effect, and the
  `quarantined` value is available for the isolation tier that will consume
  it.
- A repository default and an operator publish are distinguishable in the
  index by `source`, which is the fact a control center needs to display.
- Retiring a version is recorded rather than performed with a file deletion.
- An operator, and later the system itself, can publish every registry kind
  through one command.

## Open decisions

- **`WorkflowMetadata.digest` scope beyond publish/validate.** Current code
  treats it as a normalized YAML self-digest with the digest field blanked,
  enforced by validate and publish. The registry index remains the runtime
  integrity check for exact file bytes.
