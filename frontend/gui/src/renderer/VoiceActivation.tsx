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
  voice?: { voice_profile_ref: string; voice_id: string };
}

export interface VoiceActivationProps {
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

export function VoiceActivation({
  onSessionStart,
  onPushToTalkStart,
  onPushToTalkStop,
  onInterrupt,
  onSubmitText,
}: VoiceActivationProps): React.JSX.Element {
  const [voiceSessionId, setVoiceSessionId] = useState<string | null>(null);
  const [turnId, setTurnId] = useState<string>(nextTurnId());
  const [state, setState] = useState<VoiceSessionState>("idle");
  const [workflowRef, setWorkflowRef] = useState("");
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

  return (
    <div role="group" aria-label="Voice session">
      <p>Status: {state}</p>
      {voiceSessionId && <p>Voice session: {voiceSessionId}</p>}
      <label>
        Default workflow
        <input
          type="text"
          value={workflowRef}
          onChange={(e) => setWorkflowRef(e.target.value)}
          placeholder="workflow@1.0.0"
        />
      </label>
      <label>
        Voice profile
        <input
          type="text"
          value={voiceProfileRef}
          onChange={(e) => setVoiceProfileRef(e.target.value)}
          placeholder="narrator@1.0.0"
        />
      </label>
      <label>
        Final recognized text
        <textarea value={recognizedText} onChange={(e) => setRecognizedText(e.target.value)} />
      </label>
      {partialText && <p aria-label="Partial transcript">Partial: {partialText}</p>}
      <button onClick={startSession} disabled={busy || state === "closed"}>
        Start voice session
      </button>
      <button onClick={startPushToTalk} disabled={busy || !voiceSessionId || state === "listening"}>
        Push to talk
      </button>
      <button onClick={stopPushToTalk} disabled={busy || !voiceSessionId || state !== "listening"}>
        Stop talking
      </button>
      <button onClick={submitText} disabled={busy || !voiceSessionId || !recognizedText}>
        Submit voice text
      </button>
      <button onClick={interrupt} disabled={busy || !voiceSessionId}>
        Interrupt
      </button>
      {error && <p role="alert">{error}</p>}
    </div>
  );
}
