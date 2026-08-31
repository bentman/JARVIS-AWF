import React, { useState } from "react";
import type { ArtifactSummary } from "./Dashboard.js";
import { stateClass } from "./state.js";

export interface EvidencePanelProps {
  artifacts: ArtifactSummary[];
  verdicts: ArtifactSummary[];
  onArtifactRead?: (artifactId: string) => Promise<ArtifactSummary & { content: string }>;
}

export function EvidencePanel({ artifacts, verdicts, onArtifactRead }: EvidencePanelProps): React.JSX.Element {
  const [openArtifact, setOpenArtifact] = useState<{ id: string; content: string } | null>(null);
  const evidence = artifacts.filter((artifact) =>
    ["verdict", "finding", "test-result", "report"].includes(artifact.artifact_type),
  );
  const visible = evidence.length > 0 ? evidence : artifacts;

  const viewArtifact = async (artifactId: string) => {
    if (!onArtifactRead) return;
    const artifact = await onArtifactRead(artifactId);
    setOpenArtifact({ id: artifactId, content: artifact.content });
  };

  return (
    <section aria-label="Evidence" className="card">
      <h2>Evidence</h2>
      {verdicts.length > 0 && (
        <div className="evidence-summary">
          <span className={`chip ${stateClass("ready")}`}>{verdicts.length} verdict{verdicts.length === 1 ? "" : "s"}</span>
        </div>
      )}
      {visible.length === 0 ? (
        <p className="empty">No evidence artifacts.</p>
      ) : (
        <ul className="list">
          {visible.map((artifact) => (
            <li key={artifact.artifact_id} className="row">
              <span>{artifact.relative_path}</span>
              <span className={`chip ${stateClass(artifact.artifact_type)}`}>{artifact.artifact_type}</span>
              <span className="mono row-reason">{artifact.artifact_id}</span>
              {onArtifactRead && (
                <button type="button" className="btn btn-secondary" onClick={() => void viewArtifact(artifact.artifact_id)}>
                  View
                </button>
              )}
            </li>
          ))}
        </ul>
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
    </section>
  );
}
