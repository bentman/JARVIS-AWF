# ADR-0036: fluid voice continuous listening and streaming stt

## Status

Proposed.

## Context

`docs/archives/ProjectVisionAWF.md` establishes the sixth promise (Layer 8: Fluid Voice): transitioning from file-based push-to-talk to continuous listening, interim streamed speech, barge-in playback cancellation, hands-free endpointing, and direct intent routing.

ADR-0023 introduced the initial voice session state machine (`backend/src/awf/speech/session.py`), anchoring voice sessions to active session memory and declaring frame types including `vad.speech_started`, `stt.partial`, `vad.speech_stopped`, `stt.final`, `tts.done`, and `interruption`. However, in the GUI client:
1. Interaction was strictly push-to-talk by button click: the operator manually clicked "Push to talk", spoke, clicked "Stop talking", waited for batch transcription to populate a textarea, and clicked "Submit voice text".
2. Interim transcription hypothesis was never displayed, leaving the operator with no visual feedback while speaking.
3. Assistant speech playback occurred via disconnected `new Audio(...).play()` calls; no barge-in interruption occurred when the operator spoke during assistant audio playback.
4. When audio playback concluded, no `tts.done` event was transmitted to reset the session state from `speaking` to `idle`.

## Decision

AWF implements fluid voice continuous listening, streaming interim STT, barge-in playback cancellation, and hands-free endpointing:

1. **Continuous Audio Stream & Web Audio VAD:**
   - `VoiceActivation.tsx` provides a continuous listening toggle.
   - When enabled, the browser `MediaStream` feeds a Web Audio API `AudioContext` with an `AnalyserNode` monitoring root-mean-square (RMS) energy levels continuously.
   - When energy exceeds the speech detection threshold:
     - If the session is `idle` or `armed`, it emits `vad.speech_started` and transitions to `listening`.
     - If the session is `speaking`, it immediately triggers barge-in: pauses and resets the active assistant audio playback, emits `interruption`, and transitions to `listening`.

2. **Interim Chunk Transcription (`stt.partial`):**
   - While in `listening` state, the audio recorder produces timesliced audio chunks.
   - Each chunk is converted to mono 16-bit 16kHz WAV format and passed through `window.awf.voiceTranscribe`.
   - The resulting text hypothesis populates `partialText` in real time, rendering inline feedback in the GUI and emitting `stt.partial` frames.

3. **Hands-Free Endpointing & Direct Dispatch:**
   - When RMS energy remains below the silence threshold for a sustained duration (800ms) after speech, the client detects utterance completion:
     - Emits `vad.speech_stopped`.
     - Finalizes the full utterance transcription (`stt.final`).
     - Directly and automatically submits the finalized text to `onSubmitText` without requiring operator button clicks.
     - Routes through `awf.ops.voice.op_voice_submit_text`, which applies intent classification (`classify_intent`) and dispatches to the requested workflow or default assistant workflow under full Capability Guard governance.

4. **Audio Playback Lifecycle & Event Bridge:**
   - Active assistant audio playback is tracked via a persistent reference.
   - On playback completion (`audio.onended`), the client emits `tts.done` via `window.awf.voiceEvent`, resetting the session state back to `idle` (or re-arming continuous listening).
   - An IPC channel `awf:voiceSessionEvent` is exposed in `voicePipeline.ts` and `preload.ts` to forward arbitrary frames (`VoiceFrameType`) directly to `client.voiceEvent`.

## Consequences

- **Hands-Free Operator Experience:** The operator can converse naturally with the assistant without manual button clicks for recording, transcription, or submission.
- **Unified Governance & Intent Routing:** Spoken commands follow the identical Capability Guard, active session memory, and asynchronous execution pipeline as typed input.
- **Immediate Barge-in:** The assistant ceases speaking immediately when the operator speaks, preserving fluid turn-taking.
- **No Headless Architecture Divergence:** The core state machine and JSON-RPC protocol remain headless; the client-side energy VAD and timeslicing act solely as an adaptive transport layer over standard protocol methods.
