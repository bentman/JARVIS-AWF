import React from "react";
import type { ControlRunDetail } from "./Dashboard.js";
import { stateClass } from "./state.js";

export interface RunTimelineProps {
  detail: ControlRunDetail;
  onApprove?: (approvalId: string) => Promise<void>;
  onReject?: (approvalId: string, reason: string) => Promise<void>;
  onImprovementRequestMerge?: (improvementId: string) => Promise<unknown>;
  onImprovementMerge?: (improvementId: string, approvalId: string) => Promise<unknown>;
  onImprovementReject?: (improvementId: string, reason?: string) => Promise<unknown>;
}

export function RunTimeline({
  detail,
  onApprove,
  onReject,
  onImprovementRequestMerge,
  onImprovementMerge,
  onImprovementReject,
}: RunTimelineProps): React.JSX.Element {
  const timeline = detail.operator_timeline ?? [];
  const [approvalRejecting, setApprovalRejecting] = React.useState<string | null>(null);
  const [approvalReason, setApprovalReason] = React.useState("");
  const [proposalRejecting, setProposalRejecting] = React.useState<string | null>(null);
  const [proposalReason, setProposalReason] = React.useState("");
  const currentWorkItem = detail.operator_work_items?.[0];
  const failedSteps = detail.run.steps.filter((step) => step.status === "FAILED");

  return (
    <section aria-label="Run detail" className="operate-band">
      <h2>Run detail</h2>
      <div className="run-status-lane">
        <span>{detail.run.workflow_ref}</span>
        <span className={`chip ${stateClass(detail.run.status)}`}>{detail.run.status}</span>
        <span className="mono">{detail.run.run_id}</span>
      </div>
      <div className="run-now">
        <div>
          <span className="stat-label">Current action</span>
          <strong>{currentWorkItem?.title ?? detail.outcome?.next_action ?? "No operator action required"}</strong>
        </div>
        {failedSteps.length > 0 && (
          <div>
            <span className="stat-label">Failure</span>
            <strong>{failedSteps[0].node_id}: {failedSteps[0].status}</strong>
          </div>
        )}
      </div>
      {detail.outcome && (
        <div className="run-outcome">
          <p>{detail.outcome.response_text}</p>
          <div>Next: {detail.outcome.next_action}</div>
        </div>
      )}
      {detail.operator_next_actions && detail.operator_next_actions.length > 0 && (
        <div className="next-action-box">
          <strong>{detail.operator_next_actions[0].label}</strong>
          <span>{detail.operator_next_actions[0].description}</span>
          <code>{detail.operator_next_actions[0].command}</code>
        </div>
      )}
      {timeline.length === 0 ? (
        <>
          <h3>Timeline</h3>
          <ul className="list">
            {detail.run.steps.map((step) => (
              <li key={step.step_id}>
                {step.node_id}: {step.status} (attempt {step.attempt})
              </li>
            ))}
          </ul>
        </>
      ) : (
        <>
          <h3>Timeline</h3>
          <ol className="timeline-list">
            {timeline.map((item, index) => (
              <li key={`${item.kind}-${item.event_id ?? item.approval_id ?? item.artifact_id ?? item.step_id ?? index}`}>
                <span className={`dot ${stateClass(item.status)}`} />
                <div className="timeline-entry">
                  <div className="timeline-entry-title">
                    <strong>{item.title}</strong>
                    <span className={`chip ${stateClass(item.status)}`}>{item.status}</span>
                  </div>
                  <div className="row-reason">
                    {item.description}
                    {item.occurred_at ? ` - ${item.occurred_at}` : ""}
                  </div>
                  {item.kind === "approval" && item.status === "pending" && item.approval_id && (
                    <div className="inline-actions">
                      {onApprove && (
                        <button type="button" className="btn btn-primary" onClick={() => void onApprove(item.approval_id!)}>
                          Approve
                        </button>
                      )}
                      {onReject && (
                        <button
                          type="button"
                          className="btn btn-danger"
                          onClick={() => setApprovalRejecting(item.approval_id!)}
                        >
                          Reject
                        </button>
                      )}
                    </div>
                  )}
                  {approvalRejecting === item.approval_id && item.approval_id && (
                    <div className="decision-form">
                      <label>
                        Rejection reason
                        <textarea
                          value={approvalReason}
                          onChange={(event) => setApprovalReason(event.currentTarget.value)}
                        />
                      </label>
                      <div className="inline-actions">
                        <button
                          type="button"
                          className="btn btn-danger"
                          onClick={() => {
                            void onReject?.(item.approval_id!, approvalReason || "Rejected by operator");
                            setApprovalRejecting(null);
                            setApprovalReason("");
                          }}
                        >
                          Confirm rejection
                        </button>
                        <button type="button" className="btn btn-secondary" onClick={() => setApprovalRejecting(null)}>
                          Cancel
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              </li>
            ))}
          </ol>
        </>
      )}
      {detail.improvements.length > 0 && (
        <div>
          <h3>Follow-up proposals</h3>
          <ul className="list">
            {detail.improvements.map((proposal) => (
              <li key={proposal.improvement_id} className="row">
                <span>{proposal.human_summary || proposal.summary}</span>
                <span className={`chip ${stateClass(proposal.status)}`}>{proposal.status}</span>
                {proposal.status === "ready_for_review" && onImprovementRequestMerge && (
                  <button
                    type="button"
                    className="btn btn-primary"
                    onClick={() => void onImprovementRequestMerge(proposal.improvement_id)}
                  >
                    Request merge approval
                  </button>
                )}
                {proposal.approval?.status === "approved" && onImprovementMerge && (
                  <button
                    type="button"
                    className="btn btn-primary"
                    onClick={() => void onImprovementMerge(proposal.improvement_id, proposal.approval!.approval_id)}
                  >
                    Merge
                  </button>
                )}
                {proposal.status !== "merged" && proposal.status !== "rejected" && onImprovementReject && (
                  <button
                    type="button"
                    className="btn btn-danger"
                    onClick={() => setProposalRejecting(proposal.improvement_id)}
                  >
                    Reject
                  </button>
                )}
                {proposalRejecting === proposal.improvement_id && (
                  <div className="decision-form">
                    <label>
                      Rejection reason
                      <textarea
                        value={proposalReason}
                        onChange={(event) => setProposalReason(event.currentTarget.value)}
                      />
                    </label>
                    <div className="inline-actions">
                      <button
                        type="button"
                        className="btn btn-danger"
                        onClick={() => {
                          void onImprovementReject?.(proposal.improvement_id, proposalReason || "Rejected by operator");
                          setProposalRejecting(null);
                          setProposalReason("");
                        }}
                      >
                        Confirm rejection
                      </button>
                      <button type="button" className="btn btn-secondary" onClick={() => setProposalRejecting(null)}>
                        Cancel
                      </button>
                    </div>
                  </div>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
      {Object.keys(detail.timeline).length > 0 && (
        <details>
          <summary>Advanced/raw event data</summary>
          <pre className="pre-scroll">{JSON.stringify(detail.timeline, null, 2)}</pre>
        </details>
      )}
    </section>
  );
}
