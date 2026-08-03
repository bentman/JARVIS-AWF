import React, { useRef, useState } from "react";
import { ApprovalConfirmation } from "./ApprovalConfirmation.js";
import { Transcript, type TranscriptEntry } from "./Transcript.js";
import { VoiceActivation } from "./VoiceActivation.js";
import type { RiskClass } from "../voiceApproval.js";

export interface PendingApproval {
  approvalId: string;
  actionDigest: string;
  riskClass: RiskClass;
}

export interface VoiceRoundTripFn {
  (wakeAudioPath: string, commandAudioPath: string): Promise<{
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
}

export function App({
  initialTranscript = [],
  pendingApproval,
  voiceConfirmed = false,
  onApprove,
  onReject,
  onVoiceRoundTrip,
}: AppProps): React.JSX.Element {
  const [entries, setEntries] = useState<TranscriptEntry[]>(initialTranscript);
  const nextId = useRef(initialTranscript.length);

  const handleRoundTrip = async (wakeAudioPath: string, commandAudioPath: string) => {
    if (!onVoiceRoundTrip) return;
    const result = await onVoiceRoundTrip(wakeAudioPath, commandAudioPath);
    setEntries((prev) => [
      ...prev,
      { id: nextId.current++, speaker: "Operator (voice)", text: result.command_text },
      { id: nextId.current++, speaker: "AWF", text: result.response_text },
    ]);
  };

  return (
    <div>
      <Transcript entries={entries} />
      {onVoiceRoundTrip && <VoiceActivation onRoundTrip={handleRoundTrip} />}
      {pendingApproval && (
        <ApprovalConfirmation
          approvalId={pendingApproval.approvalId}
          actionDigest={pendingApproval.actionDigest}
          riskClass={pendingApproval.riskClass}
          voiceConfirmed={voiceConfirmed}
          onApprove={onApprove}
          onReject={onReject}
        />
      )}
    </div>
  );
}
