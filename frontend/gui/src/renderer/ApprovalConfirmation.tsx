import React from "react";
import { stateClass } from "./state.js";
import { decideVoiceAcknowledgement, type RiskClass } from "../voiceApproval.js";

export interface ApprovalConfirmationProps {
  approvalId: string;
  actionDigest: string;
  riskClass: RiskClass;
  preview?: { machine_action?: Record<string, unknown>; machine_action_digest?: string } | null;
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
  preview,
  voiceConfirmed,
  onApprove,
  onReject,
}: ApprovalConfirmationProps): React.JSX.Element {
  const decision = decideVoiceAcknowledgement(riskClass, voiceConfirmed);
  const action = preview?.machine_action;

  React.useEffect(() => {
    if (decision.decided) {
      onApprove(approvalId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [decision.decided, approvalId]);

  return (
    <div role="dialog" aria-label="Approval confirmation" className="card approval-card">
      <p>
        Action digest: <code className="mono">{actionDigest}</code>
      </p>
      {action && (
        <div aria-label="Action preview">
          <p>
            Action: {String(action.kind ?? "action")} {String(action.capability_ref ?? "")}
          </p>
          <pre className="pre-scroll">{JSON.stringify(action.target ?? {}, null, 2)}</pre>
        </div>
      )}
      <p className={`chip ${stateClass(riskClass)}`}>Risk class: {riskClass}</p>
      {decision.requiresOnScreenConfirmation && (
        <p role="alert">Voice alone cannot approve this action - confirm on screen.</p>
      )}
      <button className="btn btn-primary" onClick={() => onApprove(approvalId)}>
        Approve
      </button>
      <button className="btn btn-danger" onClick={() => onReject(approvalId, "rejected on screen")}>
        Reject
      </button>
    </div>
  );
}
