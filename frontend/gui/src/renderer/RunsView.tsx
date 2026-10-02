import React from "react";
import type { ArtifactSummary, ControlRunDetail, RunSummary } from "./Dashboard.js";
import { EvidencePanel } from "./EvidencePanel.js";
import { RunTimeline } from "./RunTimeline.js";
import { stateClass } from "./state.js";

export interface RunsViewProps {
  runs: RunSummary[];
  selectedRunDetail?: ControlRunDetail | null;
  onCloseDetail?: () => void;
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
  onCloseDetail,
  onRunDetail,
  onArtifactRead,
  onApprove,
  onReject,
  onImprovementRequestMerge,
  onImprovementMerge,
  onImprovementReject,
}: RunsViewProps): React.JSX.Element {
  const [statusFilter, setStatusFilter] = React.useState<string>("all");
  const [searchQuery, setSearchQuery] = React.useState<string>("");
  const [copiedId, setCopiedId] = React.useState<string | null>(null);

  const copyRunId = (id: string) => {
    void navigator.clipboard.writeText(id);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 1500);
  };

  const filteredRuns = React.useMemo(() => {
    return runs.filter((run) => {
      if (statusFilter !== "all" && run.status.toUpperCase() !== statusFilter.toUpperCase()) {
        return false;
      }
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        return (
          run.workflow_ref.toLowerCase().includes(q) ||
          run.run_id.toLowerCase().includes(q) ||
          (run.outcome?.response_text ?? "").toLowerCase().includes(q)
        );
      }
      return true;
    });
  }, [runs, statusFilter, searchQuery]);

  return (
    <>
      <section aria-label="Runs" className="card">
        <div className="section-heading">
          <div>
            <h2>Runs</h2>
            <p className="muted">Filter and inspect workflow execution lifecycles and artifacts.</p>
          </div>
          <span className="chip state-ok">{runs.length} Total</span>
        </div>
        {runs.length > 0 && (
          <div className="action-cluster" style={{ marginTop: 0, marginBottom: "var(--space-3)", justifyContent: "space-between" }}>
            <div className="row">
              {["all", "RUNNING", "FAILED", "SUCCEEDED"].map((status) => (
                <button
                  key={status}
                  type="button"
                  className={`chip chip-btn ${statusFilter === status ? "state-ok" : ""}`}
                  onClick={() => setStatusFilter(status)}
                  style={{ fontWeight: statusFilter === status ? 600 : 400 }}
                >
                  {status.toUpperCase()}
                </button>
              ))}
            </div>
            <input
              aria-label="Filter runs"
              className="mono"
              placeholder="Search runs..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              style={{ maxWidth: "200px", padding: "var(--space-1) var(--space-2)", fontSize: "var(--text-xs)" }}
            />
          </div>
        )}
        {runs.length === 0 ? (
          <p className="empty">No runs yet.</p>
        ) : filteredRuns.length === 0 ? (
          <div style={{ padding: "var(--space-2) 0" }}>
            <p className="empty" style={{ margin: 0, marginBottom: "var(--space-2)" }}>No runs match current filter.</p>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={() => { setStatusFilter("all"); setSearchQuery(""); }}
            >
              Clear filters
            </button>
          </div>
        ) : (
          <ul className="list">
            {filteredRuns.map((run) => (
              <li key={run.run_id} className="row">
                <span>{run.workflow_ref}</span>
                <span className={`chip ${stateClass(run.status)}`}>{run.status}</span>
                {run.outcome?.response_text && <span className="row-reason">{run.outcome.response_text}</span>}
                <span className="mono row-reason">{run.run_id}</span>
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  style={{ fontSize: "11px", padding: "1px 6px" }}
                  onClick={() => copyRunId(run.run_id)}
                  title="Copy run ID"
                >
                  {copiedId === run.run_id ? "Copied" : "Copy ID"}
                </button>
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
              onClose={onCloseDetail}
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
