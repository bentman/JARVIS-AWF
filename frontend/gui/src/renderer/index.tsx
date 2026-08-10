import React from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App.js";
import type { ApprovalSummary, ImprovementSummary, RunSummary } from "./Dashboard.js";
import type { MemorySearchResult } from "./MemoryPanel.js";
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
      approvalDetail: (approvalId: string) => Promise<unknown>;
      approvalApprove: (approvalId: string) => Promise<unknown>;
      approvalReject: (approvalId: string, reason: string) => Promise<unknown>;
      proposalGet: (proposalId: string) => Promise<ProposalSummary>;
      proposalPublish: (proposalId: string, digest: string) => Promise<unknown>;
      proposalReject: (proposalId: string, reason?: string) => Promise<unknown>;
      improvementList: () => Promise<ImprovementSummary[]>;
      improvementGet: (improvementId: string) => Promise<unknown>;
      improvementRequestMerge: (improvementId: string) => Promise<unknown>;
      improvementMerge: (improvementId: string, approvalId: string) => Promise<unknown>;
      improvementReject: (improvementId: string, reason?: string) => Promise<unknown>;
      memorySearch: (query: string, profile?: string) => Promise<MemorySearchResult>;
      memoryGet: (ref: string) => Promise<unknown>;
      memoryPropose: (path: string, summary?: string) => Promise<unknown>;
      memoryPublish: (proposalId: string, digest: string) => Promise<unknown>;
      memoryReject: (proposalId: string, reason?: string) => Promise<unknown>;
      memoryBlock: (ref: string) => Promise<unknown>;
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
      onImprovementList: () => window.awf.improvementList(),
      onProposalGet: (proposalId: string) => window.awf.proposalGet(proposalId),
      onProposalPublish: (proposalId: string, digest: string) => window.awf.proposalPublish(proposalId, digest),
      onProposalReject: (proposalId: string, reason?: string) => window.awf.proposalReject(proposalId, reason),
      onMemorySearch: (query: string) => window.awf.memorySearch(query),
      onMemoryBlock: (ref: string) => window.awf.memoryBlock(ref),
      onMemoryPublish: (proposalId: string, digest: string) => window.awf.memoryPublish(proposalId, digest),
      onMemoryReject: (proposalId: string, reason?: string) => window.awf.memoryReject(proposalId, reason),
    }),
  );
}
