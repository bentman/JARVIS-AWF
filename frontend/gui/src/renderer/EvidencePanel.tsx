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
  const [copied, setCopied] = useState(false);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [loadingId, setLoadingId] = useState<string | null>(null);
  const [readError, setReadError] = useState<string | null>(null);

  const evidence = artifacts.filter((artifact) =>
    ["verdict", "finding", "test-result", "report"].includes(artifact.artifact_type),
  );
  const visible = evidence.length > 0 ? evidence : artifacts;

  const copyArtifactId = (id: string) => {
    void navigator.clipboard.writeText(id);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 1500);
  };

  const viewArtifact = async (artifactId: string) => {
    if (!onArtifactRead) return;
    setReadError(null);
    setLoadingId(artifactId);
    try {
      const artifact = await onArtifactRead(artifactId);
      setOpenArtifact({ id: artifactId, content: artifact.content });
    } catch (err) {
      setReadError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoadingId(null);
    }
  };

  return (
    <section aria-label="Evidence" className="card">
      <h2>Evidence</h2>
      {verdicts.length > 0 && (
        <div className="evidence-summary">
          <span className={`chip ${stateClass("ready")}`}>{verdicts.length} verdict{verdicts.length === 1 ? "" : "s"}</span>
        </div>
      )}
      {readError && (
        <div style={{ display: "flex", alignItems: "center", gap: "var(--space-2)", margin: "var(--space-2) 0" }}>
          <p role="alert" style={{ margin: 0 }}>{readError}</p>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            style={{ fontSize: "11px", padding: "1px 6px" }}
            onClick={() => setReadError(null)}
          >
            Dismiss
          </button>
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
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                style={{ fontSize: "11px", padding: "1px 6px" }}
                onClick={() => copyArtifactId(artifact.artifact_id)}
                title="Copy artifact ID"
              >
                {copiedId === artifact.artifact_id ? "Copied" : "Copy ID"}
              </button>
              {onArtifactRead && (
                <button
                  type="button"
                  className="btn btn-secondary"
                  disabled={loadingId === artifact.artifact_id}
                  onClick={() => void viewArtifact(artifact.artifact_id)}
                >
                  {loadingId === artifact.artifact_id ? "Loading..." : "View"}
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
      {openArtifact && (
        <div style={{ marginTop: "var(--space-3)" }}>
          <div className="action-cluster" style={{ marginTop: 0, marginBottom: "var(--space-2)" }}>
            <button type="button" className="btn btn-secondary" onClick={() => setOpenArtifact(null)}>
              Close
            </button>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => {
                if (typeof navigator !== "undefined" && navigator.clipboard) {
                  void navigator.clipboard.writeText(openArtifact.content);
                  setCopied(true);
                  setTimeout(() => setCopied(false), 1500);
                }
              }}
            >
              {copied ? "Copied" : "Copy content"}
            </button>
          </div>
          <pre aria-label="Artifact content" className="pre-scroll">
            {openArtifact.content.length > 50000
              ? `${openArtifact.content.slice(0, 50000)}\n\n--- [Truncated: content exceeds 50KB] ---`
              : openArtifact.content}
          </pre>
        </div>
      )}
    </section>
  );
}
