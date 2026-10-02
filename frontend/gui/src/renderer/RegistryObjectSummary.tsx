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
  const [copiedKey, setCopiedKey] = React.useState<string | null>(null);

  const copyText = (key: string, text: string) => {
    void navigator.clipboard.writeText(text);
    setCopiedKey(key);
    setTimeout(() => setCopiedKey(null), 1500);
  };

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
        <div className="mono row-reason" style={{ display: "flex", alignItems: "center", gap: "var(--space-2)" }}>
          <span>Digest: {meta.digest}</span>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            style={{ fontSize: "11px", padding: "1px 6px" }}
            onClick={() => copyText("digest", meta.digest as string)}
          >
            {copiedKey === "digest" ? "Copied" : "Copy"}
          </button>
        </div>
      )}
      {inputSchema !== undefined && inputSchema !== null && (
        <div style={{ marginTop: "var(--space-3)" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "var(--space-1)" }}>
            <h3 style={{ margin: 0 }}>Workflow input schema</h3>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              style={{ fontSize: "11px", padding: "1px 6px" }}
              onClick={() => copyText("schema", JSON.stringify(inputSchema, null, 2))}
            >
              {copiedKey === "schema" ? "Copied" : "Copy schema"}
            </button>
          </div>
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
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              style={{ fontSize: "11px", padding: "1px 6px" }}
              onClick={() => copyText("cmd", `awf run ${workflowRef}`)}
            >
              {copiedKey === "cmd" ? "Copied" : "Copy command"}
            </button>
          </div>
        </div>
      )}
      <details style={{ marginTop: "var(--space-3)" }}>
        <summary>Advanced/raw registry object</summary>
        <div style={{ marginTop: "var(--space-2)" }}>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            style={{ fontSize: "11px", padding: "1px 6px", marginBottom: "var(--space-1)" }}
            onClick={() => copyText("raw", JSON.stringify(detail, null, 2))}
          >
            {copiedKey === "raw" ? "Copied" : "Copy JSON"}
          </button>
          <pre aria-label="Registry entry detail" className="pre-scroll">
            {JSON.stringify(detail, null, 2)}
          </pre>
        </div>
      </details>
    </div>
  );
}
