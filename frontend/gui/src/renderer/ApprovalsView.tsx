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
  const [rejectReasons, setRejectReasons] = useState<Record<string, string>>({});
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
      const reason = rejectReasons[approvalId]?.trim() || "Rejected by operator";
      await onReject(approvalId, reason);
      setShowRejectForm(null);
      setRejectReasons((prev) => {
        const next = { ...prev };
        delete next[approvalId];
        return next;
      });
    } finally {
      setProcessingId(null);
    }
  };

  return (
    <section aria-label="Pending approvals" className="card">
      <h2>Pending Approvals</h2>
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
              <li key={approval.approval_id} className="proposal-item" style={{ marginBottom: "1.5rem", paddingBottom: "1rem", borderBottom: "1px solid var(--border)" }}>
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
                  <div className="mono row-reason">Digest: {approval.action_digest}</div>
                  <span className="mono muted" style={{ fontSize: "0.75em", textAlign: "right" }}>
                    {approval.requested_at}
                  </span>
                </div>

                {isImprovement && (
                  <div style={{ marginTop: "0.75rem" }}>
                    {summary && (
                      <div style={{ fontWeight: 500, fontSize: "0.95em", marginBottom: "0.5rem", color: "var(--text)" }}>
                        {summary}
                      </div>
                    )}
                    {safety && (
                      <div style={{ fontSize: "0.85em", color: "var(--text-dim)", marginTop: "0.4rem", padding: "0.5rem", background: "var(--surface-raised)", borderLeft: "3px solid var(--accent)", borderRadius: "2px" }}>
                        <strong>Safety:</strong> {safety}
                      </div>
                    )}
                    {diffStats.length > 0 && (
                      <div style={{ marginTop: "0.5rem" }}>
                        <div className="muted" style={{ fontSize: "0.85em", fontWeight: 600 }}>Changed Files:</div>
                        <ul style={{ margin: "0.25rem 0", paddingLeft: "1.2rem" }}>
                          {diffStats.map((f) => (
                            <li key={f.path} style={{ fontFamily: "monospace", fontSize: "0.8em", color: "var(--text-dim)" }}>
                              {f.path} <span style={{ color: "var(--ok)" }}>+{f.additions}</span> / <span style={{ color: "var(--danger)" }}>-{f.deletions}</span>
                              {f.preview_lines && f.preview_lines.length > 0 && (
                                <pre className="pre-scroll" style={{ fontSize: "0.75em", margin: "0.25rem 0", background: "var(--surface-card)", padding: "0.25rem" }}>
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

                <div style={{ marginTop: "1rem", paddingTop: "0.75rem", borderTop: "1px solid var(--border)", display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                  {onApprove && (
                    <button
                      type="button"
                      className="btn btn-primary"
                      disabled={processingId === approval.approval_id}
                      onClick={() => void handleApprove(approval.approval_id)}
                      style={{ flex: "1" }}
                    >
                      {processingId === approval.approval_id ? "Approving..." : (
                        <>
                          <span>✓ Approve this action</span> <span className="kbd-hint">Ctrl+Enter</span>
                        </>
                      )}
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
                  <div style={{ marginTop: "0.75rem", padding: "0.75rem", background: "var(--surface-raised)", borderRadius: "var(--radius)", border: "1px solid var(--border)", borderLeft: "3px solid var(--danger)" }}>
                    <label
                      htmlFor={`reject-reason-${approval.approval_id}`}
                      style={{ display: "block", fontSize: "var(--text-sm)", marginBottom: "0.5rem", color: "var(--text-dim)" }}
                    >
                      Reason for rejection (optional):
                    </label>
                    <textarea
                      id={`reject-reason-${approval.approval_id}`}
                      value={rejectReasons[approval.approval_id] ?? ""}
                      onChange={(e) => setRejectReasons((prev) => ({ ...prev, [approval.approval_id]: e.target.value }))}
                      onKeyDown={(e) => {
                        if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
                          e.preventDefault();
                          void handleReject(approval.approval_id);
                        }
                      }}
                      placeholder="e.g., Change needs more review, concerns about scope, etc. (Ctrl+Enter to confirm)"
                      className="mono"
                      style={{
                        width: "100%",
                        minHeight: "64px",
                        padding: "var(--space-2)",
                        background: "var(--surface-input)",
                        border: "1px solid var(--border)",
                        borderRadius: "var(--radius)",
                        color: "var(--text)",
                        fontSize: "var(--text-sm)",
                      }}
                    />
                    <div className="action-cluster" style={{ marginTop: "0.5rem" }}>
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
                        onClick={() => setShowRejectForm(null)}
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
