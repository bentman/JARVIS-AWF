# ADR-0010: setup flag dispatch, and repository surface cleanup

## Status

Proposed. Not implemented.

Five independent tasks. Task A changes behavior; the rest remove surfaces that
name things this repository does not contain.

## Context

**`awf-setup` silently drops flags.** `run()` evaluates `--provision`,
`--install`, and `--verify` in sequence and returns on the first match, so
`awf-setup --provision --verify` runs provision, prints nothing about
verification, and exits `0`. The three commands are independent reports over
the same host; combining them is the natural way to use them.

**Two directories hold a `.gitkeep` and nothing else.** `config/hardware/` —
no module builds a path under it; ADR-0008 placed the profile, provision,
preflight, and readiness stages in `backend/src/awf/hardware/`.
`models/llm/` — model access is LiteLLM endpoints declared per Model Profile,
so no local weights are stored; the repository layout names
`models/{stt,tts,vad,wake}`.

**`cache/temp/`** is created by `setup.bootstrap_repo` through
`paths.temp_dir`. The layout names `cache/sandbox/<run_id>/` as cache's
content.

**`.gitignore` carries rules for paths this repository does not contain:**
`/desktop/node_modules/`, `/desktop/dist/`, `/desktop/src-tauri/target/`,
`/desktop/src-tauri/gen/`, `/docker-compose.override.yml`,
`/runtimes/llama.cpp/*`, `/**/llama-server`, `/**/llama-server.exe`,
`/reports/tests/*`, `!/reports/tests/.gitkeep`, and
`!/reports/validation/slice_h`. Two section comments name absent things: the
cache header reads "Redis local persistence, temp outputs", and the data
re-include block refers to "tree roots documented in repo_tree.md".

**Five registry directories carry a `.gitkeep` alongside real content:**
`config/app_registry/{agents,capabilities,mcp,voice-profiles,workflows}`.
`skills/` is the one that is still empty.

**The MCP registry directory is lowercase.** `config/app_registry/mcp/` and
`data/registry/mcp/` on disk, `"mcp"` as the kind string in
`resolve.resolve_registry_object` and `core_ops.op_registry_publish`, and
`/data/registry/mcp/` in `.gitignore`. The repository layout spells it
`MCP`.

**`README.md`'s Status section** states that implementation has not started.

## Decision

**Task A — `awf-setup` runs every requested flag.** Each of `--provision`,
`--install`, and `--verify` executes in that order when given, and the
command returns the highest exit code any of them produced.

**Task B — remove `config/hardware/` and `models/llm/`,** with their
`.gitignore` rules.

**Task C — remove `cache/temp/`** once its only consumer is confirmed to be
`setup.bootstrap_repo`'s `mkdir`: the directory, its `.gitignore` rules, and
`paths.temp_dir`.

**Task D — prune `.gitignore`** of the rules and comments naming absent
paths.

**Task E — remove the five stale `.gitkeep` files,** keeping
`config/app_registry/skills/.gitkeep`, and replace `README.md`'s Status
section with an accurate one.

**`mcp` stays lowercase.** Every occurrence agrees with every other; the
divergence is between the repository and the layout's spelling, and it is
recorded below rather than changed.

## Rationale

A rule for a path that cannot exist is a claim about the repository that
does not hold, and an empty directory is a claim that something belongs
there. Both cost a reader time and neither is load-bearing.

Task A is the one behavioral item: a command that accepts a flag and ignores
it reports success for work it did not do.

Lowercase `mcp` is consistent across the tree, the ignore rules, and both
kind-string call sites. Changing it would touch three surfaces to match a
spelling that appears in one sentence of the layout; recording it costs a
table row.

## Deviation recorded

| Requirement | Deviation | Compensating control |
|---|---|---|
| Section 7 layout: `config/app_registry/MCP/` | `mcp/` lowercase, in both registry roots, in the `.gitignore` rules, and as the kind string in `resolve_registry_object` and `op_registry_publish` | one spelling throughout; registry resolution keys on the same string in both roots, so no path is constructed from a second casing |

Removing `config/hardware/`, `models/llm/`, and `cache/temp/` moves toward
the stated layout: the layout names none of them, and it admits no
placeholder directories.

## Mechanism

### Task A — flag dispatch

```python
def run(argv: list[str], repo_root: Path) -> int:
    args = build_parser().parse_args(argv)

    commands = []
    if args.provision:
        commands.append(cmd_provision)
    if args.install:
        commands.append(cmd_install)
    if args.verify:
        commands.append(cmd_verify)

    if not commands:
        bootstrap_repo(repo_root)
        print(f"AWF bootstrap complete: {db_path(repo_root)}")
        return 0

    return max(command(repo_root) for command in commands)
```

Order is fixed at provision, install, verify, so `--verify --install` runs
the install before the verification that reports on it. Each command keeps
printing its own labelled output, so a combined invocation reads as
consecutive reports.

### Task B — unused directories

Remove `config/hardware/` and `models/llm/`, and the `.gitignore` pair
`/models/llm/*` and `!/models/llm/.gitkeep`. Nothing imports a path under
either.

### Task C — `cache/temp/`

Confirm that `paths.temp_dir` is imported only by `setup.py` and that no
module writes under `cache/temp/`. When confirmed: remove the directory, the
`.gitignore` rules `/cache/temp/*`, `!/cache/temp/`, `!/cache/temp/.gitkeep`,
`paths.temp_dir`, and its call in `bootstrap_repo`. When a consumer is found,
leave all of it and record the consumer.

### Task D — `.gitignore`

Remove: the Desktop/Tauri section and its four rules; the Docker overrides
section and `/docker-compose.override.yml`; `/runtimes/llama.cpp/*`,
`/**/llama-server`, `/**/llama-server.exe`; `/reports/tests/*` and
`!/reports/tests/.gitkeep`; `!/reports/validation/slice_h`.

Reword two comments: the cache section header to name `cache/`'s actual
contents, and the data re-include comment to drop the `repo_tree.md`
reference while keeping the ordering note, which is load-bearing —
directories must be re-included before their contents.

Everything else stays. The per-folder model allowlist, the `data/` base gate
and its re-include block, the `*.bak` rule, and the binary-extension list are
all in use.

### Task E — placeholders and README

Remove `.gitkeep` from `config/app_registry/agents/`, `capabilities/`,
`mcp/`, `voice-profiles/`, and `workflows/`; keep `skills/.gitkeep`, which is
the only one of the six still empty. The `data/registry/` and `reports/`
`.gitkeep` files stay: their directories are ignored, and the placeholder is
what keeps them in the tree.

Replace `README.md`'s Status section with one describing what the repository
contains, and add a `Quick Start` section after the description.

## Layout delta

```text
config/
  hardware/                        (removed)
  app_registry/
    agents/.gitkeep                (removed)
    capabilities/.gitkeep          (removed)
    mcp/.gitkeep                   (removed)
    voice-profiles/.gitkeep        (removed)
    workflows/.gitkeep             (removed)
    skills/.gitkeep                (kept - still empty)
models/
  llm/                             (removed)
cache/
  temp/                            (removed, pending Task C confirmation)
.gitignore                         (rules for absent paths removed)
README.md                          (Status rewritten, Quick Start added)
backend/src/awf/
  setup.py                         (run() executes every requested flag)
  paths.py                         (temp_dir removed with Task C)
```

## The tradeoffs accepted

- `max()` over exit codes reports the worst outcome of a combined
  invocation, which means a failing `--verify` masks a successful
  `--provision` in the exit code alone. The printed output distinguishes
  them.
- Removing `models/llm/` closes the door on local LLM weights living in the
  repository. Adding it back is a directory and two ignore rules if a local
  runtime is ever introduced.
- Keeping `mcp` lowercase leaves one sentence of the layout unmatched.
  Changing it would touch the two registry trees, the ignore rules, and two
  kind-string call sites.

## Scope for implementation

1. Rewrite `setup.run()` to execute every requested flag and return the
   highest exit code.
2. Remove `config/hardware/` and `models/llm/` with their ignore rules.
3. Confirm `temp_dir` has no consumer beyond `setup.bootstrap_repo`; if
   confirmed, remove `cache/temp/`, its ignore rules, `paths.temp_dir`, and
   its call site.
4. Prune `.gitignore` per Task D and reword the two comments.
5. Remove the five stale `.gitkeep` files.
6. Replace `README.md`'s Status section and add `Quick Start`.
7. Tests: `run(["--provision", "--verify"], root)` invokes both commands;
   `run([], root)` still bootstraps; a failing command's code is what a
   combined invocation returns.
8. Run all six `scripts/validate_backend.py` commands, and
   `awf-setup --provision --verify` as one invocation.

## Acceptance

- `awf-setup --provision --verify` prints both reports in one invocation.
- `awf-setup` with no flags still creates `.env`, `cache/sandbox/`, and the
  database.
- `config/hardware/`, `models/llm/`, and `cache/temp/` are absent, and no
  `.gitignore` rule names them.
- No `.gitignore` rule names a path absent from the repository.
- `config/app_registry/` holds one `.gitkeep`, under `skills/`.
- A fresh clone produces the same `data/registry/` and `reports/` directory
  skeleton it does today.
- `README.md`'s Status section describes the repository's actual state, and a
  `Quick Start` section follows the description.
- `pytest backend/tests` matches or exceeds the pre-change pass count with the
  same or fewer skips.

## Consequences

- A combined `awf-setup` invocation does everything it was asked to do.
- Every directory in the tree holds something, and every ignore rule names a
  path that can exist.
- The first section a reader reaches in `README.md` describes what is there.
- `mcp` has one spelling, recorded as diverging from the layout's.