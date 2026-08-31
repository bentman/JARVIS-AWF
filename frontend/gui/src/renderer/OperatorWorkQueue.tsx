import React from "react";
import type { OperatorAction, OperatorWorkItem } from "./Dashboard.js";
import { stateClass } from "./state.js";

export interface OperatorWorkQueueProps {
  items: OperatorWorkItem[];
  onRunDetail?: (runId: string) => void;
  onApprovalReview?: (approvalId: string, runId?: string | null) => void;
  onImprovementReview?: (improvementId: string, runId?: string | null) => void;
  onDoctor?: () => void;
  onLlmModels?: () => void;
  onStartWorkflow?: (workflowRef?: string | null) => void;
}

const GROUP_LABELS: Record<string, string> = {
  approval: "Blocked approvals",
  active_run: "Active runs",
  failed_run: "Failed runs",
  improvement: "Proposals",
  readiness: "Readiness",
  llm: "LLM configuration",
  doctor: "Doctor checks",
  completed_evidence: "Recent completed work",
  idle: "Ready",
};

function laneFor(item: OperatorWorkItem): string {
  if (item.kind === "idle") return "start";
  if (item.kind === "approval" || item.kind === "failed_run" || item.kind === "readiness" || item.kind === "llm" || item.kind === "doctor") {
    return "needs_action";
  }
  if (item.kind === "active_run") return "running";
  if (item.kind === "improvement" || item.kind === "completed_evidence") return "review";
  return "review";
}

const LANE_LABELS: Record<string, string> = {
  start: "Start work",
  needs_action: "Needs action",
  running: "Running",
  review: "Review / close out",
};

function actionLabel(action: OperatorAction | undefined, fallback: string): string {
  return action?.label || fallback;
}

export function OperatorWorkQueue({
  items,
  onRunDetail,
  onApprovalReview,
  onImprovementReview,
  onDoctor,
  onLlmModels,
  onStartWorkflow,
}: OperatorWorkQueueProps): React.JSX.Element {
  const grouped = items.reduce<Record<string, OperatorWorkItem[]>>((acc, item) => {
    const key = laneFor(item);
    acc[key] = [...(acc[key] ?? []), item];
    return acc;
  }, {});
  const orderedGroups = ["start", "needs_action", "running", "review"].filter((key) => grouped[key]?.length);

  const invoke = (item: OperatorWorkItem) => {
    const action = item.primary_action;
    if (action?.kind === "workflow.start") {
      onStartWorkflow?.(action.workflow_ref);
    } else if (action?.kind === "approval.review" && item.approval_id) {
      onApprovalReview?.(item.approval_id, item.run_id);
    } else if (action?.kind === "improvement.review" && item.improvement_id) {
      onImprovementReview?.(item.improvement_id, item.run_id);
    } else if (action?.kind === "doctor.open") {
      onDoctor?.();
    } else if (action?.kind === "llm.status" || action?.kind === "llm.models") {
      onLlmModels?.();
    } else if (item.run_id) {
      onRunDetail?.(item.run_id);
    }
  };

  return (
    <section aria-label="Operate queue" className="operate-band">
      <div className="section-heading">
        <h2>Work queue</h2>
      </div>
      {items.length === 0 ? (
        <p className="empty">No operator work items. Start a workflow when you are ready.</p>
      ) : (
        orderedGroups.map((group) => (
          <div key={group} className="queue-group">
            <h3>{LANE_LABELS[group] ?? "Other"}</h3>
            <ul className="list">
              {grouped[group].map((item) => (
                <li key={item.item_id} className="queue-item">
                  <div className="queue-item-main">
                    <span className={`chip ${stateClass(item.status)}`}>{item.status}</span>
                    <strong>{item.title}</strong>
                    <span className="chip">{GROUP_LABELS[item.kind] ?? item.kind}</span>
                    <span className="row-reason">{item.description}</span>
                  </div>
                  <div className="queue-actions">
                    <button type="button" className="btn btn-primary" onClick={() => invoke(item)}>
                      {actionLabel(item.primary_action, item.run_id ? "Open run" : "Open")}
                    </button>
                    {item.run_id && onRunDetail && (
                      <button type="button" className="btn btn-secondary" onClick={() => onRunDetail(item.run_id!)}>
                        Open run
                      </button>
                    )}
                    {item.primary_action?.command && <code>{item.primary_action.command}</code>}
                  </div>
                </li>
              ))}
            </ul>
          </div>
        ))
      )}
    </section>
  );
}
