import React from "react";

export interface RegistryObjectSummaryProps {
  detail: Record<string, unknown>;
  onWorkflowRun?: (workflowRef: string) => void;
}

function metadata(detail: Record<string, unknown>): Record<string, unknown> {
  const value = detail.metadata;
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function spec(detail: Record<string, unknown>): Record<string, unknown> {
  const value = detail.spec;
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

export function RegistryObjectSummary({ detail, onWorkflowRun }: RegistryObjectSummaryProps): React.JSX.Element {
  const meta = metadata(detail);
  const body = spec(detail);
  const inputSchema = body.inputSchema;
  const nodes = Array.isArray(body.nodes) ? body.nodes : [];
  const workflowRef = `${String(meta.name ?? detail.name ?? "unknown")}@${String(meta.version ?? detail.version ?? "unknown")}`;

  return (
    <div aria-label="Registry object summary" className="registry-summary">
      <div className="stat-grid">
        <div className="stat-card">
          <div className="stat-label">Kind</div>
          <div className="stat-value">{String(detail.kind ?? "unknown")}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Name</div>
          <div className="stat-value">{String(meta.name ?? detail.name ?? "unknown")}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Version</div>
          <div className="stat-value">{String(meta.version ?? detail.version ?? "unknown")}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Nodes</div>
          <div className="stat-value">{nodes.length}</div>
        </div>
      </div>
      {typeof meta.digest === "string" && (
        <div className="mono row-reason">Digest: {meta.digest}</div>
      )}
      {inputSchema !== undefined && inputSchema !== null && (
        <div>
          <h3>Workflow input schema</h3>
          <pre className="pre-scroll">{JSON.stringify(inputSchema, null, 2)}</pre>
        </div>
      )}
      {detail.kind === "Workflow" && (
        <div className="next-action-box">
          <strong>Run this workflow</strong>
          <div className="inline-actions">
            {onWorkflowRun && (
              <button type="button" className="btn btn-primary" onClick={() => onWorkflowRun(workflowRef)}>
                Run
              </button>
            )}
            <code>awf run {workflowRef}</code>
          </div>
        </div>
      )}
      <details>
        <summary>Advanced/raw registry object</summary>
        <pre aria-label="Registry entry detail" className="pre-scroll">
          {JSON.stringify(detail, null, 2)}
        </pre>
      </details>
    </div>
  );
}
