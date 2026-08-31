import React from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";
import { App } from "./App.js";
import type {
  ApprovalSummary,
  ArtifactSummary,
  ControlRunDetail,
  ControlSummary,
  ImprovementSummary,
  LlmModelsReport,
  RunSummary,
} from "./Dashboard.js";
import type { MemorySearchResult } from "./MemoryPanel.js";
import type { ProposalSummary } from "./ProposalReview.js";
import type { RegistryEntry } from "./RegistryActions.js";
import type { VoiceSessionResult, VoiceSubmitTextResult } from "./VoiceActivation.js";

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
      runStart: (workflowRef: string, input?: Record<string, unknown>) => Promise<{ run_id: string; status: string }>;
      runStatus: (runId: string) => Promise<unknown>;
      controlSummary: () => Promise<ControlSummary>;
      controlRunDetail: (runId: string) => Promise<ControlRunDetail>;
      systemReadiness: () => Promise<unknown>;
      llmServers: () => Promise<unknown>;
      llmModels: () => Promise<LlmModelsReport>;
      llmServeStatus: () => Promise<unknown>;
      registryValidate: (path: string, kind?: string) => Promise<unknown>;
      registryPublish: (path: string, kind: string) => Promise<unknown>;
      registryReindex: () => Promise<unknown>;
      registryRetire: (kind: string, name: string, version: string) => Promise<unknown>;
      registryTrust: (kind: string, name: string, version: string, status: string) => Promise<unknown>;
      registryList: (kind: string) => Promise<RegistryEntry[]>;
      registryGet: (kind: string, name: string, version: string) => Promise<Record<string, unknown>>;
      artifactList: (runId: string) => Promise<ArtifactSummary[]>;
      artifactRead: (artifactId: string) => Promise<ArtifactSummary & { content: string }>;
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
      voiceSessionStart: (title?: string, wakeEnabled?: boolean) => Promise<VoiceSessionResult>;
      voiceSessionStop: (voiceSessionId: string, reason?: string) => Promise<VoiceSessionResult>;
      voicePushToTalkStart: (voiceSessionId: string, turnId?: string) => Promise<VoiceSessionResult>;
      voicePushToTalkStop: (voiceSessionId: string, turnId?: string) => Promise<VoiceSessionResult>;
      voiceInterrupt: (voiceSessionId: string, turnId?: string) => Promise<VoiceSessionResult>;
      voiceSubmitText: (
        voiceSessionId: string,
        text: string,
        workflowRef: string | undefined,
        voiceProfileRef?: string,
        turnId?: string,
      ) => Promise<VoiceSubmitTextResult>;
      voiceSpeakText: (
        text: string,
        voiceId: string | undefined,
        responseAudioOutPath?: string,
      ) => Promise<{ response_audio_path: string }>;
      voiceTranscribe: (audioData: ArrayBuffer) => Promise<{ text: string; language: string }>;
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
      onTextSubmit: (text: string, workflowRef: string) => window.awf.runStart(workflowRef, { objective: text }),
      onRunStart: (workflowRef: string, input?: Record<string, unknown>) => window.awf.runStart(workflowRef, input ?? {}),
      onVoiceSessionStart: (title?: string, wakeEnabled?: boolean) =>
        window.awf.voiceSessionStart(title, wakeEnabled),
      onVoicePushToTalkStart: (voiceSessionId: string, turnId: string) =>
        window.awf.voicePushToTalkStart(voiceSessionId, turnId),
      onVoicePushToTalkStop: (voiceSessionId: string, turnId: string) =>
        window.awf.voicePushToTalkStop(voiceSessionId, turnId),
      onVoiceInterrupt: (voiceSessionId: string, turnId: string) => window.awf.voiceInterrupt(voiceSessionId, turnId),
      onVoiceSubmitText: (
        voiceSessionId: string,
        text: string,
        workflowRef: string | undefined,
        voiceProfileRef: string | undefined,
        turnId: string,
      ) => window.awf.voiceSubmitText(voiceSessionId, text, workflowRef, voiceProfileRef, turnId),
      onVoiceSpeakText: (text: string, voiceId: string | undefined, responseAudioOutPath?: string) =>
        window.awf.voiceSpeakText(text, voiceId, responseAudioOutPath),
      onRunList: () => window.awf.runList(),
      onApprovalList: () => window.awf.approvalList(),
      onApprovalDetail: (approvalId: string) =>
        window.awf.approvalDetail(approvalId) as Promise<{ approval: ApprovalSummary; preview?: { machine_action?: Record<string, unknown>; machine_action_digest?: string } | null }>,
      onImprovementList: () => window.awf.improvementList(),
      onControlSummary: () => window.awf.controlSummary(),
      onControlRunDetail: (runId: string) => window.awf.controlRunDetail(runId),
      onRegistryValidate: (path: string, kind?: string) => window.awf.registryValidate(path, kind),
      onRegistryPublish: (path: string, kind: string) => window.awf.registryPublish(path, kind),
      onRegistryReindex: () => window.awf.registryReindex(),
      onRegistryRetire: (kind: string, name: string, version: string) =>
        window.awf.registryRetire(kind, name, version),
      onRegistryTrust: (kind: string, name: string, version: string, status: string) =>
        window.awf.registryTrust(kind, name, version, status),
      onRegistryList: (kind: string) => window.awf.registryList(kind),
      onRegistryGet: (kind: string, name: string, version: string) => window.awf.registryGet(kind, name, version),
      onArtifactRead: (artifactId: string) => window.awf.artifactRead(artifactId),
      onLlmModels: () => window.awf.llmModels(),
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
