import React from "react";
import { stateClass } from "./state.js";
import { decideVoiceAcknowledgement, type RiskClass } from "../voiceApproval.js";

export interface ApprovalConfirmationProps {
  approvalId: string;
  actionDigest: string;
  riskClass: RiskClass;
  preview?: {
    machine_action?: Record<string, unknown>;
    machine_action_digest?: string;
    kind?: string;
    improvement_id?: string;
    human_summary?: string;
    scope_classification?: "localized" | "broad";
    safety_assessment?: string;
    proposal_review?: Record<string, unknown>;
    diff_stats?: { path: string; additions: number; deletions: number; preview_lines: string[] }[];
    verdict_artifact_id?: string | null;
  } | null;
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
  const isImprovement = preview?.kind === "improvement_merge" || !!preview?.human_summary;
  const summary = preview?.human_summary;
  const safety = preview?.safety_assessment;
  const diffStats = preview?.diff_stats || [];

  React.useEffect(() => {
    if (decision.decided) {
      onApprove(approvalId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [decision.decided, approvalId]);

  return (
    <div role="dialog" aria-label="Approval confirmation" className="card approval-card">
      <div className="approval-header">
        <h3>Review & Approval Required</h3>
        <span className={`chip ${stateClass(riskClass)}`}>{riskClass}</span>
      </div>

      {isImprovement && (
        <div style={{ marginBottom: "var(--space-3)" }}>
          {summary && <div className="approval-summary">{summary}</div>}
          {safety && (
            <div className="approval-safety">
              <strong>Safety Rationale:</strong> {safety}
            </div>
          )}
          {diffStats.length > 0 && (
            <div>
              <div className="approval-delta-title">Proposed Delta:</div>
              <ul className="approval-diff-list">
                {diffStats.map((f) => (
                  <li key={f.path}>
                    {f.path} <span className="approval-diff-add">+{f.additions}</span> /{" "}
                    <span className="approval-diff-del">-{f.deletions}</span>
                    {f.preview_lines && f.preview_lines.length > 0 && (
                      <pre className="pre-scroll" style={{ fontSize: "0.8em", marginTop: "var(--space-1)" }}>
                        {f.preview_lines.join("\n")}
                      </pre>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {action && (
        <div aria-label="Action preview" style={{ marginBottom: "var(--space-3)" }}>
          <p>
            Action: {String(action.kind ?? "action")} {String(action.capability_ref ?? "")}
          </p>
          <pre className="pre-scroll">{JSON.stringify(action.target ?? {}, null, 2)}</pre>
        </div>
      )}

      {decision.requiresOnScreenConfirmation && (
        <p role="alert" className="approval-alert">
          Voice alone cannot approve this action - confirm on screen.
        </p>
      )}

      <div className="action-cluster">
        <button className="btn btn-primary" onClick={() => onApprove(approvalId)}>
          <span>Approve</span> <span className="kbd-hint">Ctrl+Enter</span>
        </button>
        <button className="btn btn-danger" onClick={() => onReject(approvalId, "rejected on screen")}>
          Reject
        </button>
      </div>

      <p className="approval-digest-footer mono">
        Action digest: <code className="mono">{actionDigest}</code> ({approvalId})
      </p>
    </div>
  );
}
