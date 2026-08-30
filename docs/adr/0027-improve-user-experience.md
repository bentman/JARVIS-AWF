# ADR-0027: improve operator user experience for proposal review and run closeout

## Status

Accepted. Implemented and validated (Aug 30, 2026).

This record treats the AWF operator as the primary customer for the product. The
user is not a developer reading JSON or a database row; they are a person who
must decide whether a proposal is safe, relevant, and worth approving. The
source of truth remains the code and the durable trace: the UX must surface the
same evidence without forcing the operator through a long chain of internal
inspection.

**Implementation complete:**
- ✅ 5-point narrative summary layer (what/where/validation/why/next-action)
- ✅ Compact diff preview with file counts and line-by-line context
- ✅ Explicit next-action framing in both CLI and GUI
- ✅ Approval workflow UI with Approve/Reject buttons
- ✅ No archaeology required: operator can review fully within the tool
- ✅ All tests passing (8 summary + 6 CLI + 7 integration)

## Context

The AWF core already records the high-value evidence we need: run status,
validation artifacts, candidate worktrees, exact diff digests, patch artifact
IDs, and merge approvals. This is enough for a reliable safety gate.

What is missing is the product-grade experience: the operator cannot easily tell
what changed, why it changed, how risky it is, and what the next action is.
Worse, the current flow still leaves the operator asking, "what did AWF actually
propose?" long after the run succeeded.

The current human path is not equivalent to a modern agentic or AI-assisted UX:

- success is reported as metadata and artifact references;
- the proposal summary is dense and low-level;
- the run still leaves the operator to discover the actual patch from a
  candidate worktree or raw artifact;
- the operator must infer a plain-English story from JSON, digests, and path
  lists.

This is not a correctness problem. It is a usability problem, and it matters in
practice because the most important decision in self-improvement is the operator's
review. If a review surface does not make the delta obvious, the safety model is
not actually usable.

Several community systems have converged on a similar pattern for usability in
agentic workflows:

- GitHub Copilot and Copilot Chat surface the changed file list, the diff, and a
  compact summary before asking for approval or final review;
- Claude Code, OpenAI Codex, and similar terminal-first agents keep the operator
  in the request/response loop with short status messages, targeted file
  summaries, and explicit next actions;
- Cursor and Continue make the edit and diff review feel like a first-class part
  of the workflow rather than a hidden artifact that must be reconstructed from
  the session state.

The common pattern is simple: show the delta, show the validation, then show the
next action. The operator should not need to reverse-engineer the system to find
that information.

## Decision

**AWF will adopt an operator-first experience for proposal review.** Proposal
review will prioritize plain-language explanation over raw internal state.

### Decision details

**1. Every proposal must have a readable summary.**

A proposal is not just a diff digest and storage record. It is a human review
object. A readable summary must include:

- what changed,
- where it changed,
- whether the change is localized or broad,
- whether validation passed,
- and what the next action is.

The summary will be derived from the same durable evidence the system already
stores: changed paths, patch artifact, verdict artifact, step events, and status.
The summary is not a separate source of truth; it is a presentation layer over
existing facts.

**2. Proposal review must present the diff before approval.**

The operator should see the minimal diff in one screen or command, not a JSON
record that only names the file and counts lines. The default review should show:

- file list,
- short human sentence summarizing the delta,
- compact patch preview,
- result of validation,
- and a clear Accept / Reject action.

The raw artifact remains available under an advanced disclosure path, but the
primary operator experience must not require opening the worktree or querying the
underlying database.

**3. The next action must be explicit.**

Every successful self-improvement run should produce an operator-visible next
step such as:

- review the proposal,
- request merge approval,
- approve the merge,
- reject the proposal,
- or discard the candidate worktree.

This is more important than showing a pass/fail badge alone. Operators do not
need a machine-readable status; they need a clear instruction.

**4. Safety remains intact.**

This UX change does not weaken the merge gate. The exact diff digest, approval
binding, and validation verdict remain required. The UX layer only makes those
facts readable and easier to trust.

**5. The UX must degrade gracefully.**

If the system cannot summarize the diff well, it should still fall back to clear
facts: file list, validation verdict, patch artifact ID, and worktree location.
A degraded but explainable UI is still better than a hidden JSON blob.

**6. Product-grade completion is not reached until the operator can review without archaeology.**

The implementation is not complete when the system has only raw proposal
metadata or a worktree that must be inspected manually. A product-grade outcome
requires an operator to be able to answer, in plain language and without SQL or
repository spelunking, the following questions within the review surface:

- what changed,
- where it changed,
- whether validation passed,
- why the change is safe to consider,
- and what the next operator action is.

If the operator still has to read the internal worktree or query the database to
understand the proposal, the experience is not product-grade and the coding
assistant work is not done.

## Deviation recorded

This decision broadens the concept of "proposal review" beyond raw database
inspection and into the product-facing operating surface. The durability and
safety model stay the same; the operator-facing experience is the changed part.
The implementation should continue to use the same run, artifact, and approval
storage machinery, but must present it as a review surface instead of an internal
debug trace.

## Mechanism

### Part A — summary layer

The improvement object already contains the exact facts needed for human review:
`changed_paths`, `diff_digest`, `status`, `verdict_artifact_id`, and related
approval state. The summary layer should convert this into a compact, natural
language description such as:

- "One file changed: scripts/validate_backend.py. The docstring was updated from
  six commands to eight commands. Validation passed. Proposal is ready for review."

This summary must be generated from the same persisted fields already used for
merge approval, so it is not an independent interpretation layer.

### Part B — diff preview

The raw patch is already stored as a patch artifact. The operator-facing path
should offer a compact preview in the same way that modern coding tools show a
small diff first, then a full file only on demand.

The default view should show:

- file name,
- count of added/deleted lines,
- first few context lines,
- and a "show full patch" disclosure if desired.

This keeps the operator oriented without loading the entire repository diff.

### Part C — default action framing

The next action should be expressed explicitly, not implicitly from a status
string. Example operator prompts:

- "Review this proposal"
- "Request merge approval"
- "Reject this proposal"
- "Discard the worktree"

This is the pattern used by successful agent ecosystems: short, explicit, and
clear.

### Part D — command and UI equivalence

The command UI and GUI should expose equivalent information:

- a summary sentence,
- the changed file list,
- the validation result,
- the diff digest,
- the pending approval state,
- and the exact next step.

If the operator sees the same action flow in either surface, the story becomes
consistent across TUI and GUI.

### Part E — no hidden operational work

The proposal record should no longer force the operator to inspect the
worktree directory to understand the candidate change. The worktree remains a
validation sandbox and a durable object for safety, but it is not the primary
operator review experience.

## Consequences

### Positive

- operators can understand the delta without reading raw JSON;
- proposal review becomes understandable and defensible;
- the safety gate remains intact because the review still points to the exact
  diff digest;
- the workflow feels consistent with mature agentic developer tools;
- the UX supports both trust and explanation instead of just traceability.

### Negative

- additional presentation logic is required above the durable proposal record;
- some summaries may be less precise than raw diff output and need careful
  wording;
- the system must retain a way to show the full patch for advanced review;
- the operator-facing text must be generated from current evidence and cannot be
  a hand-authored summary that drifts from the actual patch.

## Implementation notes

A minimal version of this design should be enough for the first UX pass:

- add a readable summary string to proposal display,
- show changed-file path list and line counts in a friendly format,
- render a compact patch preview or one-file diff preview,
- encode the next action in the UI and TUI output,
- and keep the digest, approval, and verifier evidence in view at all times.

This does not require weakening the approval model. It only requires making the
existing evidence readable to a human operator.

## Implementation completion checklist

### Part A — Summary layer ✅
- `backend/src/awf/improvement/summary.py`: Generates human-readable 5-point narrative
  - `generate_human_summary()`: Single-line change summary
  - `derive_safety_assessment()`: Plain-English safety narrative
  - `derive_scope_classification()`: Localized vs. broad determination
  - `derive_next_action()`: Explicit next step with command
  - `generate_proposal_review_narrative()`: Full 5-point structured review

### Part B — Diff preview ✅
- `frontend/gui/src/renderer/Dashboard.tsx`: Compact diff preview in proposal card
  - File list with path, additions/deletions counts
  - First 6 preview lines per file
  - Collapsible for large diffs
  - Line count summary for each changed file

### Part C — Default action framing ✅
- Next-action section in both CLI and GUI
  - Explicit action label ("review", "request merge", "approve", "merge", "reject")
  - Description explaining the rationale
  - Exact command to execute
- `backend/src/awf/cli/main.py`: CLI formatted 6-point output
- `frontend/gui/src/renderer/Dashboard.tsx`: GUI prominent next-action box

### Part D — Command and UI equivalence ✅
- CLI (`awf improvement review <id>`) shows identical narrative structure
- GUI Dashboard shows matching 5-point layout
- Both surfaces link to same approval binding and verdict

### Part E — Approval workflow ✅
- `frontend/gui/src/renderer/ApprovalsView.tsx`: Approval action UI
  - Approve/Reject buttons for each pending approval
  - Rejection reason form with optional comment
  - Processing states and visual feedback
  - Context showing improvement proposal details
- Protocol methods: `approval_approve()` and `approval_reject()`
- Backend operations in `backend/src/awf/ops/approval.py`
- Frontend handlers wired in `App.tsx` with automatic refresh

### Part E — No hidden operational work ✅
- Operators can review and approve fully within GUI
- No worktree inspection required
- No database queries needed
- All evidence visible in review surface

## Test results

- 8/8 summary generation tests PASS
- 6/6 CLI formatting tests PASS  
- 7/7 integration proposal lifecycle tests PASS
- 0 TypeScript errors in frontend build

## Files modified

- `backend/src/awf/improvement/summary.py`: Narrative generation (already complete)
- `backend/src/awf/cli/main.py`: CLI structured output (already complete)
- `backend/src/awf/ops/approval.py`: Approval operations (verified existing)
- `frontend/gui/src/renderer/Dashboard.tsx`: 5-point proposal review card
- `frontend/gui/src/renderer/ApprovalsView.tsx`: Approval action UI (Approve/Reject buttons)
- `frontend/gui/src/renderer/App.tsx`: Approval handler wiring
- `frontend/shared/src/protocol.generated.ts`: Protocol regeneration

## Related records

- ADR-0022: system improvement with consent
- ADR-0025: control-center look and usability
- ADR-0024: control-center data path

The immediate target was the proposal-review surface, because that is where the
operator enters the system's trust boundary. This ADR is now complete.
