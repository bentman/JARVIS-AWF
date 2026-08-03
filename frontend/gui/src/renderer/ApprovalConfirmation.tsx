import React from "react";
import { decideVoiceAcknowledgement, type RiskClass } from "../voiceApproval.js";

export interface ApprovalConfirmationProps {
  approvalId: string;
  actionDigest: string;
  riskClass: RiskClass;
  voiceConfirmed: boolean;
  onApprove: (approvalId: string) => void;
  onReject: (approvalId: string, reason: string) => void;
}

/** Section 16.4's approval rule, rendered: the exact action digest is always
 * shown, and an R2+ decision is NEVER granted just because `voiceConfirmed`
 * is true - only a real click (onApprove fired by the button) counts. */
export function ApprovalConfirmation({
  approvalId,
  actionDigest,
  riskClass,
  voiceConfirmed,
  onApprove,
  onReject,
}: ApprovalConfirmationProps): React.JSX.Element {
  const decision = decideVoiceAcknowledgement(riskClass, voiceConfirmed);

  React.useEffect(() => {
    if (decision.decided) {
      onApprove(approvalId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [decision.decided, approvalId]);

  return (
    <div role="dialog" aria-label="Approval confirmation">
      <p>
        Action digest: <code>{actionDigest}</code>
      </p>
      <p>Risk class: {riskClass}</p>
      {decision.requiresOnScreenConfirmation && (
        <p role="alert">Voice alone cannot approve this action - confirm on screen.</p>
      )}
      <button onClick={() => onApprove(approvalId)}>Approve</button>
      <button onClick={() => onReject(approvalId, "rejected on screen")}>Reject</button>
    </div>
  );
}
