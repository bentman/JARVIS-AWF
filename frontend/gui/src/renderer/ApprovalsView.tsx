import React from "react";
import type { ApprovalSummary } from "./Dashboard.js";
import { stateClass } from "./state.js";

export interface ApprovalsViewProps {
  approvals: ApprovalSummary[];
}

export function ApprovalsView({ approvals }: ApprovalsViewProps): React.JSX.Element {
  return (
    <section aria-label="Pending approvals" className="card">
      <h2>Pending approvals</h2>
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

            return (
              <li key={approval.approval_id} className="proposal-item" style={{ marginBottom: "1rem" }}>
                <div className="row" style={{ alignItems: "center" }}>
                  <span className={`chip ${stateClass(approval.risk_class ?? "unknown risk class")}`}>
                    {approval.risk_class ?? "unknown risk class"}
                  </span>{" "}
                  <strong>{approval.approval_id}</strong>
                  <span className="mono muted" style={{ marginLeft: "0.5rem", fontSize: "0.85em" }}>
                    digest: {approval.action_digest}
                  </span>
                </div>

                {isImprovement && (
                  <div style={{ marginTop: "0.5rem" }}>
                    {summary && <div style={{ fontWeight: 600 }}>{summary}</div>}
                    {safety && (
                      <div style={{ fontSize: "0.85em", color: "var(--text-muted, #8b949e)", marginTop: "0.25rem" }}>
                        <strong>Safety:</strong> {safety}
                      </div>
                    )}
                    {diffStats.length > 0 && (
                      <div style={{ marginTop: "0.5rem" }}>
                        <div className="muted" style={{ fontSize: "0.85em" }}>Changed Files & Diff Preview:</div>
                        <ul style={{ margin: "0.25rem 0", paddingLeft: "1.2rem" }}>
                          {diffStats.map((f) => (
                            <li key={f.path} style={{ fontFamily: "monospace", fontSize: "0.85em" }}>
                              {f.path} <span style={{ color: "#2ea043" }}>+{f.additions}</span> /{" "}
                              <span style={{ color: "#da3633" }}>-{f.deletions}</span>
                              {f.preview_lines && f.preview_lines.length > 0 && (
                                <pre className="pre-scroll" style={{ fontSize: "0.8em", margin: "0.25rem 0" }}>
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

                {preview?.machine_action && (
                  <pre className="pre-scroll" style={{ marginTop: "0.5rem" }}>
                    {JSON.stringify(preview.machine_action, null, 2)}
                  </pre>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
