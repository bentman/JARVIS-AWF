import React, { useEffect, useRef, useState } from "react";
import { ApprovalConfirmation } from "./ApprovalConfirmation.js";
import { Dashboard, type ApprovalSummary, type RunSummary } from "./Dashboard.js";
import { Transcript, type TranscriptEntry } from "./Transcript.js";
import { VoiceActivation } from "./VoiceActivation.js";
import type { RiskClass } from "../voiceApproval.js";

export interface PendingApproval {
  approvalId: string;
  actionDigest: string;
  riskClass: RiskClass;
}

export interface VoiceRoundTripFn {
  (wakeAudioPath: string, commandAudioPath: string, voiceId: string): Promise<{
    command_text: string;
    response_text: string;
  }>;
}

export interface AppProps {
  initialTranscript?: TranscriptEntry[];
  pendingApproval?: PendingApproval;
  voiceConfirmed?: boolean;
  onApprove: (approvalId: string) => void;
  onReject: (approvalId: string, reason: string) => void;
  onVoiceRoundTrip?: VoiceRoundTripFn;
  onRunList?: () => Promise<RunSummary[]>;
  onApprovalList?: () => Promise<ApprovalSummary[]>;
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
  onVoiceRoundTrip,
  onRunList,
  onApprovalList,
}: AppProps): React.JSX.Element {
  const [entries, setEntries] = useState<TranscriptEntry[]>(initialTranscript);
  const nextId = useRef(initialTranscript.length);
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [approvals, setApprovals] = useState<ApprovalSummary[]>([]);
  const [refreshing, setRefreshing] = useState(false);

  const refresh = async () => {
    if (!onRunList && !onApprovalList) return;
    setRefreshing(true);
    try {
      const [nextRuns, nextApprovals] = await Promise.all([
        onRunList ? onRunList() : Promise.resolve(runs),
        onApprovalList ? onApprovalList() : Promise.resolve(approvals),
      ]);
      setRuns(nextRuns);
      setApprovals(nextApprovals);
    } finally {
      setRefreshing(false);
    }
  };

  useEffect(() => {
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleRoundTrip = async (wakeAudioPath: string, commandAudioPath: string, voiceId: string) => {
    if (!onVoiceRoundTrip) return;
    const result = await onVoiceRoundTrip(wakeAudioPath, commandAudioPath, voiceId);
    setEntries((prev) => [
      ...prev,
      { id: nextId.current++, speaker: "Operator (voice)", text: result.command_text },
      { id: nextId.current++, speaker: "AWF", text: result.response_text },
    ]);
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
      {(onRunList || onApprovalList) && (
        <Dashboard runs={runs} approvals={approvals} onRefresh={() => void refresh()} refreshing={refreshing} />
      )}
      <Transcript entries={entries} />
      {onVoiceRoundTrip && <VoiceActivation onRoundTrip={handleRoundTrip} />}
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
