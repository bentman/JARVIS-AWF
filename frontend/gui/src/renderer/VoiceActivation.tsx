import React, { useEffect, useRef, useState } from "react";
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
  sessionState?: VoiceSessionState;
  onSessionStateChange?: (state: VoiceSessionState) => void;
  onSessionStart: (title?: string, wakeEnabled?: boolean) => Promise<VoiceSessionResult>;
  onPushToTalkStart: (voiceSessionId: string, turnId: string) => Promise<VoiceSessionResult>;
  onPushToTalkStop: (voiceSessionId: string, turnId: string) => Promise<VoiceSessionResult>;
  onInterrupt: (voiceSessionId: string, turnId: string) => Promise<VoiceSessionResult>;
  onVoiceEvent?: (
    voiceSessionId: string,
    frameType: string,
    payload?: Record<string, unknown>,
    turnId?: string,
  ) => Promise<VoiceSessionResult>;
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

const ENERGY_THRESHOLD = 0.02;
const ENDPOINTING_SILENCE_MS = 800;

function voiceStateClass(state: VoiceSessionState): string {
  if (state === "speaking") return "state-ok";
  if (state === "listening" || state === "transcribing" || state === "submitting" || state === "recovering") {
    return "state-warn";
  }
  return "state-idle";
}

export interface VoiceActivationHandle {
  togglePushToTalk: () => void;
  toggleContinuousListening: () => void;
}

export const VoiceActivation = React.forwardRef<VoiceActivationHandle, VoiceActivationProps>(
  function VoiceActivation({
    defaultWorkflowRef = "",
    workflowOptions = [],
    sessionState,
    onSessionStateChange,
    onSessionStart,
    onPushToTalkStart,
    onPushToTalkStop,
    onInterrupt,
    onVoiceEvent,
    onSubmitText,
  }: VoiceActivationProps, ref): React.JSX.Element {
  const [voiceSessionId, setVoiceSessionId] = useState<string | null>(null);
  const [turnId, setTurnId] = useState<string>(nextTurnId());
  const [state, setState] = useState<VoiceSessionState>(sessionState ?? "idle");
  const [workflowRef, setWorkflowRef] = useState(defaultWorkflowRef);
  const [recognizedText, setRecognizedText] = useState("");
  const [partialText, setPartialText] = useState("");
  const [continuousListening, setContinuousListening] = useState(false);
  const [voiceProfileRef, setVoiceProfileRef] = useState("narrator@1.0.0");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const streamRef = useRef<MediaStream | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const vadIntervalRef = useRef<number | null>(null);
  const silenceStartRef = useRef<number | null>(null);
  const isSpeechActiveRef = useRef<boolean>(false);

  const continuousListeningRef = useRef<boolean>(continuousListening);
  continuousListeningRef.current = continuousListening;

  const stateRef = useRef<VoiceSessionState>(state);
  stateRef.current = state;

  const turnIdRef = useRef<string>(turnId);
  turnIdRef.current = turnId;

  const voiceSessionIdRef = useRef<string | null>(voiceSessionId);
  voiceSessionIdRef.current = voiceSessionId;

  const workflowRefRef = useRef<string>(workflowRef);
  workflowRefRef.current = workflowRef;

  const voiceProfileRefRef = useRef<string>(voiceProfileRef);
  voiceProfileRefRef.current = voiceProfileRef;

  useEffect(() => {
    if (sessionState && sessionState !== state) {
      setState(sessionState);
    }
  }, [sessionState]);

  const updateFrom = (result: VoiceSessionResult | VoiceSubmitTextResult) => {
    setState(result.state);
    onSessionStateChange?.(result.state);
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

  const startMediaRecorder = (stream: MediaStream) => {
    audioChunksRef.current = [];
    const recorder = new MediaRecorder(stream);
    recorder.ondataavailable = async (e) => {
      if (e.data.size > 0) {
        audioChunksRef.current.push(e.data);
        if (continuousListeningRef.current && window.awf?.voiceTranscribe) {
          try {
            const blob = new Blob(audioChunksRef.current, { type: recorder.mimeType });
            const wav = await blobToWav16(blob);
            const transcript = await window.awf.voiceTranscribe(wav);
            if (transcript?.text) {
              setPartialText(transcript.text);
              if (onVoiceEvent && voiceSessionIdRef.current) {
                void onVoiceEvent(voiceSessionIdRef.current, "stt.partial", { text: transcript.text }, turnIdRef.current);
              }
            }
          } catch {
            // Ignore interim transcription errors
          }
        }
      }
    };
    mediaRecorderRef.current = recorder;
    if (continuousListeningRef.current) {
      recorder.start(800);
    } else {
      recorder.start();
    }
  };

  const startPushToTalk = () =>
    withBusy(async () => {
      if (!voiceSessionId) return;
      if (!streamRef.current && navigator.mediaDevices?.getUserMedia) {
        streamRef.current = await navigator.mediaDevices.getUserMedia({ audio: true });
      }
      if (streamRef.current) {
        startMediaRecorder(streamRef.current);
      }
      const nextTurn = nextTurnId();
      setTurnId(nextTurn);
      setPartialText("");
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
        setPartialText("");
      }
      mediaRecorderRef.current = null;
      if (!continuousListeningRef.current) {
        streamRef.current?.getTracks().forEach((track) => track.stop());
        streamRef.current = null;
      }
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
      if (!continuousListeningRef.current) {
        streamRef.current?.getTracks().forEach((track) => track.stop());
        streamRef.current = null;
      }
      isSpeechActiveRef.current = false;
      silenceStartRef.current = null;
      setPartialText("");
      updateFrom(await onInterrupt(voiceSessionId, turnId));
    });

  const handleContinuousSpeechStart = async () => {
    if (!voiceSessionIdRef.current) return;
    if (stateRef.current === "speaking") {
      updateFrom(await onInterrupt(voiceSessionIdRef.current, turnIdRef.current));
    }
    const nextTurn = nextTurnId();
    setTurnId(nextTurn);
    turnIdRef.current = nextTurn;
    setPartialText("");
    if (streamRef.current) {
      startMediaRecorder(streamRef.current);
    }
    updateFrom(await onPushToTalkStart(voiceSessionIdRef.current, nextTurn));
  };

  const handleContinuousSpeechStop = async () => {
    if (!voiceSessionIdRef.current) return;
    const recorder = mediaRecorderRef.current;
    let finalUtterance = "";
    if (recorder && recorder.state !== "inactive") {
      try {
        finalUtterance = await new Promise<string>((resolve) => {
          recorder.onstop = async () => {
            try {
              const blob = new Blob(audioChunksRef.current, { type: recorder.mimeType });
              const wav = await blobToWav16(blob);
              const transcript = await window.awf.voiceTranscribe(wav);
              resolve(transcript.text || "");
            } catch {
              resolve("");
            }
          };
          recorder.stop();
        });
      } catch {
        finalUtterance = "";
      }
    }
    mediaRecorderRef.current = null;
    updateFrom(await onPushToTalkStop(voiceSessionIdRef.current, turnIdRef.current));
    setPartialText("");

    if (finalUtterance.trim()) {
      setRecognizedText(finalUtterance);
      try {
        const result = await onSubmitText(
          voiceSessionIdRef.current,
          finalUtterance,
          workflowRefRef.current || undefined,
          voiceProfileRefRef.current || undefined,
          turnIdRef.current,
        );
        updateFrom(result);
      } catch (err) {
        setError((err as Error).message);
      }
    }
  };

  const checkAudioEnergy = () => {
    if (!analyserRef.current || !continuousListeningRef.current || !voiceSessionIdRef.current) return;
    const analyser = analyserRef.current;
    const buffer = new Uint8Array(analyser.fftSize);
    analyser.getByteTimeDomainData(buffer);
    let sumSquares = 0;
    for (let i = 0; i < buffer.length; i++) {
      const norm = (buffer[i] - 128) / 128;
      sumSquares += norm * norm;
    }
    const rms = Math.sqrt(sumSquares / buffer.length);

    if (rms > ENERGY_THRESHOLD) {
      if (stateRef.current === "speaking") {
        void handleContinuousSpeechStart();
        isSpeechActiveRef.current = true;
        silenceStartRef.current = null;
      } else if (!isSpeechActiveRef.current && (stateRef.current === "idle" || stateRef.current === "armed")) {
        isSpeechActiveRef.current = true;
        silenceStartRef.current = null;
        void handleContinuousSpeechStart();
      } else {
        silenceStartRef.current = null;
      }
    } else {
      if (isSpeechActiveRef.current && stateRef.current === "listening") {
        if (!silenceStartRef.current) {
          silenceStartRef.current = Date.now();
        } else if (Date.now() - silenceStartRef.current >= ENDPOINTING_SILENCE_MS) {
          isSpeechActiveRef.current = false;
          silenceStartRef.current = null;
          void handleContinuousSpeechStop();
        }
      }
    }
  };

  const startContinuousVad = async () => {
    if (!navigator.mediaDevices?.getUserMedia) return;
    if (!streamRef.current) {
      streamRef.current = await navigator.mediaDevices.getUserMedia({ audio: true });
    }
    const AudioContextCtor =
      window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (AudioContextCtor) {
      const ctx = new AudioContextCtor();
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 512;
      const source = ctx.createMediaStreamSource(streamRef.current);
      source.connect(analyser);
      audioContextRef.current = ctx;
      analyserRef.current = analyser;
    }
    vadIntervalRef.current = window.setInterval(checkAudioEnergy, 50);
  };

  const stopContinuousVad = () => {
    if (vadIntervalRef.current !== null) {
      clearInterval(vadIntervalRef.current);
      vadIntervalRef.current = null;
    }
    analyserRef.current = null;
    if (audioContextRef.current) {
      void audioContextRef.current.close().catch(() => {});
      audioContextRef.current = null;
    }
    isSpeechActiveRef.current = false;
    silenceStartRef.current = null;
  };

  const toggleContinuousListening = async () => {
    if (continuousListening) {
      setContinuousListening(false);
      stopContinuousVad();
      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
        mediaRecorderRef.current.stop();
        mediaRecorderRef.current = null;
      }
      streamRef.current?.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    } else {
      setContinuousListening(true);
      try {
        await startContinuousVad();
      } catch (err) {
        setError((err as Error).message);
        setContinuousListening(false);
      }
    }
  };

  useEffect(() => {
    return () => {
      stopContinuousVad();
      streamRef.current?.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    };
  }, []);

  React.useImperativeHandle(
    ref,
    () => ({
      togglePushToTalk: () => {
        if (state === "listening") void stopPushToTalk();
        else void startPushToTalk();
      },
      toggleContinuousListening: () => {
        void toggleContinuousListening();
      },
    }),
    [state, continuousListening, startPushToTalk, stopPushToTalk],
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
          className={`btn ${continuousListening ? "btn-primary" : "btn-secondary"}`}
          onClick={() => void toggleContinuousListening()}
          disabled={busy || !voiceSessionId || state === "closed"}
        >
          {continuousListening ? "Continuous: On" : "Continuous: Off"}
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
        {partialText && (
          <div className="voice-partial mono" data-testid="voice-partial-text">
            Interim: {partialText}
          </div>
        )}
        {error && <span role="alert">{error}</span>}
      </div>
    </div>
  );
});
