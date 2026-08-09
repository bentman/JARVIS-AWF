import React from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App.js";
import type { ApprovalSummary, RunSummary } from "./Dashboard.js";
import type { ProposalSummary } from "./ProposalReview.js";

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
      runList: () => Promise<RunSummary[]>;
      approvalList: () => Promise<ApprovalSummary[]>;
      approvalApprove: (approvalId: string) => Promise<unknown>;
      approvalReject: (approvalId: string, reason: string) => Promise<unknown>;
      proposalGet: (proposalId: string) => Promise<ProposalSummary>;
      proposalPublish: (proposalId: string, digest: string) => Promise<unknown>;
      proposalReject: (proposalId: string, reason?: string) => Promise<unknown>;
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
      onVoiceRoundTrip: (wakeAudioPath: string, commandAudioPath: string, voiceId: string) =>
        window.awf.voiceRoundTrip(wakeAudioPath, commandAudioPath, voiceId, "/tmp/awf-gui-response.wav"),
      onRunList: () => window.awf.runList(),
      onApprovalList: () => window.awf.approvalList(),
      onProposalGet: (proposalId: string) => window.awf.proposalGet(proposalId),
      onProposalPublish: (proposalId: string, digest: string) => window.awf.proposalPublish(proposalId, digest),
      onProposalReject: (proposalId: string, reason?: string) => window.awf.proposalReject(proposalId, reason),
    }),
  );
}
