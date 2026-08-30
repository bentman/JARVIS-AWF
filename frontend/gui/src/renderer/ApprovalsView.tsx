import React, { useState } from "react";
import type { ApprovalSummary } from "./Dashboard.js";
import { stateClass } from "./state.js";

export interface ApprovalsViewProps {
  approvals: ApprovalSummary[];
  onApprove?: (approvalId: string) => Promise<void>;
  onReject?: (approvalId: string, reason: string) => Promise<void>;
}

export function ApprovalsView({ approvals, onApprove, onReject }: ApprovalsViewProps): React.JSX.Element {
  const [processingId, setProcessingId] = useState<string | null>(null);
  const [rejectReason, setRejectReason] = useState<string>("");
  const [showRejectForm, setShowRejectForm] = useState<string | null>(null);

  const handleApprove = async (approvalId: string) => {
    if (!onApprove) return;
    setProcessingId(approvalId);
    try {
      await onApprove(approvalId);
    } finally {
      setProcessingId(null);
    }
  };

  const handleReject = async (approvalId: string) => {
    if (!onReject) return;
    setProcessingId(approvalId);
    try {
      await onReject(approvalId, rejectReason || "Rejected by operator");
      setShowRejectForm(null);
      setRejectReason("");
    } finally {
      setProcessingId(null);
    }
  };

  return (
    <section aria-label="Pending approvals" className="card">
      <h2>Pending Approvals</h2>
      <div style={{ marginBottom: "1rem", padding: "0.75rem", background: "var(--bg-info, rgba(88, 166, 255, 0.08))", border: "1px solid var(--accent, #58a6ff)", borderRadius: "6px" }}>
        <div style={{ fontSize: "0.9em", fontWeight: 500, marginBottom: "0.5rem" }}>
          📋 What is an Approval?
        </div>
        <div style={{ fontSize: "0.85em", color: "var(--text-secondary, #8b949e)", lineHeight: 1.5 }}>
          An approval is a human authorization gate. AWF has determined that this action is ready and safe, but requires your explicit approval before proceeding.
          <br />
          <strong>For improvements:</strong> You've reviewed the proposal, validated it passed all checks, and now must approve the merge into your main branch.
        </div>
      </div>
      {approvals.length === 0 ? (
        <p className="empty">No pending approvals.</p>
      ) : (
        <ul className="list">
          {approvals.map((approval) => {
            const preview = approval.preview;
            const isImprovement = preview?.kind === "improvement_merge" || !!preview?.proposal || !!preview?.human_summary;
            const summary = preview?.human_summary;
            const safety = preview?.safety_assessment;
            const diffStats = preview?.diff_stats || [];
            const improvementId = preview?.improvement_id;

            return (
              <li key={approval.approval_id} className="proposal-item" style={{ marginBottom: "1.5rem", paddingBottom: "1rem", borderBottom: "1px solid var(--border-color, rgba(255,255,255,0.1))" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "start" }}>
                  <div>
                    <div className="row" style={{ alignItems: "center", marginBottom: "0.5rem" }}>
                      <span className={`chip ${stateClass(approval.risk_class ?? "unknown risk class")}`} style={{ marginRight: "0.5rem" }}>
                        {approval.risk_class ?? "unknown risk class"} APPROVAL
                      </span>
                      <strong style={{ fontSize: "0.95em" }}>Required: {approval.approval_id}</strong>
                    </div>
                    {improvementId && (
                      <div className="muted" style={{ fontSize: "0.8em", marginBottom: "0.5rem" }}>
                        For proposal: <code>{improvementId}</code>
                      </div>
                    )}
                  </div>
                  <span className="mono muted" style={{ fontSize: "0.75em", textAlign: "right" }}>
                    {approval.requested_at}
                  </span>
                </div>

                {isImprovement && (
                  <div style={{ marginTop: "0.75rem" }}>
                    {summary && (
                      <div style={{ fontWeight: 500, fontSize: "0.95em", marginBottom: "0.5rem", color: "var(--text-main, #c9d1d9)" }}>
                        {summary}
                      </div>
                    )}
                    {safety && (
                      <div style={{ fontSize: "0.85em", color: "var(--text-secondary, #8b949e)", marginTop: "0.4rem", padding: "0.5rem", background: "var(--bg-subtle, rgba(255,255,255,0.03))", borderLeft: "3px solid var(--accent, #58a6ff)", borderRadius: "2px" }}>
                        <strong>Safety:</strong> {safety}
                      </div>
                    )}
                    {diffStats.length > 0 && (
                      <div style={{ marginTop: "0.5rem" }}>
                        <div className="muted" style={{ fontSize: "0.85em", fontWeight: 600 }}>Changed Files:</div>
                        <ul style={{ margin: "0.25rem 0", paddingLeft: "1.2rem" }}>
                          {diffStats.map((f) => (
                            <li key={f.path} style={{ fontFamily: "monospace", fontSize: "0.8em", color: "var(--text-secondary, #8b949e)" }}>
                              {f.path} <span style={{ color: "#2ea043" }}>+{f.additions}</span> / <span style={{ color: "#da3633" }}>-{f.deletions}</span>
                              {f.preview_lines && f.preview_lines.length > 0 && (
                                <pre className="pre-scroll" style={{ fontSize: "0.75em", margin: "0.25rem 0", background: "rgba(0,0,0,0.2)", padding: "0.25rem" }}>
                                  {f.preview_lines.slice(0, 6).join("\n")}
                                </pre>
                              )}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                )}

                {preview?.machine_action && (
                  <pre className="pre-scroll" style={{ marginTop: "0.5rem" }}>
                    {JSON.stringify(preview.machine_action, null, 2)}
                  </pre>
                )}

                <div style={{ marginTop: "1rem", paddingTop: "0.75rem", borderTop: "1px solid var(--border-color, rgba(255,255,255,0.1))", display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                  {onApprove && (
                    <button
                      type="button"
                      className="btn btn-primary"
                      disabled={processingId === approval.approval_id}
                      onClick={() => void handleApprove(approval.approval_id)}
                      style={{ flex: "1" }}
                    >
                      {processingId === approval.approval_id ? "Approving..." : "✓ Approve this action"}
                    </button>
                  )}
                  {onReject && showRejectForm !== approval.approval_id && (
                    <button
                      type="button"
                      className="btn btn-danger"
                      disabled={processingId === approval.approval_id}
                      onClick={() => setShowRejectForm(approval.approval_id)}
                      style={{ flex: "1" }}
                    >
                      ✗ Reject this action
                    </button>
                  )}
                </div>

                {showRejectForm === approval.approval_id && (
                  <div style={{ marginTop: "0.75rem", padding: "0.75rem", background: "var(--bg-subtle, rgba(255,255,255,0.03))", borderRadius: "4px", borderLeft: "3px solid var(--danger, #da3633)" }}>
                    <label style={{ display: "block", fontSize: "0.85em", marginBottom: "0.5rem" }}>
                      Reason for rejection (optional):
                    </label>
                    <textarea
                      value={rejectReason}
                      onChange={(e) => setRejectReason(e.target.value)}
                      placeholder="e.g., Change needs more review, concerns about scope, etc."
                      style={{
                        width: "100%",
                        minHeight: "60px",
                        padding: "0.5rem",
                        background: "var(--bg-input, rgba(0,0,0,0.2))",
                        border: "1px solid var(--border-color, rgba(255,255,255,0.1))",
                        borderRadius: "3px",
                        color: "var(--text-main, #c9d1d9)",
                        fontFamily: "monospace",
                        fontSize: "0.85em",
                      }}
                    />
                    <div style={{ marginTop: "0.5rem", display: "flex", gap: "0.5rem" }}>
                      <button
                        type="button"
                        className="btn btn-danger"
                        disabled={processingId === approval.approval_id}
                        onClick={() => void handleReject(approval.approval_id)}
                      >
                        {processingId === approval.approval_id ? "Rejecting..." : "Confirm rejection"}
                      </button>
                      <button
                        type="button"
                        className="btn btn-secondary"
                        disabled={processingId === approval.approval_id}
                        onClick={() => {
                          setShowRejectForm(null);
                          setRejectReason("");
                        }}
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
