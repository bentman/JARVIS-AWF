import React, { useState } from "react";
import type { ArtifactSummary, ControlRunDetail, RunSummary } from "./Dashboard.js";
import { stateClass } from "./state.js";

export interface RunsViewProps {
  runs: RunSummary[];
  selectedRunDetail?: ControlRunDetail | null;
  onRunDetail?: (runId: string) => void;
  onArtifactRead?: (artifactId: string) => Promise<ArtifactSummary & { content: string }>;
}

export function RunsView({ runs, selectedRunDetail, onRunDetail, onArtifactRead }: RunsViewProps): React.JSX.Element {
  const [openArtifact, setOpenArtifact] = useState<{ id: string; content: string } | null>(null);

  const viewArtifact = async (artifactId: string) => {
    if (!onArtifactRead) return;
    const artifact = await onArtifactRead(artifactId);
    setOpenArtifact({ id: artifactId, content: artifact.content });
  };

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
      <section aria-label="Selected run detail" className="card">
        <h2>Selected run detail</h2>
        {selectedRunDetail ? (
          <>
            <div>
              {selectedRunDetail.run.workflow_ref} - {selectedRunDetail.run.status}
            </div>
            {selectedRunDetail.outcome && (
              <div aria-label="Run outcome">
                <h3>Outcome</h3>
                <p>{selectedRunDetail.outcome.response_text}</p>
                <div>Next: {selectedRunDetail.outcome.next_action}</div>
                {selectedRunDetail.outcome.evidence.length > 0 && (
                  <ul className="list">
                    {selectedRunDetail.outcome.evidence.map((item) => (
                      <li key={`${item.artifact_id}-${item.path}`}>
                        Evidence: {item.type} - {item.path} ({item.artifact_id})
                      </li>
                    ))}
                  </ul>
                )}
                {selectedRunDetail.outcome.failures.length > 0 && (
                  <ul className="list">
                    {selectedRunDetail.outcome.failures.map((failure) => (
                      <li key={`${failure.step_id}-${failure.node_id}`}>
                        Failure: {failure.node_id} - {failure.failure_class ?? "failed"}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
            <ul className="list">
              {selectedRunDetail.run.steps.map((step) => (
                <li key={step.step_id}>
                  {step.node_id}: {step.status} (attempt {step.attempt})
                </li>
              ))}
            </ul>
            {selectedRunDetail.artifacts.length > 0 && (
              <div>
                <h3>Artifacts</h3>
                <ul className="list">
                  {selectedRunDetail.artifacts.map((artifact) => (
                    <li key={artifact.artifact_id}>
                      {artifact.relative_path} ({artifact.artifact_type})
                      {onArtifactRead && (
                        <button
                          type="button"
                          className="btn btn-secondary"
                          onClick={() => void viewArtifact(artifact.artifact_id)}
                        >
                          View
                        </button>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {selectedRunDetail.verdicts.length > 0 && (
              <div>
                <h3>Verdicts</h3>
                <ul className="list">
                  {selectedRunDetail.verdicts.map((verdict) => (
                    <li key={verdict.artifact_id}>
                      {verdict.relative_path} ({verdict.artifact_type})
                      {onArtifactRead && (
                        <button
                          type="button"
                          className="btn btn-secondary"
                          onClick={() => void viewArtifact(verdict.artifact_id)}
                        >
                          View
                        </button>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {Object.keys(selectedRunDetail.timeline).length > 0 && (
              <div>
                <h3>Timeline</h3>
                <pre className="pre-scroll">{JSON.stringify(selectedRunDetail.timeline, null, 2)}</pre>
              </div>
            )}
            {openArtifact && (
              <div>
                <button type="button" className="btn btn-secondary" onClick={() => setOpenArtifact(null)}>
                  Close
                </button>
                <pre aria-label="Artifact content" className="pre-scroll">
                  {openArtifact.content}
                </pre>
              </div>
            )}
          </>
        ) : (
          <p className="empty">No run selected.</p>
        )}
      </section>
    </>
  );
}
