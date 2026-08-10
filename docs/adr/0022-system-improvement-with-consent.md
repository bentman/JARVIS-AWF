# ADR-0022: system improvement with consent

## Status

Implemented.

Acceptance run: `backend/.venv/bin/python -m pytest backend/tests -q` outside
the Codex sandbox -> 559 passed, 7 warnings; `backend/.venv/bin/python -m ruff
check .` passed; `npm --prefix frontend run build --workspaces` passed; `npm
--prefix frontend test --workspaces` passed.

## Context

`docs/archives/ProjectVisionAWF.md` defines the fifth promise as AWF pointed
at its own repository: a Run creates an isolated worktree, an agent proposes a
change, a gate verifies it, the operator reviews a diff, and only an operator
approval merges it. The boundary is exact: AWF never merges its own change.

The current codebase already has the core pieces:

- `awf.isolation.worktree` creates one Git worktree per mutating Run and can
  report the most recent committed diff.
- `awf.workflow.engine` and `awf.cli.core_ops.op_run_start` run published
  Workflows against a resolved registry object.
- `awf.gates.gate_node` writes deterministic Verdict artifacts from verifier
  and adversary Findings.
- `awf.workflow.approval` and `awf.machine.approvals` bind approvals to exact
  action digests.
- `awf.authoring.workflow` creates registry proposals that remain drafts until
  a caller publishes them with the current draft digest.
- `awf.cli.core_ops.op_registry_publish` writes durable registry objects under
  `data/registry/`.
- `frontend/shared`, `frontend/cli`, and `frontend/gui` already expose
  proposal, approval, artifact, and run surfaces over JSON-RPC rather than
  reading durable state directly.

The missing shape is the self-improvement closeout path. A Run can produce
commits inside its worktree, and a gate can review the last commit diff, but
there is no first-class Improvement Proposal that records:

- the target repository and base commit;
- the candidate branch/worktree commit;
- the exact reviewed diff digest;
- the validation evidence and Verdict artifact;
- the operator decision bound to that reviewed diff;
- the merge result after approval.

Provider and community practice aligns with this boundary:

- Codex app-server approval flows carry the proposed command or diff to the UI,
  require a client decision, and scope the request to the active turn:
  <https://github.com/openai/codex/blob/main/codex-rs/app-server/README.md>
- Claude Code treats permissions and sandboxing as complementary controls:
  permission rules decide tool access while OS sandboxing constrains command
  effects:
  <https://code.claude.com/docs/en/permissions>
- Claude Code security reviews are positioned as review support that
  complements existing security and manual review practices:
  <https://support.claude.com/en/articles/11932705-automated-security-reviews-in-claude-code>
- MCP requires explicit user consent and clear review UI before tool access or
  tool invocation:
  <https://modelcontextprotocol.io/specification/2025-03-26/index>
- GitHub branch protection practice separates generated changes from merge
  authority with pull request reviews, status checks, stale-review handling,
  and branch restrictions:
  <https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches>

## Decision

**Self-improvement is a normal Run with a special target.** AWF improves its
own repository by running a published Workflow against the repository worktree
through the existing engine, adapter, guard, gate, and approval paths.

**The durable object is an Improvement Proposal.** Add a lightweight
`improvement_proposals` table, plus event rows, for repository diffs produced
by Runs. This is separate from `registry_proposals`, which is scoped to
registry objects such as Workflows and Semantic Memories.

**The reviewed diff is the approval unit.** An Improvement Proposal stores a
canonical diff digest computed from the candidate diff between the base commit
and candidate commit. Any new commit changes the digest and requires a fresh
operator decision.

**Verification precedes merge approval.** The proposal can enter
`ready_for_review` only after the associated Run has a passing Gate Verdict and
the validation evidence artifacts are attached. A failed, missing, or stale
Verdict prevents merge approval.

**AWF never merges its own change.** The core may prepare a merge candidate and
record an approval request, but merge execution requires an explicit operator
approval whose action digest includes the base commit, candidate commit, target
branch, diff digest, and validation evidence refs.

**Merge approvals are normal approval rows.** A merge approval is attached to a
dedicated Step row for the source Run. It is not a detached approval record.
This keeps approval listing, approval detail, event history, and voice-approval
rules on the same database contract as existing workflow and machine-action
approvals.

**Frontend surfaces remain presentation only.** CLI and GUI may show the
proposal, diff summary, artifacts, approval preview, and final merge result.
They must call JSON-RPC methods and must not run Git operations directly.

**External PR integration is optional.** The first implementation closes the
local repository loop. A later GitHub or other forge integration can publish
the same Improvement Proposal as a pull request, but it must not replace the
local approval and digest checks.

## Rationale

The fifth promise does not need a separate self-updating subsystem. AWF already
has the required primitives: isolated worktrees, durable runs, gate verdicts,
approval rows, artifacts, and frontend approval displays. The gap is a durable
record that connects those primitives around a repository diff.

Keeping the approval unit as the exact reviewed diff matches the security
model used elsewhere in AWF. It prevents a passing review of one commit from
authorizing a different commit.

Separating Improvement Proposals from registry proposals avoids overloading a
registry-object draft table with repository merge semantics. Registry proposals
publish data objects; improvement proposals merge code/config/docs changes.

## Deviation recorded

| Requirement | Deviation | Compensating control |
|---|---|---|
| Section 16.3 JSON-RPC method list has no improvement proposal surface | Adds improvement proposal methods | Methods map to core operations only; frontends still do not read `data/` or run Git |
| Current approval rows can approve a generic workflow action | Adds a merge-action digest that includes exact Git identities and diff digest, attached to a dedicated merge-review Step | Any changed candidate commit or target branch invalidates the approval while preserving the existing `approvals.step_id` contract |
| Current gate reviews the latest commit diff but does not bind that diff to a merge proposal | Stores the reviewed diff digest and Verdict artifact on the Improvement Proposal | Merge approval requires matching digest and passing Verdict |
| Current worktree cleanup removes successful Run worktrees | Self-improvement Runs retain the candidate worktree/branch until proposal closeout | Closed proposals can clean up the branch/worktree after merge or rejection |

No change is made to the existing Run state machine, registry resolution order,
adapter contract, or frontend authority model.

## Mechanism

### Task A — Improvement proposal storage

Add durable tables:

```sql
CREATE TABLE improvement_proposals (
    improvement_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs (run_id),
    target_repo TEXT NOT NULL,
    target_branch TEXT NOT NULL,
    base_commit TEXT NOT NULL,
    candidate_branch TEXT NOT NULL,
    candidate_commit TEXT NOT NULL,
    diff_digest TEXT NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('draft', 'ready_for_review', 'approved', 'merged', 'rejected', 'abandoned')
    ),
    summary TEXT NOT NULL,
    verdict_artifact_id TEXT,
    validation_artifact_ids_json TEXT NOT NULL,
    merge_commit TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    decided_at TEXT,
    closed_at TEXT
);

CREATE TABLE improvement_proposal_events (
    event_id TEXT PRIMARY KEY,
    improvement_id TEXT NOT NULL REFERENCES improvement_proposals (improvement_id),
    event_type TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    actor TEXT NOT NULL,
    payload_json TEXT NOT NULL
);
```

The `target_repo` value is the repository root relative to AWF's current root
for local self-improvement. Absolute operator paths are not stored in
application defaults.

### Task B — Diff identity and artifact capture

Add `awf.improvement.diff` helpers:

- resolve the current repository HEAD as `base_commit` when the improvement
  Run starts;
- compute candidate commit from the Run worktree;
- compute a canonical `git diff --binary <base_commit> <candidate_commit>`
  digest;
- write the diff as an artifact;
- summarize changed paths and line counts for frontend display.

The canonical digest uses Git output bytes and a `sha256:` prefix. If the
candidate branch is rebased or amended, the digest changes.

### Task C — Core operations

Add core operations:

- `op_improvement_prepare(repo_root, conn, run_id, summary=None)`:
  creates or updates a draft Improvement Proposal from a terminal Run worktree;
- `op_improvement_get(conn, improvement_id)`:
  returns proposal metadata, changed-path summary, approval state, and artifact
  refs;
- `op_improvement_list(conn, status=None)`:
  returns proposal summaries;
- `op_improvement_mark_ready(conn, improvement_id, verdict_artifact_id,
  validation_artifact_ids)`:
  moves a proposal to `ready_for_review` only when the linked Verdict passes;
- `op_improvement_request_merge(repo_root, conn, improvement_id)`:
  creates or reuses a dedicated merge-review Step for the proposal's Run, then
  creates a pending R2 approval for the exact merge action;
- `op_improvement_merge(repo_root, conn, improvement_id, approval_id)`:
  validates the approval, rechecks base/candidate/diff identities, performs the
  merge, records the merge commit, and closes the proposal;
- `op_improvement_reject(conn, improvement_id, reason)`:
  records operator rejection and keeps evidence available.

Merge execution uses existing Git helpers where possible. Any merge conflict
fails without choosing a side and leaves the proposal unmerged for operator
resolution.

### Task D — Workflow entry point

Add a default application Workflow under
`config/app_registry/workflows/self-improvement/1.0.0.yaml`.

Initial shape:

1. `agent` node: implement the requested improvement in the Run worktree.
2. `gate` node: run focused validation and independent review against the
   produced diff.

Proposal preparation and merge approval are explicit closeout operations after
the Run completes. That keeps merge authority out of the Workflow itself while
still binding the final operator approval to the exact reviewed diff.

The Workflow is a repo default, not operator data. Operators can copy and
override it under `data/registry/workflows/` if they need different validation
coverage.

### Task E — JSON-RPC and frontend surfaces

Extend the JSON-RPC method surface with:

- `awf/improvement.list`
- `awf/improvement.get`
- `awf/improvement.prepare`
- `awf/improvement.markReady`
- `awf/improvement.requestMerge`
- `awf/improvement.merge`
- `awf/improvement.reject`

CLI slash commands:

- `/improvements`
- `/improvement <id>`
- `/improvement-prepare <run-id>`
- `/improvement-request-merge <id>`
- `/improvement-merge <id> <approval-id>`
- `/improvement-reject <id> <reason>`

GUI additions stay limited to proposal inspection, diff preview, linked
artifacts, approval state, and merge/reject controls.

### Task F — Cleanup policy

Successful ordinary Runs may continue to remove their worktree. A Run whose
Workflow ref resolves to `self-improvement@...`, or whose input explicitly
sets `{"retainWorktreeForImprovement": true}`, keeps its worktree and
candidate branch while the Improvement Proposal is `draft`,
`ready_for_review`, or `approved`.

After `merged`, `rejected`, or `abandoned`, cleanup may remove the worktree and
candidate branch after the proposal records enough Git identity and artifact
evidence to audit the decision.

## Validation

Focused backend tests:

- proposal creation from a committed Run worktree records base commit,
  candidate commit, branch, diff digest, and diff artifact;
- re-running prepare after an amended candidate updates the digest and records
  an event;
- ready-for-review rejects a failed Verdict;
- merge requests create R2 approvals whose action digest matches the proposal's
  current merge action;
- merge refuses unapproved approval rows;
- changed candidate commits invalidate the previous merge approval;
- rejection closes the proposal without merging;
- worktree cleanup retains candidate branches until proposal closeout.

Frontend tests:

- shared protocol exposes improvement methods and types;
- CLI commands call the protocol client with exact ids/digests;
- GUI renders improvement proposal diff summary, artifacts, and approval state
  without reading files directly.

Milestone checks:

```bash
backend/.venv/bin/python -m ruff check .
backend/.venv/bin/python -m pytest backend/tests -q
npm --prefix frontend run build --workspaces
npm --prefix frontend test --workspaces
git diff --check
```

Live validation:

- Run `self-improvement@1.0.0` against a harmless repo-local change only from
  an intentionally clean real checkout, or use a temporary Git repository for
  live proof while this checkout has unrelated work in progress.
- Confirm the candidate diff is visible before merge approval.
- Confirm approval is bound to the exact diff digest.
- Confirm merge produces a merge commit only after explicit operator approval.
- Confirm a changed candidate commit invalidates the old approval.

Live commands that depend on host reach outside the Codex sandbox must be run
outside the sandbox and reported separately from unit/integration evidence.

## Implementation

Implemented on 2026-08-09.

- Added durable Improvement Proposal storage, proposal events, diff digesting,
  changed-path summaries, and patch artifact capture.
- Added core, CLI, JSON-RPC, shared TypeScript protocol, AWF-CLI, and AWF-GUI
  surfaces for proposal prepare, review, merge request, merge, and rejection.
- Added merge approvals as R2 approval rows attached to dedicated merge-review
  Step rows.
- Added self-improvement Run worktree retention for `self-improvement@...`
  workflows and explicit `retainWorktreeForImprovement` input.
- Added the default `self-improvement@1.0.0` application Workflow.

## Acceptance criteria

- AWF can create an Improvement Proposal from a Run that changed this repo in
  an isolated worktree.
- The proposal exposes the exact diff, candidate commit, validation artifacts,
  and Gate Verdict.
- AWF cannot merge the proposal without an operator approval bound to the exact
  reviewed diff digest.
- A changed candidate commit or target branch invalidates the merge approval.
- CLI and GUI can inspect and close the proposal through JSON-RPC only.
- Rejection and merge both preserve enough evidence to reconstruct what was
  proposed, reviewed, and decided.
