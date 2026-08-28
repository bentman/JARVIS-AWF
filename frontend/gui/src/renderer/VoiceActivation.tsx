import React, { useRef, useState } from "react";
import { blobToWav16 } from "./wav.js";

export type VoiceSessionState =
  | "idle"
  | "armed"
  | "listening"
  | "transcribing"
  | "submitting"
  | "speaking"
  | "recovering"
  | "closed";

export interface VoiceSessionResult {
  voice_session_id: string;
  memory_session_id: string;
  state: VoiceSessionState;
}

export interface VoiceSubmitTextResult {
  recognized_text: string;
  response_text: string;
  state: VoiceSessionState;
  run?: { run_id: string };
  voice?: { voice_profile_ref: string; voice_id: string };
}

export interface VoiceActivationProps {
  defaultWorkflowRef?: string;
  workflowOptions?: string[];
  onSessionStart: (title?: string, wakeEnabled?: boolean) => Promise<VoiceSessionResult>;
  onPushToTalkStart: (voiceSessionId: string, turnId: string) => Promise<VoiceSessionResult>;
  onPushToTalkStop: (voiceSessionId: string, turnId: string) => Promise<VoiceSessionResult>;
  onInterrupt: (voiceSessionId: string, turnId: string) => Promise<VoiceSessionResult>;
  onSubmitText: (
    voiceSessionId: string,
    text: string,
    workflowRef: string | undefined,
    voiceProfileRef: string | undefined,
    turnId: string,
  ) => Promise<VoiceSubmitTextResult>;
}

function nextTurnId(): string {
  return `turn-${Date.now()}`;
}

// The Part C table doesn't cover voice-session states directly, but the ADR's
// own worked example calls out `listening` reading warn and `speaking`
// reading ok - a small local mapping on top of the shared `stateClass`,
// scoped to this component's vocabulary only.
function voiceStateClass(state: VoiceSessionState): string {
  if (state === "speaking") return "state-ok";
  if (state === "listening" || state === "transcribing" || state === "submitting" || state === "recovering") {
    return "state-warn";
  }
  return "state-idle";
}

export interface VoiceActivationHandle {
  /** Drives the existing push-to-talk flow from an external control (e.g. the
   * chat composer's mic button). No-op while no voice session is started. */
  togglePushToTalk: () => void;
}

export const VoiceActivation = React.forwardRef<VoiceActivationHandle, VoiceActivationProps>(
  function VoiceActivation({
    defaultWorkflowRef = "",
    workflowOptions = [],
    onSessionStart,
    onPushToTalkStart,
    onPushToTalkStop,
    onInterrupt,
    onSubmitText,
  }: VoiceActivationProps, ref): React.JSX.Element {
  const [voiceSessionId, setVoiceSessionId] = useState<string | null>(null);
  const [turnId, setTurnId] = useState<string>(nextTurnId());
  const [state, setState] = useState<VoiceSessionState>("idle");
  const [workflowRef, setWorkflowRef] = useState(defaultWorkflowRef);
  const [recognizedText, setRecognizedText] = useState("");
  const [voiceProfileRef, setVoiceProfileRef] = useState("narrator@1.0.0");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);

  const updateFrom = (result: VoiceSessionResult | VoiceSubmitTextResult) => {
    setState(result.state);
  };

  const withBusy = async (fn: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const startSession = () =>
    withBusy(async () => {
      const result = await onSessionStart("Voice session", false);
      setVoiceSessionId(result.voice_session_id);
      updateFrom(result);
    });

  const startPushToTalk = () =>
    withBusy(async () => {
      if (!voiceSessionId) return;
      if (navigator.mediaDevices?.getUserMedia) {
        streamRef.current = await navigator.mediaDevices.getUserMedia({ audio: true });
      }
      if (streamRef.current) {
        audioChunksRef.current = [];
        // Whatever container Chromium gives us; `blobToWav16` re-encodes
        // it to the mono 16-bit PCM WAV the STT adapters require.
        const recorder = new MediaRecorder(streamRef.current);
        recorder.ondataavailable = (e) => {
          if (e.data.size > 0) audioChunksRef.current.push(e.data);
        };
        mediaRecorderRef.current = recorder;
        recorder.start();
      }
      const nextTurn = nextTurnId();
      setTurnId(nextTurn);
      updateFrom(await onPushToTalkStart(voiceSessionId, nextTurn));
    });

  const stopPushToTalk = () =>
    withBusy(async () => {
      if (!voiceSessionId) return;
      const recorder = mediaRecorderRef.current;
      if (recorder && recorder.state !== "inactive") {
        const transcript = await new Promise<{ text: string; language: string }>((resolve, reject) => {
          recorder.onstop = () => {
            const blob = new Blob(audioChunksRef.current, { type: recorder.mimeType });
            blobToWav16(blob)
              .then((wav) => window.awf.voiceTranscribe(wav))
              .then(resolve)
              .catch(reject);
          };
          recorder.stop();
        });
        setRecognizedText(transcript.text);
      }
      mediaRecorderRef.current = null;
      streamRef.current?.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
      updateFrom(await onPushToTalkStop(voiceSessionId, turnId));
    });

  const submitText = () =>
    withBusy(async () => {
      if (!voiceSessionId) return;
      const result = await onSubmitText(
        voiceSessionId,
        recognizedText,
        workflowRef || undefined,
        voiceProfileRef || undefined,
        turnId,
      );
      updateFrom(result);
    });

  const interrupt = () =>
    withBusy(async () => {
      if (!voiceSessionId) return;
      mediaRecorderRef.current?.stop();
      mediaRecorderRef.current = null;
      streamRef.current?.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
      updateFrom(await onInterrupt(voiceSessionId, turnId));
    });

  React.useImperativeHandle(
    ref,
    () => ({
      togglePushToTalk: () => {
        if (state === "listening") void stopPushToTalk();
        else void startPushToTalk();
      },
    }),
    [state, startPushToTalk, stopPushToTalk],
  );

  return (
    <div role="group" aria-label="Voice session" className="voice-bar">
      <div className="voice-row">
        <span className={`chip ${voiceStateClass(state)}`}>{state}</span>
        {voiceSessionId && <span className="voice-session mono">Voice session: {voiceSessionId}</span>}
        <button className="btn btn-primary" onClick={startSession} disabled={busy || state === "closed"}>
          Start voice session
        </button>
        <button
          className="btn btn-secondary voice-ptt"
          onClick={startPushToTalk}
          disabled={busy || !voiceSessionId || state === "listening"}
        >
          Push to talk
        </button>
        <button
          className="btn btn-secondary"
          onClick={stopPushToTalk}
          disabled={busy || !voiceSessionId || state !== "listening"}
        >
          Stop talking
        </button>
        <button
          className="btn btn-primary"
          onClick={submitText}
          disabled={busy || !voiceSessionId || !recognizedText}
        >
          Submit voice text
        </button>
        <button className="btn btn-danger" onClick={interrupt} disabled={busy || !voiceSessionId}>
          Interrupt
        </button>
      </div>
      <div className="voice-row">
        <label>
          Default workflow
          <input
            type="text"
            value={workflowRef}
            onChange={(e) => setWorkflowRef(e.target.value)}
            placeholder="workflow@1.0.0"
            list={workflowOptions.length > 0 ? "voice-workflow-options" : undefined}
          />
          {workflowOptions.length > 0 && (
            <datalist id="voice-workflow-options">
              {workflowOptions.map((option) => (
                <option key={option} value={option} />
              ))}
            </datalist>
          )}
        </label>
        <label>
          Voice profile
          <input
            type="text"
            className="mono"
            value={voiceProfileRef}
            onChange={(e) => setVoiceProfileRef(e.target.value)}
            placeholder="narrator@1.0.0"
          />
        </label>
        <label>
          Final recognized text
          <textarea value={recognizedText} onChange={(e) => setRecognizedText(e.target.value)} />
        </label>
        {error && <span role="alert">{error}</span>}
      </div>
    </div>
  );
});
