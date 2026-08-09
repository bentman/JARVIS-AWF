import React from "react";

export interface RunSummary {
  run_id: string;
  workflow_ref: string;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface ApprovalSummary {
  approval_id: string;
  run_id: string;
  step_id: string;
  action_digest: string;
  status: string;
  reason: string | null;
  requested_at: string;
  decided_at: string | null;
  risk_class: string | null;
  preview?: { machine_action?: Record<string, unknown>; machine_action_digest?: string } | null;
}

export interface DashboardProps {
  runs: RunSummary[];
  approvals: ApprovalSummary[];
  onRefresh: () => void;
  refreshing: boolean;
}

/** `awf/run.list` and `awf/approval.list` were already real, working IPC
 * channels - `registerIpcHandlers` called the same `ProtocolClient` the CLI
 * uses - but nothing in the renderer ever called them. This is that
 * caller: real run/approval state, not dead plumbing. */
export function Dashboard({ runs, approvals, onRefresh, refreshing }: DashboardProps): React.JSX.Element {
  return (
    <div role="region" aria-label="Dashboard">
      <button onClick={onRefresh} disabled={refreshing}>
        {refreshing ? "Refreshing..." : "Refresh"}
      </button>
      <section aria-label="Runs">
        <h2>Runs</h2>
        {runs.length === 0 ? (
          <p>No runs yet.</p>
        ) : (
          <ul>
            {runs.map((run) => (
              <li key={run.run_id}>
                {run.workflow_ref} - {run.status} ({run.run_id})
              </li>
            ))}
          </ul>
        )}
      </section>
      <section aria-label="Pending approvals">
        <h2>Pending approvals</h2>
        {approvals.length === 0 ? (
          <p>No pending approvals.</p>
        ) : (
          <ul>
            {approvals.map((approval) => (
              <li key={approval.approval_id}>
                {approval.action_digest} - {approval.risk_class ?? "unknown risk class"} ({approval.approval_id})
                {approval.preview?.machine_action && (
                  <pre>{JSON.stringify(approval.preview.machine_action, null, 2)}</pre>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
