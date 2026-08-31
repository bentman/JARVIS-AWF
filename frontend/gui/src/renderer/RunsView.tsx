import React from "react";
import type { ArtifactSummary, ControlRunDetail, RunSummary } from "./Dashboard.js";
import { EvidencePanel } from "./EvidencePanel.js";
import { RunTimeline } from "./RunTimeline.js";
import { stateClass } from "./state.js";

export interface RunsViewProps {
  runs: RunSummary[];
  selectedRunDetail?: ControlRunDetail | null;
  onRunDetail?: (runId: string) => void;
  onArtifactRead?: (artifactId: string) => Promise<ArtifactSummary & { content: string }>;
  onApprove?: (approvalId: string) => Promise<void>;
  onReject?: (approvalId: string, reason: string) => Promise<void>;
  onImprovementRequestMerge?: (improvementId: string) => Promise<unknown>;
  onImprovementMerge?: (improvementId: string, approvalId: string) => Promise<unknown>;
  onImprovementReject?: (improvementId: string, reason?: string) => Promise<unknown>;
}

export function RunsView({
  runs,
  selectedRunDetail,
  onRunDetail,
  onArtifactRead,
  onApprove,
  onReject,
  onImprovementRequestMerge,
  onImprovementMerge,
  onImprovementReject,
}: RunsViewProps): React.JSX.Element {
  return (
    <>
      <section aria-label="Runs" className="card">
        <h2>Runs</h2>
        {runs.length === 0 ? (
          <p className="empty">No runs yet.</p>
        ) : (
          <ul className="list">
            {runs.map((run) => (
              <li key={run.run_id} className="row">
                <span>{run.workflow_ref}</span>
                <span className={`chip ${stateClass(run.status)}`}>{run.status}</span>
                {run.outcome?.response_text && <span className="row-reason">{run.outcome.response_text}</span>}
                <span className="mono row-reason">{run.run_id}</span>
                {onRunDetail && (
                  <button type="button" className="btn btn-secondary" onClick={() => onRunDetail(run.run_id)}>
                    View details
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>
      <section aria-label="Selected run detail" className="detail-stack">
        <h2>Selected run detail</h2>
        {selectedRunDetail ? (
          <>
            <RunTimeline
              detail={selectedRunDetail}
              onApprove={onApprove}
              onReject={onReject}
              onImprovementRequestMerge={onImprovementRequestMerge}
              onImprovementMerge={onImprovementMerge}
              onImprovementReject={onImprovementReject}
            />
            <EvidencePanel
              artifacts={selectedRunDetail.artifacts}
              verdicts={selectedRunDetail.verdicts}
              onArtifactRead={onArtifactRead}
            />
          </>
        ) : (
          <p className="empty">No run selected.</p>
        )}
      </section>
    </>
  );
}
