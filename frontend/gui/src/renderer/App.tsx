import React, { useEffect, useRef, useState } from "react";
import { ApprovalConfirmation } from "./ApprovalConfirmation.js";
import { Dashboard, type ApprovalSummary, type ImprovementSummary, type RunSummary } from "./Dashboard.js";
import { MemoryPanel, type MemorySearchResult } from "./MemoryPanel.js";
import { ProposalReview, type ProposalSummary } from "./ProposalReview.js";
import { Transcript, type TranscriptEntry } from "./Transcript.js";
import { VoiceActivation, type VoiceSessionResult, type VoiceSubmitTextResult } from "./VoiceActivation.js";
import type { RiskClass } from "../voiceApproval.js";

export interface PendingApproval {
  approvalId: string;
  actionDigest: string;
  riskClass: RiskClass;
}

export interface VoiceSessionFns {
  onVoiceSessionStart?: (title?: string, wakeEnabled?: boolean) => Promise<VoiceSessionResult>;
  onVoicePushToTalkStart?: (voiceSessionId: string, turnId: string) => Promise<VoiceSessionResult>;
  onVoicePushToTalkStop?: (voiceSessionId: string, turnId: string) => Promise<VoiceSessionResult>;
  onVoiceInterrupt?: (voiceSessionId: string, turnId: string) => Promise<VoiceSessionResult>;
  onVoiceSubmitText?: (
    voiceSessionId: string,
    text: string,
    workflowRef: string,
    voiceProfileRef: string | undefined,
    turnId: string,
  ) => Promise<VoiceSubmitTextResult>;
  onVoiceSpeakText?: (
    text: string,
    voiceId: string | undefined,
    responseAudioOutPath: string,
  ) => Promise<{ response_audio_path: string }>;
}

export interface AppProps extends VoiceSessionFns {
  initialTranscript?: TranscriptEntry[];
  pendingApproval?: PendingApproval;
  voiceConfirmed?: boolean;
  onApprove: (approvalId: string) => void;
  onReject: (approvalId: string, reason: string) => void;
  onRunList?: () => Promise<RunSummary[]>;
  onApprovalList?: () => Promise<ApprovalSummary[]>;
  onImprovementList?: () => Promise<ImprovementSummary[]>;
  onProposalGet?: (proposalId: string) => Promise<ProposalSummary>;
  onProposalPublish?: (proposalId: string, digest: string) => Promise<unknown>;
  onProposalReject?: (proposalId: string, reason?: string) => Promise<unknown>;
  onMemorySearch?: (query: string) => Promise<MemorySearchResult>;
  onMemoryBlock?: (ref: string) => Promise<unknown>;
  onMemoryPublish?: (proposalId: string, digest: string) => Promise<unknown>;
  onMemoryReject?: (proposalId: string, reason?: string) => Promise<unknown>;
}

// An approval whose node never declared `riskClass` (Section 12.2) has no
// real value to show - treated as R2 here too, the same safe-never-R0/R1
// default `op_approval_approve` itself uses, not silently downgraded to
// something voice could auto-approve.
function toPendingApproval(approval: ApprovalSummary): PendingApproval {
  return {
    approvalId: approval.approval_id,
    actionDigest: approval.action_digest,
    riskClass: (approval.risk_class as RiskClass | null) ?? "R2",
  };
}

export function App({
  initialTranscript = [],
  pendingApproval,
  voiceConfirmed = false,
  onApprove,
  onReject,
  onVoiceSessionStart,
  onVoicePushToTalkStart,
  onVoicePushToTalkStop,
  onVoiceInterrupt,
  onVoiceSubmitText,
  onVoiceSpeakText,
  onRunList,
  onApprovalList,
  onImprovementList,
  onProposalGet,
  onProposalPublish,
  onProposalReject,
  onMemorySearch,
  onMemoryBlock,
  onMemoryPublish,
  onMemoryReject,
}: AppProps): React.JSX.Element {
  const [entries, setEntries] = useState<TranscriptEntry[]>(initialTranscript);
  const nextId = useRef(initialTranscript.length);
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [approvals, setApprovals] = useState<ApprovalSummary[]>([]);
  const [improvements, setImprovements] = useState<ImprovementSummary[]>([]);
  const [refreshing, setRefreshing] = useState(false);

  const refresh = async () => {
    if (!onRunList && !onApprovalList && !onImprovementList) return;
    setRefreshing(true);
    try {
      const [nextRuns, nextApprovals, nextImprovements] = await Promise.all([
        onRunList ? onRunList() : Promise.resolve(runs),
        onApprovalList ? onApprovalList() : Promise.resolve(approvals),
        onImprovementList ? onImprovementList() : Promise.resolve(improvements),
      ]);
      setRuns(nextRuns);
      setApprovals(nextApprovals);
      setImprovements(nextImprovements);
    } finally {
      setRefreshing(false);
    }
  };

  useEffect(() => {
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleVoiceSubmit = async (
    voiceSessionId: string,
    text: string,
    workflowRef: string,
    voiceProfileRef: string | undefined,
    turnId: string,
  ) => {
    if (!onVoiceSubmitText) throw new Error("voice submit is not available");
    const result = await onVoiceSubmitText(voiceSessionId, text, workflowRef, voiceProfileRef, turnId);
    setEntries((prev) => [
      ...prev,
      { id: nextId.current++, speaker: "Operator (voice)", text: result.recognized_text },
      {
        id: nextId.current++,
        speaker: result.voice?.voice_profile_ref ?? "AWF",
        text: result.response_text,
      },
    ]);
    if (onVoiceSpeakText) {
      const spoken = await onVoiceSpeakText(
        result.response_text,
        result.voice?.voice_id,
        "/tmp/awf-gui-live-response.wav",
      );
      if (typeof Audio !== "undefined") {
        void new Audio(spoken.response_audio_path).play().catch(() => undefined);
      }
    }
    return result;
  };

  const handleApprove = (approvalId: string) => {
    onApprove(approvalId);
    void refresh();
  };

  const handleReject = (approvalId: string, reason: string) => {
    onReject(approvalId, reason);
    void refresh();
  };

  // An explicit `pendingApproval` prop wins (a caller with its own source
  // of truth); otherwise the first real pending approval from the fetched
  // list is what the operator actually sees and can act on.
  const effectivePendingApproval = pendingApproval ?? (approvals.length > 0 ? toPendingApproval(approvals[0]) : undefined);

  return (
    <div>
      {(onRunList || onApprovalList || onImprovementList) && (
        <Dashboard
          runs={runs}
          approvals={approvals}
          improvements={improvements}
          onRefresh={() => void refresh()}
          refreshing={refreshing}
        />
      )}
      {onProposalGet && onProposalPublish && onProposalReject && (
        <ProposalReview
          onProposalGet={onProposalGet}
          onProposalPublish={onProposalPublish}
          onProposalReject={onProposalReject}
        />
      )}
      {onMemorySearch && onMemoryBlock && onMemoryPublish && onMemoryReject && (
        <MemoryPanel
          onMemorySearch={onMemorySearch}
          onMemoryBlock={onMemoryBlock}
          onMemoryPublish={onMemoryPublish}
          onMemoryReject={onMemoryReject}
        />
      )}
      <Transcript entries={entries} />
      {onVoiceSessionStart &&
        onVoicePushToTalkStart &&
        onVoicePushToTalkStop &&
        onVoiceInterrupt &&
        onVoiceSubmitText && (
          <VoiceActivation
            onSessionStart={onVoiceSessionStart}
            onPushToTalkStart={onVoicePushToTalkStart}
            onPushToTalkStop={onVoicePushToTalkStop}
            onInterrupt={onVoiceInterrupt}
            onSubmitText={handleVoiceSubmit}
          />
        )}
      {effectivePendingApproval && (
        <ApprovalConfirmation
          approvalId={effectivePendingApproval.approvalId}
          actionDigest={effectivePendingApproval.actionDigest}
          riskClass={effectivePendingApproval.riskClass}
          voiceConfirmed={voiceConfirmed}
          onApprove={handleApprove}
          onReject={handleReject}
        />
      )}
    </div>
  );
}
