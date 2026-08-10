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
          {approvals.map((approval) => (
            <li key={approval.approval_id} className="row">
              <span className="mono">
                {approval.action_digest} -{" "}
                <span className={`chip ${stateClass(approval.risk_class ?? "unknown risk class")}`}>
                  {approval.risk_class ?? "unknown risk class"}
                </span>{" "}
                ({approval.approval_id})
              </span>
              {approval.preview?.machine_action && (
                <pre className="pre-scroll">{JSON.stringify(approval.preview.machine_action, null, 2)}</pre>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
