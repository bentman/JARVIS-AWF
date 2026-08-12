# ADR-0018: personas and the prompt envelope

## Status

Implemented.

Acceptance run: `scripts/validate_backend.py lint` passed; `scripts/validate_backend.py runtime` -> 17 passed, 1 skipped; `scripts/validate_backend.py ci` -> 509 passed, 18 deselected. Focused prompt/persona coverage is included in the backend test suite.

Corrective update, 2026-08-12: agent-step envelope assembly now includes
bounded memory retrieval. Segment order is application instruction, persona
style, skill instructions, untrusted memory/retrieval context, then current
user input. Only trusted `application`/`persona`/`contract` segments can be
promoted to the chat system message; memory and retrieval remain user-side
context.

Two tasks. Task A adds the Persona registry kind. Task B adds the prompt
envelope. Task B depends on Task A.

## Context

**Prompt text is assembled by string concatenation.**
`engine/agent_step._apply_skills` builds

```python
objective_parts = [instructions] if instructions else []
objective_parts += [skill.body for _ref, skill, _digest, _dir in resolved if skill.body]
objective_parts.append(invocation.objective)
objective = "\n\n".join(part for part in objective_parts if part)
```

and sets `AgentInvocation.objective` to the result. `gateway/client.complete`
takes a `messages` list its caller built. Nothing distinguishes text the
application wrote from text a published Skill supplied, from text a node
carried in. Once joined, the distinction cannot be recovered, so a Skill body
reads to the model exactly like an operator instruction.

**Persona exists in one place and is never read.**
`registry/voice_profile.py` defines `Persona(name, description, style_prompt)`
and `parse_voice_profile` requires a `persona` block.
`speech/pipeline.run_voice_round_trip` uses `voice_id` and nothing else from
the profile; `resolve_default_voice_id` reads `enabled_candidates_by_priority`.
No module reads `VoiceProfile.persona`.

**Nothing governs prompt text.** `guard/capability_guard.authorize` decides
whether an action may run. A registry object that carries instruction text
carries whatever that text says, because there is no schema-level boundary on
what instruction text may claim.

**The registry can take another kind cheaply.** `registry/kinds.py` declares
`RegistryKind(key, layout, data_only)`, seven instances, `KINDS`, `by_key`,
`object_path`, and `version_names`. `resolve.py`, `op_registry_list`, and
`op_registry_publish` all read layout from there (ADR-0011), and ADR-0012 made
every kind publishable, indexable, digested, and trust-marked through one
path. An eighth entry inherits all of it.

**The loader shape is fixed.** `registry/schema.py` exports
`require(mapping, key, context, *, error)`,
`require_enum(value, allowed, context, *, error)`, and
`split_frontmatter(text, *, label, error)`. Each loader binds them with
`functools.partial` to its own `<Kind>ValidationError` and verifies that the
parsed `name`/`version` match the containing directory and the file stem.

## Decision

**Task A — `personas` becomes the eighth registry kind.** A Persona is
behavior text with a closed field set and an explicit prohibition on fields
that would grant authority. It compiles deterministically to system text; no
model participates.

**Voice Profile references a Persona.** `VoiceProfile.persona` is replaced by
`persona_ref`. A voice describes how something sounds; a persona describes how
it answers.

**Task B — one envelope, two renderers.** `awf/cognition/` holds a
`PromptEnvelope` of authority-tagged, trust-flagged segments. `render_flat`
produces the single objective string adapters take. `render_chat` produces the
`messages` list the Gateway takes, and places only trusted `application`,
`persona`, and `contract` segments in the system message.

**`_apply_skills` composes an envelope.** The adapter still receives a string:
`AgentInvocation.objective = render_flat(envelope)`.

## Rationale

Concatenation is the shared cause. Tagging each segment with its authority and
whether it is trusted is what lets the chat renderer place untrusted content
where a model treats it as data rather than direction, and what lets the flat
render label its provenance for an adapter that only accepts one string.

A Persona is operator-authored instruction text published into the registry,
which makes it the most likely place for authority to leak in. A closed field
set plus a named prohibition list means a persona that grants itself tool
access fails to load rather than loading and being trusted because it sits in
a registry directory.

Separating persona from voice follows from use. The terminal client has no
voice and needs a persona; the verifier and adversary Gate roles need
personas whose assertiveness differs from the narrator's without inventing
voices for them.

## Deviation recorded

| Requirement | Deviation | Compensating control |
|---|---|---|
| Section 16.5 Voice Profile schema, which carries `persona: {name, description, style_prompt}` inline | replaced by `persona_ref: <name>@<version>` | the four shipped Voice Profiles each gain a ref to a shipped Persona carrying their existing text; `load_voice_profile` resolves the ref, so a caller reaches persona text in one hop |
| Section 7 layout, which enumerates the registry kinds | adds `config/app_registry/personas/` and `data/registry/personas/` | declared in `registry/kinds.py` alongside the other seven; publishes, indexes, digests, and trust-marks through the same path with no special case |

The Capability Guard, resolution precedence, the Model Gateway's existing
`complete`, and every adapter contract are unchanged.

## Mechanism

### Task A — the Persona kind

**`registry/kinds.py`** gains one line and one tuple entry:

```python
PERSONAS = RegistryKind("personas", "yaml", False)

KINDS: tuple[RegistryKind, ...] = (
    WORKFLOWS, AGENTS, CAPABILITIES, MCP, SKILLS, VOICE_PROFILES, MODEL_PROFILES, PERSONAS
)
```

**`registry/persona.py`**, following the `voice_profile.py` shape exactly —
`functools.partial`-bound helpers from `registry/schema.py`, a frozen
dataclass per block, a `ref` property, and a `load_*` that checks the path:

```python
TRAIT_LEVELS = ("none", "low", "medium", "high", "strong")
HUMOR_LEVELS = ("none", "light", "medium", "high", "dry")

ALLOWED_FIELDS = (
    "name", "version", "display_name", "description", "locale",
    "system", "style", "traits", "examples", "generation", "enabled",
)

PROHIBITED_FIELDS = (
    "capabilities", "tool_permissions", "tool_policy",
    "routing_policy", "model_routing", "model_profile", "mcp", "skills",
    "memory_policy", "memory_permissions",
    "safety_overrides", "hidden_instructions",
)

class PersonaValidationError(ValueError): ...

@dataclass(frozen=True)
class PersonaStyle:
    max_words_default: int
    structure: str
    do: tuple[str, ...]
    avoid: tuple[str, ...]

@dataclass(frozen=True)
class PersonaTraits:
    warmth: str
    assertiveness: str
    detail: str
    humor: str

@dataclass(frozen=True)
class PersonaExample:
    user: str
    assistant: str

@dataclass(frozen=True)
class Persona:
    name: str
    version: str
    display_name: str
    description: str
    locale: str
    system: str
    style: PersonaStyle
    traits: PersonaTraits
    examples: tuple[PersonaExample, ...]
    generation: dict
    enabled: bool

    @property
    def ref(self) -> str: ...

parse_persona(raw: dict) -> Persona
load_persona(path: Path) -> Persona
compile_persona(persona: Persona) -> CompiledPersona
```

`parse_persona` rejects in this order, so the more specific message wins:

1. any key in `PROHIBITED_FIELDS` — `"persona contains prohibited authority fields: <names>"`;
2. any key outside `ALLOWED_FIELDS` — `"persona contains unknown fields: <names>"`;
3. missing required keys, through `_require`.

`enabled` defaults to `True`. `warmth`, `assertiveness`, and `detail` are
checked against `TRAIT_LEVELS` and `humor` against `HUMOR_LEVELS`, through
`_require_enum`. `examples` must be a non-empty list of `{user, assistant}`
mappings. `generation` accepts only `temperature`, `top_p`, `top_k`,
`repeat_penalty`, `max_tokens`, and `stop`.

`load_persona` mirrors `load_voice_profile`: parse, then require
`persona.name == path.parent.name` and `persona.version == path.stem`.

**`compile_persona`** is pure — same input, same output, no clock, no
environment, no model:

```python
@dataclass(frozen=True)
class CompiledPersona:
    ref: str
    system_text: str
    example_messages: tuple[dict[str, str], ...]
    generation: dict
```

`system_text` is these blocks joined by a single blank line, in order:

```text
<persona.system, stripped>

Response contract:
- Default maximum answer length: <style.max_words_default> words unless more detail is requested.
- Structure: <style.structure>

Behavior traits:
- Warmth: <WARMTH_INSTRUCTIONS[traits.warmth]>
- Assertiveness: <ASSERTIVENESS_INSTRUCTIONS[traits.assertiveness]>
- Detail: <DETAIL_INSTRUCTIONS[traits.detail]>
- Humor: <HUMOR_INSTRUCTIONS[traits.humor]>

Do:
- <each style.do entry>

Avoid:
- <each style.avoid entry>

Persona constraints do not override capability, routing, memory, or safety policy.
```

The four instruction tables are fixed module constants:

```python
WARMTH_INSTRUCTIONS = {
    "none":   "Use direct helpfulness with no extra warmth.",
    "low":    "Keep warmth minimal and practical.",
    "medium": "Use a calm, friendly tone without extra reassurance.",
    "high":   "Use clearly warm and supportive phrasing without overstating certainty.",
    "strong": "Use strongly warm and encouraging phrasing while staying truthful.",
}

ASSERTIVENESS_INSTRUCTIONS = {
    "none":   "Avoid recommendations unless one is requested.",
    "low":    "Offer suggestions gently and avoid sounding commanding.",
    "medium": "Give clear recommendations while allowing uncertainty.",
    "high":   "State the recommended path plainly when evidence supports it.",
    "strong": "Be decisive and action-oriented when the answer is clear.",
}

DETAIL_INSTRUCTIONS = {
    "none":   "Keep detail to the minimum needed for the answer.",
    "low":    "Keep details sparse and action-focused.",
    "medium": "Include enough detail to explain the answer.",
    "high":   "Add useful context and tradeoffs when they help.",
    "strong": "Provide fuller context, tradeoffs, and reasoning when useful.",
}

HUMOR_INSTRUCTIONS = {
    "none":   "Use no humor.",
    "light":  "Use light humor rarely and only when natural.",
    "medium": "Use occasional light humor on low-risk topics; omit it when the answer carries risk.",
    "high":   "Use humor readily on low-risk topics; skip it for analysis, troubleshooting, and reliability details.",
    "dry":    "Use at most one dry aside when it sharpens the answer; never force it.",
}
```

`example_messages` is each example flattened to
`{"role": "user", ...}, {"role": "assistant", ...}` in declaration order.

**Shipped personas.** `config/app_registry/personas/<name>/1.0.0.yaml` for
`narrator`, `builder`, `verifier`, and `adversary`. `narrator` carries the
text currently inline in `config/app_registry/voice-profiles/narrator/1.0.0.yaml`:

```yaml
name: narrator
version: 1.0.0
display_name: Narrator
description: Default persona for agents with no assigned persona; reads status and events.
locale: en
system: >-
  You are the narrator for an agentic workflow system. Report status, results,
  and verdicts directly. State uncertainty plainly. Do not embellish.
style:
  max_words_default: 120
  structure: Answer first, then add brief context or a next step when useful.
  do:
    - Start with the practical answer.
    - State uncertainty plainly.
    - Keep the tone calm and informative.
  avoid:
    - Long digressions.
    - Embellishment.
    - Overexplaining simple requests.
traits: {warmth: medium, assertiveness: medium, detail: medium, humor: none}
examples:
  - user: Did the gate pass?
    assistant: >-
      Yes, on the second attempt. The first failed on a missing test for the
      empty-input case, which the repair step added.
generation:
  temperature: 0.6
  top_p: 0.9
  top_k: 40
  repeat_penalty: 1.08
  max_tokens: 180
  stop: ["\nUser:", "\nAssistant:"]
enabled: true
```

`builder`, `verifier`, and `adversary` follow the same shape with the persona
text from their existing Voice Profiles, and with traits matching their Gate
role: the verifier raises `detail` and drops `warmth`; the adversary raises
`assertiveness` to `strong` and sets `humor: none`.

**`registry/voice_profile.py`** replaces the `Persona` dataclass and the
`persona` block with:

```python
persona_ref: str        # "<name>@<version>", required
```

`parse_voice_profile` requires `persona_ref` and rejects a `persona` key with
`"voice profile: 'persona' is replaced by 'persona_ref' (ADR-0018)"`.
`load_voice_profile` gains a `repo_root` parameter and resolves the ref
through `resolve_registry_object(repo_root, "personas", name, version)`,
returning the loaded `Persona` on the profile as `persona`. Callers that only
need `voice_id` — `resolve_default_voice_id` — pass the `repo_root` they
already hold.

### Task B — the prompt envelope

**`awf/cognition/envelope.py`:**

```python
AUTHORITIES = ("application", "persona", "contract", "session",
               "memory", "retrieval", "skill", "tool", "user")
CONTENT_TYPES = ("instruction", "style", "context", "result", "input", "contract")

SYSTEM_AUTHORITIES = ("application", "persona", "contract")

@dataclass(frozen=True)
class PromptSegment:
    authority: str
    content_type: str
    trusted: bool
    text: str

@dataclass(frozen=True)
class PromptEnvelope:
    segments: tuple[PromptSegment, ...] = ()
    example_messages: tuple[dict[str, str], ...] = ()
    generation: dict = field(default_factory=dict)

    def with_segment(self, segment) -> "PromptEnvelope": ...
```

`PromptSegment.__post_init__` rejects an authority outside `AUTHORITIES` or a
content type outside `CONTENT_TYPES`.

**`awf/cognition/render.py`:**

```python
@dataclass(frozen=True)
class ChatPrompt:
    system_text: str
    user_text: str
    messages: list[dict[str, str]]
    generation: dict

render_flat(envelope: PromptEnvelope) -> str
render_chat(envelope: PromptEnvelope) -> ChatPrompt
```

Both renderers use one header per segment:

```text
[<authority>/<content_type>{, untrusted}]
```

so a Skill body renders under `[skill/instruction, untrusted]` and an Agent
Manifest's instructions under `[application/instruction]`. The `, untrusted`
suffix appears only when `trusted` is `False`.

`render_flat` joins `f"{header}\n{segment.text.strip()}"` for every segment in
order, separated by a blank line.

`render_chat` walks the segments in order and appends each rendered segment to
the system parts when `segment.trusted and segment.authority in
SYSTEM_AUTHORITIES`, and to the user parts otherwise. It then builds
`messages` as: the system message when `system_text` is non-empty, then
`envelope.example_messages`, then the user message when `user_text` is
non-empty. `generation` is copied through.

Trust is assigned by the composer, never read from content.

**`engine/agent_step._apply_skills`** composes, in this order:

| Segment | authority | content_type | trusted |
|---|---|---|---|
| Agent Manifest `instructions` | `application` | `instruction` | `True` |
| compiled persona `system_text` | `persona` | `style` | `True` |
| each resolved Skill `body` | `skill` | `instruction` | `False` |
| node `invocation.objective` | `user` | `input` | `False` |

Empty parts are omitted. `AgentInvocation.objective` becomes
`render_flat(envelope)`. Every other field of the returned `AgentInvocation`
is unchanged, and the existing `skills_resolved` event is unchanged.

**`registry/agent_manifest.py`** gains an optional `persona` field parsed from
the frontmatter key `persona`, alongside the existing `voice` and
`modelProfile`. `run_agent_step` gains a `persona_ref: str | None = None`
parameter, resolves it through
`resolve_registry_object(repo_root, "personas", name, version)`, loads and
compiles it, and passes the `CompiledPersona` into `_apply_skills`. A node
with no persona composes no persona segment, and the envelope's
`example_messages` and `generation` stay empty.

**`gateway/client.py`** gains:

```python
def complete_envelope(profile, envelope, *, conn=None, secret_key=None) -> str:
    chat = render_chat(envelope)
    return complete(profile, chat.messages, conn=conn, secret_key=secret_key)
```

`complete` is unchanged, so every current caller is unaffected. The Model
Profile's `limits.max_output_tokens_per_call` continues to set `max_tokens` on
the candidate call, which means it bounds a persona asking for more.

## Layout delta

```text
config/app_registry/
  personas/{narrator,builder,verifier,adversary}/1.0.0.yaml   (new)
  voice-profiles/*/1.0.0.yaml                                 (persona -> persona_ref)
backend/src/awf/
  cognition/{__init__,envelope,render}.py                     (new)
  registry/persona.py                                         (new)
  registry/kinds.py                                           (PERSONAS)
  registry/voice_profile.py                                   (persona_ref; Persona removed)
  registry/agent_manifest.py                                  (optional persona ref)
  engine/agent_step.py                                        (composes an envelope)
  gateway/client.py                                           (complete_envelope)
.gitignore                                                    (/data/registry/personas/)
```

## The tradeoffs accepted

- A trait level compiles to one fixed sentence, so `warmth: high` cannot be
  tuned without editing the table. That is what makes the same persona produce
  the same system text in every process.
- A voice and a persona are now two objects where there was one, and a Voice
  Profile cannot be loaded without a registry root to resolve its ref
  against. `load_voice_profile` gains a parameter every current caller already
  has.
- `render_chat` places a Skill body in the user message, a weaker position
  than the system-adjacent one it effectively occupies today. Skills are
  operator-published and trust-gated already; the demotion costs some
  instruction-following strength and closes a path by which published text can
  redirect the model.
- `PROHIBITED_FIELDS` is a denylist over a closed allowlist, so it can never
  be the only thing catching a bad field. It exists to name the mistake:
  `capabilities:` in a persona gets an error about granting authority rather
  than a generic unknown-field error.

## Scope for implementation

1. Add `PERSONAS` to `registry/kinds.py` and the `.gitignore` rules for
   `data/registry/personas/`.
2. Add `registry/persona.py`: schema, closed field set, prohibition list,
   `parse_persona`, `load_persona`, the four instruction tables, and
   `compile_persona`.
3. Ship the four personas under `config/app_registry/personas/`.
4. Replace `persona` with `persona_ref` in `registry/voice_profile.py`, add
   the `repo_root` parameter to `load_voice_profile`, and update the four
   shipped Voice Profiles and `resolve_default_voice_id`.
5. Add `awf/cognition/envelope.py` and `awf/cognition/render.py`.
6. Compose an envelope in `engine/agent_step._apply_skills`; set the objective
   from `render_flat`.
7. Add the optional `persona` frontmatter key to `registry/agent_manifest.py`
   and the `persona_ref` parameter to `run_agent_step`.
8. Add `gateway.complete_envelope`.
9. Tests: a persona with `capabilities:` fails to load and the error names the
   field as prohibited; a persona with an unknown field fails with the
   unknown-field error; every trait level and humor level compiles;
   `compile_persona` returns byte-identical text on two calls; a persona whose
   `name` disagrees with its directory fails to load; `render_chat` places
   trusted `application`/`persona`/`contract` segments in the system message
   and `skill`/`user`/`tool` segments in the user message; an untrusted
   `persona`-authority segment is not promoted; `render_flat` preserves
   segment order and marks untrusted segments in their headers; a Voice
   Profile with an inline `persona` block fails with the replacement message;
   a Voice Profile resolves its `persona_ref`; an agent node with a persona
   produces an objective containing the compiled text; a Model Profile's
   `max_output_tokens_per_call` bounds a persona asking for more.
10. Run all six `scripts/validate_backend.py` commands.

## Acceptance

- `config/app_registry/personas/` holds four personas, each loading through
  `load_persona` and publishing through `awf registry publish --kind personas`.
- A persona file carrying `capabilities:` or `safety_overrides:` fails to load
  with an error naming the field as prohibited.
- `compile_persona` returns identical `system_text` for the same persona in
  two separate processes.
- The four shipped Voice Profiles carry `persona_ref` and resolve it; no Voice
  Profile carries an inline `persona` block; `resolve_default_voice_id` still
  returns `bf_isabella`.
- An agent node with `persona: narrator@1.0.0` produces an
  `AgentInvocation.objective` containing the compiled persona text under a
  `[persona/style]` header, and the adapter receives it through the unchanged
  field.
- `render_chat` on an envelope with a Skill segment puts that segment in the
  user message; the system message contains only `application`, `persona`, and
  `contract` text.
- `gateway.complete_envelope` completes against a Model Profile and honours
  `limits.max_output_tokens_per_call` over the persona's `max_tokens`.
- `pytest backend/tests` matches or exceeds the pre-change pass count with the
  same or fewer skips.

## Consequences

- Every piece of text entering a model carries its authority and whether it
  was trusted, and both renderers act on that.
- A published persona cannot grant a capability, choose a model, attach an MCP
  server or Skill, or alter safety posture; those stay with the Capability
  Record, the Model Profile, the Agent Manifest, and the Guard.
- Persona is selectable without a voice, so the terminal client and the three
  Gate roles can each carry one.
- Voice Profiles describe sound only.
- The Gateway can be called with an envelope, which is the entry point a
  conversational turn will use.
