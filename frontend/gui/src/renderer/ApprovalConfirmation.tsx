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
    <div role="dialog" aria-label="Approval confirmation" className="card approval-card" style={{ maxWidth: "680px", margin: "0 auto", padding: "1.25rem" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.75rem" }}>
        <h3 style={{ margin: 0 }}>Review & Approval Required</h3>
        <span className={`chip ${stateClass(riskClass)}`}>{riskClass}</span>
      </div>

      {isImprovement && (
        <div style={{ marginBottom: "1rem" }}>
          {summary && (
            <div style={{ fontSize: "1.05em", fontWeight: 500, lineHeight: 1.4, marginBottom: "0.5rem" }}>
              {summary}
            </div>
          )}
          {safety && (
            <div style={{ fontSize: "0.85em", padding: "0.5rem", background: "var(--bg-subtle, rgba(255,255,255,0.03))", borderLeft: "3px solid var(--accent, #58a6ff)", borderRadius: "2px", marginBottom: "0.75rem" }}>
              <strong style={{ color: "var(--text-main, #c9d1d9)" }}>Safety Rationale:</strong> {safety}
            </div>
          )}
          {diffStats.length > 0 && (
            <div style={{ marginTop: "0.5rem" }}>
              <div className="muted" style={{ fontSize: "0.85em", fontWeight: 600 }}>Proposed Delta:</div>
              <ul style={{ margin: "0.25rem 0", paddingLeft: "1.2rem" }}>
                {diffStats.map((f) => (
                  <li key={f.path} style={{ fontFamily: "monospace", fontSize: "0.85em" }}>
                    {f.path} <span style={{ color: "#2ea043" }}>+{f.additions}</span> /{" "}
                    <span style={{ color: "#da3633" }}>-{f.deletions}</span>
                    {f.preview_lines && f.preview_lines.length > 0 && (
                      <pre className="pre-scroll" style={{ fontSize: "0.8em", margin: "0.25rem 0", background: "var(--bg-subtle, #161b22)" }}>
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
        <div aria-label="Action preview" style={{ marginBottom: "1rem" }}>
          <p>
            Action: {String(action.kind ?? "action")} {String(action.capability_ref ?? "")}
          </p>
          <pre className="pre-scroll">{JSON.stringify(action.target ?? {}, null, 2)}</pre>
        </div>
      )}

      {decision.requiresOnScreenConfirmation && (
        <p role="alert" style={{ color: "var(--warning, #d29922)", fontSize: "0.85em" }}>
          Voice alone cannot approve this action - confirm on screen.
        </p>
      )}

      <div style={{ display: "flex", gap: "0.5rem", marginTop: "1rem" }}>
        <button className="btn btn-primary" onClick={() => onApprove(approvalId)}>
          Approve
        </button>
        <button className="btn btn-danger" onClick={() => onReject(approvalId, "rejected on screen")}>
          Reject
        </button>
      </div>

      <p className="muted mono" style={{ fontSize: "0.8em", marginTop: "0.75rem", marginBottom: 0 }}>
        Action digest: <code className="mono">{actionDigest}</code> ({approvalId})
      </p>
    </div>
  );
}
