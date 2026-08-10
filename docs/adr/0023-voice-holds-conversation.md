# ADR-0023: voice holds conversation

## Status

Implemented.

Acceptance run: `backend/.venv/bin/python -m pytest backend/tests -q` outside
the Codex sandbox -> 566 passed, 7 warnings; `backend/.venv/bin/python -m
ruff check .` passed; `npm --prefix frontend run build --workspaces` passed;
`npm --prefix frontend test --workspaces` passed; `backend/.venv/bin/python -m
awf.speech.cli models verify` passed with configured TTS/VAD/wake artifacts OK.

## Context

`docs/archives/ProjectVisionAWF.md` defines the sixth promise as the move from
file-based voice proof to fluid operator interaction: continuous listening,
streamed speech, barge-in, clean recovery, visible text for recognized speech
and spoken replies, and the same Run, memory, guard, and approval rules as
text input.

The current codebase has the foundation:

- `backend/src/awf/speech/pipeline.py` runs one wake-file plus command-file
  round trip through hardware profiling, wake detection, VAD, STT, a supplied
  core callback, and TTS.
- `backend/src/awf/speech/{wake_openwakeword,vad_silero,stt_whisper,tts_kokoro}.py`
  provide local speech adapters behind simple function contracts.
- `frontend/gui/src/main/voicePipeline.ts` spawns `awf-speech round-trip` as a
  subprocess.
- `frontend/gui/src/renderer/VoiceActivation.tsx` is push-to-talk-by-file, not
  live microphone capture.
- `frontend/gui/src/renderer/App.tsx` appends recognized command text and
  response text into the visible transcript.
- `backend/src/awf/cli/core_ops.py` already enforces that voice alone cannot
  grant R2+ approvals.
- ADR-0020 added active sessions; `backend/src/awf/memory/sessions.py` can
  persist bounded turn entries.

The missing shape is a live voice session loop. The system needs a durable,
observable bridge from GUI audio capture to the same core protocol used by
text surfaces. The bridge must not become a second command system.

Provider and community practice supports this shape:

- Pipecat models a voice agent as a transport input -> STT -> context/core ->
  TTS -> transport output pipeline, with frame processors passing typed frames
  downstream: <https://docs.pipecat.ai/pipecat/learn/pipeline>
- Pipecat separates high-priority system frames such as interruptions and user
  speaking events from queued data/control frames, so barge-in does not wait
  behind pending speech output:
  <https://docs.pipecat.ai/api-reference/server/frames/overview>
- Pipecat turn management starts turns from VAD or transcription, stops turns
  through configurable stop strategies, and emits interruption frames when
  enabled:
  <https://docs.pipecat.ai/api-reference/server/utilities/turn-management/user-turn-strategies>
- Pipecat speech input guidance treats VAD as responsive turn-start detection
  and recommends interruption support for natural voice interactions:
  <https://docs.pipecat.ai/pipecat/learn/speech-input>
- Pipecat transcript support records user and assistant text at turn
  boundaries:
  <https://docs.pipecat.ai/api-reference/server/utilities/turn-management/transcriptions>
- OpenAI Realtime exposes server VAD and semantic VAD, including
  `interrupt_response`, silence duration, threshold, and idle timeout controls:
  <https://platform.openai.com/docs/api-reference/realtime?lang=javascript>
- faster-whisper supports local Whisper transcription and VAD filtering backed
  by Silero VAD:
  <https://github.com/SYSTRAN/faster-whisper>

## Decision

**Voice is a session transport over the existing core.** AWF-GUI may capture
audio and play audio, but recognized text is submitted through JSON-RPC/core
operations. The GUI does not read or mutate durable state directly and does
not implement a separate approval or workflow path.

**The live voice loop is frame-oriented.** Add a small internal voice frame
contract with explicit frame types:

- `audio.input`
- `wake.detected`
- `vad.speech_started`
- `vad.speech_stopped`
- `stt.partial`
- `stt.final`
- `core.submitted`
- `core.output_text`
- `tts.audio_chunk`
- `tts.done`
- `interruption`
- `error`
- `session.idle`
- `session.closed`

System frames (`interruption`, errors, session lifecycle, speaking-state
changes) must preempt queued output. Audio/text data frames remain ordered
within a turn.

**Turn state is explicit.** A voice session has a deterministic state machine:

`idle -> armed -> listening -> transcribing -> submitting -> speaking -> idle`

Interruptions move `speaking -> listening`, stop pending TTS playback, append
an interruption event, and preserve the transcript state needed to understand
what was cut off. Errors move the session to `recovering`, then back to either
`armed` or `idle` with a visible status.

**Text-first remains the invariant.** Every `stt.final` frame is displayed and
persisted before core submission. Every spoken response has visible text in the
same transcript. Voice-only capabilities are not introduced.

**Barge-in is local and deterministic.** VAD speech-start while TTS is playing
is the first implementation trigger for interruption. The implementation must
cancel queued audio chunks, stop playback, and start a new user turn without
approving or committing any pending action.

**Streaming TTS is the first streaming output.** The existing core does not yet
stream agent text, so ADR-0023 starts by chunking/verbalizing available core
text as it arrives from protocol responses. Later resident-mind streaming can
feed the same `core.output_text` frame without changing the GUI contract.

**Conversation memory uses active sessions.** A live voice session maps to an
ADR-0020 active session. Final user utterances, assistant text, interruption
markers, and selected voice profile refs are appended as session entries.
Ephemeral partial STT frames are not persisted unless promoted by the final
turn.

**Approvals remain core-governed.** R2+ approvals require the on-screen digest
and non-voice confirmation. Voice may acknowledge R0/R1 prompts only through
the existing core approval channel and must never directly call the manual
approval path for R2+ actions.

**Voice profile resolution moves to the core boundary.** The renderer should no
longer hardcode shipped voice ids as the source of truth. It may display
defaults, but speaking a role should resolve the Agent Manifest's `voice`
profile through the existing registry rules, with `narrator@1.0.0` as fallback.

**File round-trip remains as a fixture/debug path.** `awf-speech round-trip`
continues to support deterministic tests and host validation, but it is no
longer the GUI's primary voice UX.

## Rationale

The important boundary from the vision is not the audio technology; it is that
voice and text share one governed path. A frame loop gives the GUI enough
structure for streaming, interruption, transcript, and recovery without
putting workflow execution or approval semantics into Electron.

Starting with local VAD-driven turn start and speech-timeout turn stop matches
the repo's selected local stack and avoids adding a new turn-completion model
before a caller proves it is needed. The frame contract leaves space for a
later semantic turn detector.

Persisting final turns into active sessions connects voice to ADR-0020 without
storing raw continuous audio or every partial token. That keeps memory
curatable and avoids transcript growth becoming an unbounded audio log.

## Entry and exit points

### Backend

- Add `backend/src/awf/speech/session.py` for the state machine, frame dataclass
  or typed dicts, interruption handling, and session lifecycle.
- Extend `backend/src/awf/speech/pipeline.py` rather than replacing the current
  round-trip function. The existing function remains the deterministic
  file-based harness.
- Add streaming-capable adapter methods where the current functions are
  blocking:
  - VAD: accept PCM chunks and emit speech-start/speech-stop frames.
  - STT: accept completed utterance buffers first; partial STT may be added
    after the state machine exists.
  - TTS: split response text into speakable chunks and emit audio-chunk frames.
- Add core operations for voice sessions in `backend/src/awf/cli/core_ops.py`:
  - `op_voice_session_start`
  - `op_voice_session_event`
  - `op_voice_session_close`
  - `op_voice_submit_text`
- Add JSON-RPC methods in `backend/src/awf/server/stdio.py`:
  - `awf/voice.sessionStart`
  - `awf/voice.event`
  - `awf/voice.sessionClose`
  - `awf/voice.submitText`
- Reuse ADR-0020 session operations for persistence and ADR-0021/approval
  operations for governed action handling.

### Frontend shared protocol

- Add voice session request/response types in `frontend/shared/src/types.ts`.
- Add `voiceSessionStart`, `voiceEvent`, `voiceSessionClose`, and
  `voiceSubmitText` methods in `frontend/shared/src/client.ts`.

### AWF-GUI main/preload

- Replace the primary GUI voice path in `frontend/gui/src/main/voicePipeline.ts`
  with a live-session bridge:
  - owns microphone/playback process boundaries;
  - forwards voice frames to the renderer for display;
  - forwards final text and lifecycle events to JSON-RPC;
  - exposes explicit `start`, `stop`, and `interrupt` IPC channels.
- Keep the current subprocess round-trip IPC for test/debug use.
- Extend `frontend/gui/src/preload/preload.ts` with narrow voice-session IPC
  methods only.

### AWF-GUI renderer

- Replace `VoiceActivation.tsx` file inputs as the primary control with live
  controls:
  - push-to-talk start/stop;
  - optional wake-word enablement;
  - visible state: idle/listening/transcribing/speaking/recovering;
  - interruption indicator.
- Extend `Transcript.tsx` to render partial STT separately from committed final
  turns.
- Keep `ApprovalConfirmation.tsx` as the only R2+ confirmation path.
- Resolve displayed/speaking voice profiles from protocol data instead of
  hardcoded renderer constants.

## Mechanism

### Task A — Voice frame and state contract

Create a backend voice session module with:

- `VoiceFrame`
- `VoiceSessionState`
- `VoiceSession`
- `VoiceSessionError`

The state machine must reject impossible transitions, for example:

- `stt.final` before `vad.speech_stopped`;
- `tts.audio_chunk` before `core.output_text`;
- approval confirmation from a voice event for R2+;
- new `core.submitted` while a previous submission is still pending unless an
  `interruption` frame has closed the previous speaking turn.

Each accepted state transition writes an event row. The event payload should
include `voice_session_id`, frame type, state before/after, active memory
session id, and relevant artifact or approval refs. Raw audio bytes are not
written to events.

### Task B — Core voice submit path

Implement `op_voice_submit_text` as the shared bridge from recognized text to
the existing command/run surface. Initial behavior:

- append the final recognized utterance to the active memory session;
- either start the configured default workflow or dispatch a limited command
  parser already supported by the text UI;
- append the visible response text to the same memory session;
- return response text plus the voice profile ref to speak.

The operation must not execute a frontend-only command and must not bypass
Capability Guard, Gates, or approvals.

### Task C — Live GUI session bridge

Add main-process session orchestration with explicit IPC:

- `awf:voiceSessionStart`
- `awf:voiceSessionStop`
- `awf:voicePushToTalkStart`
- `awf:voicePushToTalkStop`
- `awf:voiceInterrupt`
- `awf:voiceFrame`

The renderer receives frames for UI state and transcript display. The main
process owns audio capture/playback and the Python speech session process.

### Task D — Barge-in and recovery

When VAD detects speech while TTS playback is active:

1. emit `interruption`;
2. stop playback immediately;
3. discard queued TTS chunks for the interrupted assistant turn;
4. append an interruption marker to the active session;
5. transition to `listening`;
6. display the partial assistant text as interrupted.

If STT, TTS, or model readiness fails, the session transitions to `recovering`
and reports the failure in the visible transcript/status. Recovery returns to
push-to-talk-ready `idle` unless wake listening is enabled and ready.

### Task E — Voice profile and role speech

Expose a core operation that resolves a role or agent ref to a Voice Profile.
Use existing `voice-profiles` registry loading and Agent Manifest `voice`
fields. The GUI uses resolved `voice_id`, speed, privacy, and max utterance
limits when speaking.

### Task F — Validation

Backend focused tests:

- state machine accepts the normal turn sequence;
- impossible transitions fail without durable success;
- interruption during speaking cancels queued TTS and returns to listening;
- final STT text is appended to an active session before core submission;
- assistant text is appended with the selected voice profile ref;
- R2+ voice approval stays pending and requires on-screen confirmation;
- round-trip file path remains usable.

Frontend focused tests:

- live voice controls render state transitions from frames;
- partial STT is visible but not committed as final transcript;
- final STT appears before submission;
- interruption marks the assistant turn as interrupted and stops playback;
- R2+ approval cannot be triggered by voice-only events;
- renderer reaches voice only through preload IPC.

Milestone checks:

```bash
backend/.venv/bin/python -m ruff check .
backend/.venv/bin/python -m pytest backend/tests -q
npm --prefix frontend run build --workspaces
npm --prefix frontend test --workspaces
git diff --check
```

Live validation:

- Run model readiness with `awf-speech models verify`.
- Run the existing file round-trip with pinned fixture audio.
- Run AWF-GUI live push-to-talk on a host with microphone and speaker access.
- Confirm streamed/segmented TTS begins before the whole session is closed.
- Confirm speaking during playback interrupts the response and starts a new
  turn.
- Confirm an R2+ approval attempted by voice remains pending until an on-screen
  click or keypress confirms the exact digest.

Host-sensitive GUI, microphone, speaker, and accelerator commands must be run
outside the Codex sandbox and reported separately from deterministic tests.

## Implementation

Implemented on 2026-08-09.

- Added a durable voice-session state machine backed by active session entries
  and append-only events.
- Added core and JSON-RPC voice session methods for start, event, close, and
  default-workflow text submission.
- Added TypeScript protocol methods and voice-channel approval params.
- Replaced the GUI's primary voice control with live push-to-talk session
  controls and kept file round-trip as a debug/test path.
- Added a response-synthesis command and GUI hook that reuse the existing
  Kokoro TTS path for spoken replies.
- Preserved the core R2+ approval rule: voice-only approval remains pending
  until on-screen confirmation.

## Acceptance criteria

- AWF-GUI supports a live push-to-talk voice session without file-path inputs
  as the primary interaction.
- Wake-word mode remains optional and disabled until the operator has acquired
  the wake model and enabled listening.
- Final recognized speech is visible and persisted before it is submitted to
  the core.
- Spoken responses have visible transcript text and use resolved voice
  profiles.
- Barge-in stops active playback, records an interruption, and returns to a
  clear listening state.
- Voice and text submit through the same governed core path.
- R2+ approvals cannot be granted by voice alone.
- File-based round-trip validation remains available for deterministic tests.
