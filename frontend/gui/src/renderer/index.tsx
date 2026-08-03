import React from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App.js";

interface VoiceRoundTripResult {
  wake_detected: boolean;
  wake_score: number;
  speech_segments: [number, number][];
  command_text: string;
  command_language: string;
  response_text: string;
  response_audio_path: string;
}

declare global {
  interface Window {
    awf: {
      runStatus: (runId: string) => Promise<unknown>;
      runList: () => Promise<unknown>;
      approvalList: () => Promise<unknown>;
      approvalApprove: (approvalId: string) => Promise<unknown>;
      approvalReject: (approvalId: string, reason: string) => Promise<unknown>;
      voiceRoundTrip: (
        wakeAudioPath: string,
        commandAudioPath: string,
        voiceId: string,
        responseAudioOutPath: string,
      ) => Promise<VoiceRoundTripResult>;
    };
  }
}

const container = document.getElementById("root");
if (container) {
  const root = createRoot(container);
  root.render(
    React.createElement(App, {
      onApprove: (approvalId: string) => void window.awf.approvalApprove(approvalId),
      onReject: (approvalId: string, reason: string) => void window.awf.approvalReject(approvalId, reason),
      onVoiceRoundTrip: (wakeAudioPath: string, commandAudioPath: string) =>
        window.awf.voiceRoundTrip(wakeAudioPath, commandAudioPath, "bf_isabella", "/tmp/awf-gui-response.wav"),
    }),
  );
}
