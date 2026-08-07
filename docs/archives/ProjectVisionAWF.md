# ProjectVisionAWF

## Vision

JARVIS-AWF is a local-first agentic system that runs on hardware you own, thinks with a model you host, and acts only through authority you granted.

It should feel less like a chat window with tools bolted on and more like a control center: a place where work is described, delegated, watched, verified, and kept. The operator speaks or types an intent. The system decides what that means, plans it as real work, runs it under isolation, verifies it with an independent reviewer, and records every decision it made along the way.

The distinguishing property is not autonomy. It is that nothing happens without a record of why it was allowed to.

Most assistants started as a conversation and are now growing governance. AWF started as governance and is now growing a conversation. That order is deliberate, and it is the reason this vision reads as it does.

---

## What Already Stands

The foundation is built and running. It is the part most systems overlook.

**A Run is durable.** Work is a graph of typed nodes. Every non-deterministic step writes its input and output before the graph advances, so a killed process resumes rather than restarts.

**Authority is explicit.** A Capability Guard resolves every requested action against a Capability Record and the caller's allowlist, returns allow, deny, or approval-required, and writes that decision to an event log before the action runs. No node type reaches its work without passing it.

**Verification is structural.** Gates run a builder and an independent verifier; high-risk work adds an adversary. No role assesses its own output, and the final verdict is written by control code rather than by a model.

**Isolation is per-Run.** Each mutating Run gets its own Git worktree and a disposable scratch directory, on top of whatever sandbox the agent tool provides.

**The host is known honestly.** Hardware facts, installed runtime capability, and per-function device readiness are three separate stages with three separate records. The system can tell the difference between "this machine has no GPU" and "this environment cannot reach the GPU it has."

**Voice works end to end.** Wake word, voice activity, transcription, and speech run locally, each on the device its own runtime can actually reach.

**Deviation is recorded, not silent.** Ten architecture decision records cover every place the implementation departs from the specification, with the compensating control that made the departure acceptable.

This is a fabric that can safely run agents. It is not yet an assistant.

---

## The Gap

AWF today drives other people's minds. Claude Code, Codex, Antigravity, and Copilot are invoked through one adapter contract, each bounded by a manifest and a guard decision. That works, and it should continue to work.

But AWF has no mind of its own. It cannot answer a question. It cannot decide what a request means. It cannot author the workflows it executes — those are hand-written files, a set of narratives about work rather than a system that produces them.

Ask AWF to do something new and there is nothing to ask. There is only a registry of things someone already described.

Everything that follows is about closing that gap without dissolving the foundation into it.

---

## The First Promise: A Resident Mind

Before AWF can converse, plan, or improve itself, it needs a model that is always there — local by default, on the operator's hardware, subject to the same hardware chain that already governs speech.

The model runs as a managed local runtime: llama.cpp for GGUF weights, or an Ollama endpoint when the operator prefers one. Which model loads is chosen from the resolved hardware profile — a small quantized model on a CPU-only laptop, a larger one when a GPU is verified, and a diagnostic model when something needs to be proven rather than used. Selection is declared per profile, acquired by command, and verified before it is claimed.

Cloud models remain available and remain a decision. Escalating a turn to a hosted provider is an authorization event with a risk class, not a silent fallback. The operator sees which mind answered.

The mind enters the system as a Model Profile, which the Model Gateway already resolves and the Guard already governs. It is a new provider inside an existing shape, not a new architecture beside one.

**The boundary that must hold:** the model interprets and proposes. The application owns state, permissions, retries, interruption, approvals, actions, and recovery. The model is a worker inside the fabric. It does not become the fabric.

---

## The Second Promise: The Mind Authors the Work

Once a resident model exists, the natural next question is what it should be for. The answer is not "chat." It is authorship.

An operator describes an outcome. The mind proposes a Workflow: nodes, agents, gates, budgets, and the capabilities each step will need. That proposal is a real registry object — versioned, readable, and diffable — not a hidden plan inside a context window.

The operator reviews it the way they would review a pull request. Approve it and it publishes. Reject it and it doesn't. Edit it and the edit is the version that runs.

This is what turns AWF from a runner of hand-written workflows into a system that produces them. It is also where the existing gate machinery earns its keep: a proposed workflow is work product, and work product goes through a verifier before it becomes registry truth.

The same authorship applies to the smaller shapes — a Skill for a recurring procedure, an Agent Manifest for a new role, a Capability Record for an action that needs a tighter risk class than the default.

**The boundary that must hold:** a generated workflow is a proposal until an operator approves it. Publication is an approval event, and the diff the operator saw is the diff that ran.

---

## The Third Promise: Memory Beyond Workflows

Workflows describe how work is done. They say nothing about what happened, what was learned, or what the operator prefers. AWF needs memory, and memory needs layers — each introduced only when the one beneath it is stable.

**The present turn.** Temporary context assembled to complete one exchange: the request, the active state, the resolved capabilities, retrieved facts, intermediate results. It disappears unless deliberately promoted.

**The active session.** Bounded working memory so related turns stay coherent. Summarized or expired, never an infinitely growing transcript.

**What happened.** Episodic memory over Runs, Steps, verdicts, and approvals. This already exists as the event log — it becomes memory when it can be retrieved deliberately rather than only queried forensically.

**What remains true.** Semantic memory: durable facts and preferences, each with provenance, confidence, and a correction path. A statement made once is not automatically a fact forever.

**How work is done.** Procedural memory is the Skill — a bounded, portable bundle of instructions and resources. Already a registry kind, already resolvable, already guard-governed.

**Who the operator is.** Preferences, personas, voices, defaults, and permissions live in explicit profile state that can be edited directly rather than inferred repeatedly from conversation.

Memory is curatable. The operator can see what is remembered, correct it, forget it, and pin it. Retrieval does not imply permission to retain, and a cache is never a memory authority.

**The boundary that must hold:** memory is a registry-shaped, operator-visible store under the same resolution rules as everything else — repository defaults, operator overrides, explicit versions.

---

## The Fourth Promise: A Governed Reach Into the Machine

An assistant that cannot touch the filesystem is a search box. One that can touch it without governance is a liability.

AWF already has the answer shape: reading a file, writing a file, running a command, and reaching the network are capabilities with declared effects, risk classes, and approval requirements. Reading is routine. Writing is reversible and recorded. Deleting is not routine. Anything outside an approved workspace root is denied by default rather than by judgement.

Filesystem access arrives as Capability Records and activity nodes, executing inside the worktree and scratch isolation that already exists. The operator sees the path, the operation, and the decision — before it happens, not after.

The same discipline extends to MCP connections. An MCP server is a connection boundary, not an agent, and it receives no blanket trust because it was configured once.

**The boundary that must hold:** capability comes from a record, never from a prompt. No conversation grants authority.

---

## The Fifth Promise: The System Improves Itself, With Consent

AWF is a system that runs coding agents against repositories under isolation, verification, and approval. Its own repository is a repository.

Self-improvement is therefore not a new mechanism. It is AWF pointed at itself: a Run with a worktree, an agent that proposes a change, a gate that verifies it, a diff the operator reviews, and an approval that merges it. The architecture decision record is the artifact that survives.

This is the wish that most systems get wrong by making it magic. Here it is deliberately ordinary — the same fabric, the same guard, the same verdict, the same approval. The only unusual property is the target.

**The boundary that must hold:** the system never merges its own change. Verification is independent, approval is human, and the change is a reviewable diff rather than a live mutation.

---

## The Sixth Promise: Voice That Holds a Conversation

The current voice path proves the pipeline: a wake file and a command file go in, a spoken response comes out. It is correct and it is not yet conversational.

Fluid voice means continuous listening rather than file handoff, streamed speech that begins before the full response exists, barge-in that stops playback mid-sentence and yields the turn, and recovery that returns to a clear state after an interruption rather than an ambiguous one.

It also means voice is a doorway, not a product. The same Run, the same memory, the same guard, the same approvals. What changes is the entry point. What does not change is that a high-risk approval requires on-screen confirmation of the exact action — voice alone never authorizes something irreversible.

Agent roles keep distinct personas and voices, so the operator can hear which role is speaking without being told.

**The boundary that must hold:** voice and text share one path. They may enter at different points; they may not become two systems with different rules.

---

## The Seventh Promise: A Control Center That Feels Familiar

The category has converged. Terminal-native agents ask for approval on edits and expose slash commands, hooks, and subagents. Desktop apps have become command centers for spawning and monitoring agents, with one surface for running work and another for reviewing diffs. The differentiators that matter under load are approval hierarchy, sandboxing model, and context handling — not chat quality. Teams have stopped choosing one model and started assigning models per task.

AWF should be recognizable inside that convention, because familiarity is a feature and reinvented interaction models are a tax.

**The desktop control center** presents the state a local agentic system actually has: what is running now, what is waiting on the operator, what the last verdict said, which model answered, what the host can currently accelerate. Conversation is one panel among several rather than the whole application. Approvals show the exact action. Diffs are reviewable before they land. Memory is browsable and editable. Registry objects are inspectable. The hardware chain is visible, because a system that hides its readiness cannot be trusted when it claims to be ready.

**The terminal client** is a peer, not a fallback. Interactive by default, streaming, with a slash-command surface where registry Skills appear directly as commands. Both clients attach to the same core, observe the same Run, and can act on the same approval. Starting work in the terminal and finishing it in the desktop is one session, not two.

**The core stays headless.** Both surfaces are presentation over one contract. Neither owns durable state. Anything either can do, a script can do.

**The boundary that must hold:** a frontend is never a second architecture. If a capability exists only in the GUI, it does not exist.

---

## What Must Never Break

These survive every later change:

- Every action passes the Capability Guard, and the decision is recorded before the action runs.
- Nothing assesses its own output. Verification is independent and verdicts are written by control code.
- Hardware claims come from probes, and probe results distinguish what the machine has from what the environment can reach.
- A Run resumes rather than restarts.
- Model reasoning proposes; the application decides.
- High-risk approval requires explicit confirmation of the exact action.
- Local by default. Remote is a decision with a record.
- Deviation from the specification requires an ADR, not a commit message.

---

## Growth Order

Each layer rests on the one before it. Later layers may inform earlier ones; they may not weaken them.

1. **Foundation** — durable Runs, guard, registry, gates, isolation, hardware chain. *Built.*
2. **Resident mind** — local model runtime, hardware-aware selection, governed cloud escalation.
3. **Conversation** — one turn loop through the resident mind, shared by voice and text.
4. **Authorship** — the mind proposes workflows, skills, and manifests as reviewable registry objects.
5. **Memory** — turn, session, episodic, semantic, procedural, profile; curatable and correctable.
6. **Reach** — filesystem and workspace capabilities under explicit records and approval.
7. **Surfaces** — the desktop control center and the terminal client over one headless core.
8. **Fluid voice** — continuous listening, streamed speech, barge-in, clean recovery.
9. **Self-improvement** — AWF working on AWF, through the same gate and approval path.
10. **Broader autonomy** — only after the layers beneath stay dependable under real use.

---

## Definition of Success

AWF succeeds when an operator can say what they want, watch a system they trust turn it into real work, review what it proposes, approve what matters, and read afterward exactly what happened and why it was allowed.

It succeeds when the assistant is local enough to be private, governed enough to be trusted with a filesystem, capable enough to write its own workflows, and honest enough to say what it cannot currently do.

It succeeds when adding a capability means adding a record, not adding an exception.

The system may become broad. It must not become vague.

---

## Evidence and Governance

This document defines direction and the invariants that should survive implementation change. It is not a specification and it does not authorize work.

- `ProjectVisionAWF.md` — direction and enduring shape
- `docs/AGENTIC_WORKFLOW_FABRIC_SPEC.md` — normative design
- `docs/adr/` — decisions, deviations, and their compensating controls
- `CHANGE_LOG.md` — completed changes with command evidence

Implementation is complete when the intended outcome works on the hardware it claims to support. Documents, tests, and reports support that conclusion. They do not substitute for it.