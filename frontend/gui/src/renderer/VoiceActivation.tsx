import React, { useRef, useState } from "react";

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
    workflowRef: string,
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
  const [partialText, setPartialText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const streamRef = useRef<MediaStream | null>(null);

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
      const nextTurn = nextTurnId();
      setTurnId(nextTurn);
      setPartialText("");
      updateFrom(await onPushToTalkStart(voiceSessionId, nextTurn));
    });

  const stopPushToTalk = () =>
    withBusy(async () => {
      if (!voiceSessionId) return;
      streamRef.current?.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
      updateFrom(await onPushToTalkStop(voiceSessionId, turnId));
      setPartialText(recognizedText);
    });

  const submitText = () =>
    withBusy(async () => {
      if (!voiceSessionId) return;
      if (!workflowRef) throw new Error("Set a default workflow before submitting voice text.");
      const result = await onSubmitText(
        voiceSessionId,
        recognizedText,
        workflowRef,
        voiceProfileRef || undefined,
        turnId,
      );
      updateFrom(result);
      setPartialText("");
    });

  const interrupt = () =>
    withBusy(async () => {
      if (!voiceSessionId) return;
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
        {partialText && <span aria-label="Partial transcript">Partial: {partialText}</span>}
        {error && <span role="alert">{error}</span>}
      </div>
    </div>
  );
});
