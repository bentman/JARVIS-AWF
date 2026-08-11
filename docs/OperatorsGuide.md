# AWF Operator's Guide

A plain-language guide to using JARVIS-AWF day to day.
This is not the technical spec — that lives in `docs/AGENTIC_WORKFLOW_FABRIC_SPEC.md` and `docs/adr/`.

**What AWF is, in one sentence:** you describe work, AWF starts a durable workflow for it, records everything, verifies the result, and asks *you* before anything risky or permanent happens.

**The one rule to remember:** AWF proposes, you approve. Nothing gets published, merged, or run with elevated risk without your explicit sign-off.

---

## 1. First-time setup

Do this once per machine.

1. **Create a Python venv and install** (Python 3.12–3.14):
   - Linux/WSL: `python3.12 -m venv backend/.venv` then `backend/.venv/bin/pip install -e .[dev]`
   - Windows: `py -m venv .\backend\.venv` then `.\backend\.venv\Scripts\pip install -e .[dev]`
2. **Bootstrap the repo:** run `awf-setup`
   → You get a `.env` file with a generated secret key, and an empty database at `data/awf_db/awf.db`.
3. **Match dependencies to your hardware:**
   - `awf-setup --provision` → tells you which hardware extra fits this machine, and the install command (doesn't install anything).
   - `awf-setup --install` → runs that install for you.
   - `awf-setup --verify` → confirms what actually got installed (runtime, providers, tooling) and that pip is healthy.
4. **Download voice models (only if you want voice):** `awf-speech models sync`
   → Fetches the wake-word, VAD, speech-to-text, and text-to-speech models for your hardware. `awf-speech models verify` checks them later.
5. **Frontends (optional):** `npm --prefix frontend install` then `npm --prefix frontend run build` (Node 26+).

You also need at least one CLI coding agent installed and logged in with your own account (Claude Code, Codex CLI, Antigravity CLI, GitHub Copilot CLI, or Cline CLI) for workflows that delegate implementation work. The default assistant workflow runs locally without those CLIs, so first-run chat and control-center checks can work before agent setup is complete.

---

## 2. The three ways to use AWF

All three talk to the same core. Nothing one can do that another can't.

| Surface | Start it with | Best for |
|---|---|---|
| **Core CLI** (`awf ...`) | already installed by setup | scripting, quick one-off commands |
| **Terminal app** (AWF-CLI) | `node frontend/cli/dist/cli.js` | day-to-day assistant use with plain text plus `/slash` commands |
| **Desktop app** (AWF-GUI) | `npm --prefix frontend run dev` | the control center: dashboard, approvals, voice, memory |

In the terminal app, type a normal request to use the default assistant workflow, or type `/help` to see every command.

---

## 3. Running work

**Do:** `awf run <workflow>@<version>` (e.g. `awf run assistant-default@1.0.0 --objective "check the system"`)
**Get:** a Run. The agent works in its own isolated copy of the repo (a Git worktree), so your working files are never touched. Every step is saved as it completes.

Use `assistant-default@1.0.0` to confirm the app is accepting requests end-to-end. Use implementation workflows such as `produce-gate-repair-demo@1.0.0` after the relevant agent CLIs are installed and authenticated.

Then:
- `awf status <run-id>` → where the Run is, step by step.
- `awf artifacts <run-id>` → the evidence it produced (verdicts, findings, diffs).
- `awf resume` → after a crash or reboot, picks up any unfinished Runs from the last completed step. Nothing re-runs twice.

If a Run needs your permission mid-flight, it pauses and waits — see Approvals below.

---

## 4. Approvals — where you stay in charge

Some actions are risky (writing outside the sandbox, merging code, network calls). Those create an **approval** and the Run waits.

- `awf approvals` → list what's waiting.
- `awf approve <id>` → let it proceed.
- `awf reject <id> --reason "..."` → stop it.

**What an approval means:** you're approving one *exact* action — the exact file, command, URL, or diff shown to you (identified by a digest). If anything about the action changes, the old approval is void and you're asked again.

**Voice can never approve risky actions.** Anything above low risk requires an on-screen click on the exact action. That's deliberate.

---

## 5. Letting AWF write workflows for you

You don't have to hand-write workflow YAML.

**Do:** `awf author workflow --objective "describe what you want done"`
**Get:** a draft workflow proposal, written by the local model, saved under `data/proposals/`. It is *not* live yet.

Then:
- `awf proposal show <id>` → read the draft.
- Edit it if you like: `awf proposal update <id> --file <your-edited-file>`
- `awf proposal publish <id> --digest <digest>` → makes it a real, runnable workflow. The digest proves you're publishing exactly what you reviewed.
- `awf proposal reject <id> --reason "..."` → discard it.

Once published, run it like any other workflow.

---

## 6. The local "resident mind" model

AWF can run its own local LLM (used for authoring, reviews, and chat) — no cloud required.

1. Put a `.gguf` model file in a folder under `models/llm/<model-name>/`. (You download models yourself; AWF never fetches model weights.)
2. `awf llm servers` → see the three backend options and whether each is reachable.
3. `awf llm acquire` → downloads the `llama-server` binary for this machine (the only server AWF manages itself).
4. `awf llm select llama-server` → makes it the resident mind. Or point at your own already-running server: `awf llm select ollama` / `awf llm select openai-compatible`.
5. `awf llm serve start` / `stop` / `status` → lifecycle for the managed server.

`awf llm models` lists what's available. Remote (non-local) endpoints are refused unless you explicitly pass `--allow-remote`.

Server settings live in `config/llm/servers.yaml`. Some accelerated builds (Linux CUDA, ARM64 Adreno/QNN) must be placed manually — helper notes are in `docs/helpers/`.

---

## 7. Memory

AWF remembers only what you let it keep.

- **Sessions** are short-term working context: `awf session start`, `awf session show <id>`. They expire; they don't become permanent facts.
- **Episodic memory** is "what happened": `awf episodic search <query>`, `awf episodic timeline <run-id>` — read-only search over the audit trail.
- **Semantic memory** is durable facts/preferences, and it only exists if you publish it:
  - `awf memory search <query>` / `awf memory get <name>@<version>`
  - `awf memory propose --file <path>` → drafts a memory (models can suggest these too, but can't save them).
  - `awf memory publish <id> --digest <digest>` → makes it permanent.
  - `awf memory block <name>@<version>` → forget it (it stops being retrieved).

Corrections are new versions — history isn't silently rewritten.

---

## 8. AWF improving its own code

AWF can propose changes to its own repository, but **it can never merge them itself.**

1. Run the self-improvement workflow (e.g. `awf run self-improvement@1.0.0 --objective "describe the fix"`). The change is made in an isolated worktree and reviewed by a gate.
2. `awf improvement prepare <run-id>` → turns the Run's diff into an Improvement Proposal.
3. `awf improvement show <id>` → see the exact diff, verdict, and evidence.
4. `awf improvement request-merge <id>` → creates a merge approval for that exact diff.
5. `awf approve <approval-id>` then `awf improvement merge <id> <approval-id>` → merged.
6. Or `awf improvement reject <id> --reason "..."`.

If the candidate changes after you reviewed it, the approval is invalid and you review again.

---

## 9. Voice (desktop app)

In AWF-GUI:

- **Push-to-talk:** hold, speak, release. Your words appear as text in the transcript *before* anything acts on them, and every spoken reply also appears as text.
- Pick which voice speaks; different agent roles can sound different.
- **Interrupt** stops playback and goes back to listening.
- Voice goes through the exact same rules as typing — same runs, same guard, same approvals. And again: no risky approval by voice alone.

Current honest limits: it's push-to-talk with recorded-then-transcribed turns, not always-on streaming conversation. Wake-word listening is optional and off until you enable it. `awf-speech round-trip` remains available as a file-based test path.

---

## 10. The registry — AWF's library

Everything AWF can use — workflows, agents, capabilities, skills, MCP servers, model profiles, voice profiles, personas, memory — is a versioned file in the registry.

- Shipped defaults live in `config/app_registry/` (don't edit these).
- **Your** objects live in `data/registry/`. If you publish something with the same name as a default, yours wins.
- Browse: in the terminal app, `/workflows`, `/agents`, `/skills`, `/capabilities`, `/mcp`, `/model`, `/voices`.
- Add your own: `awf registry validate <file> --kind <kind>` then `awf registry publish <file> --kind <kind>`.
- Objects from outside sources start as *quarantined* and won't run until you promote them: `awf registry trust <kind> <name> <version> --status trusted`.
- Retire what you no longer want: `awf registry retire <kind> <name> <version>`.

---

## 11. Secrets

- `awf secret set <name>` → prompts for the value (never shown, never in shell history), stored encrypted in the database.
- `awf secret list` → names only. There is deliberately no "get" command.
- `awf secret rotate-key` → re-encrypts everything under a new key.

The encryption key lives in `.env`. Keep `.env` out of backups you share; without it, secrets are unrecoverable — which is also your kill switch.

---

## 12. Checking on the system

- `/control` (terminal) or the GUI dashboard → one overview: active runs, pending approvals, proposals, model status.
- `/readiness` → what hardware AWF actually verified (GPU/NPU/CPU) and whether speech and LLM are ready. AWF never assumes hardware — if it can't prove an accelerator works, it says so and uses CPU.
- `/llm` → model server status.
- `awf episodic timeline <run-id>` → the full audit trail for any Run. Every decision, approval, and guard check is recorded and queryable.

---

## 13. Where things live

| Path | What it is | Safe to delete? |
|---|---|---|
| `data/` | your database, registry, proposals, artifacts — **the thing to back up** | No |
| `.env` | your encryption key | No |
| `config/` | shipped defaults and machine config | No (repo-tracked) |
| `models/` | model files you downloaded | Re-downloadable |
| `runtimes/` | acquired server binaries | Re-acquirable |
| `cache/` | scratch space, sandboxes | Yes, anytime |

Moving to a new machine = copy `data/` + `.env`, reinstall, re-run `awf-setup --install` and `awf-speech models sync`.

---

## 14. Things AWF will not do (on purpose)

- Merge its own code changes.
- Publish a workflow, memory, or registry object without your review.
- Approve a risky action from voice alone.
- Claim hardware acceleration it hasn't verified.
- Run quarantined third-party registry objects.
- Fetch model weights on its own, or touch endpoints off your machine without an explicit flag.
- Show you a secret value after it's stored.

## 15. Known limits (current version)

- No live event streaming to the frontends — views refresh/poll.
- Voice is push-to-talk turns, not continuous conversation.
- `/skills` and `/skill <name>@<version>` browse skills; skills are not yet directly executable as their own slash commands.
- The Cline adapter exists, but check each agent CLI's own login/version requirements — vendor CLIs change.

---

*Keep this guide short. When a capability changes, update the matching section rather than adding a new document.*
