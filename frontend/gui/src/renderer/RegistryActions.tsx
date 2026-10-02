import React, { useState } from "react";
import { RegistryObjectSummary } from "./RegistryObjectSummary.js";
import { stateClass } from "./state.js";

export interface RegistryEntry {
  source: "config" | "data";
  kind: string;
  name: string;
  version: string;
  trust_status?: string | null;
  digest?: string | null;
}

export interface RegistryActionsProps {
  onRegistryValidate: (path: string, kind?: string) => Promise<unknown>;
  onRegistryPublish: (path: string, kind: string) => Promise<unknown>;
  onRegistryReindex: () => Promise<unknown>;
  onRegistryRetire: (kind: string, name: string, version: string) => Promise<unknown>;
  onRegistryTrust: (kind: string, name: string, version: string, status: string) => Promise<unknown>;
  onRegistryList?: (kind: string) => Promise<RegistryEntry[]>;
  onRegistryGet?: (kind: string, name: string, version: string) => Promise<Record<string, unknown>>;
  onWorkflowRun?: (workflowRef: string) => void;
}

function asText(value: unknown): string {
  return JSON.stringify(value, null, 2);
}

export function RegistryActions({
  onRegistryValidate,
  onRegistryPublish,
  onRegistryReindex,
  onRegistryRetire,
  onRegistryTrust,
  onRegistryList,
  onRegistryGet,
  onWorkflowRun,
}: RegistryActionsProps): React.JSX.Element {
  const [path, setPath] = useState("");
  const [kind, setKind] = useState("workflows");
  const [name, setName] = useState("");
  const [version, setVersion] = useState("1.0.0");
  const [trustStatus, setTrustStatus] = useState("trusted");
  const [result, setResult] = useState<string>("");
  const [error, setError] = useState<string>("");
  const [entries, setEntries] = useState<RegistryEntry[]>([]);
  const [selectedDetail, setSelectedDetail] = useState<Record<string, unknown> | null>(null);
  const [listError, setListError] = useState<string>("");
  const [filterQuery, setFilterQuery] = useState("");
  const [busy, setBusy] = useState(false);

  const filteredEntries = entries.filter((entry) => {
    if (!filterQuery.trim()) return true;
    const q = filterQuery.toLowerCase();
    return (
      entry.name.toLowerCase().includes(q) ||
      entry.kind.toLowerCase().includes(q) ||
      entry.version.toLowerCase().includes(q) ||
      (entry.trust_status ?? "").toLowerCase().includes(q)
    );
  });

  const runAction = async (action: () => Promise<unknown>) => {
    setError("");
    setResult("");
    setBusy(true);
    try {
      setResult(asText(await action()));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  };

  const listEntries = async () => {
    if (!onRegistryList) return;
    setListError("");
    setSelectedDetail(null);
    try {
      setEntries(await onRegistryList(kind));
    } catch (caught) {
      setListError(caught instanceof Error ? caught.message : String(caught));
    }
  };

  const viewEntry = async (entry: RegistryEntry) => {
    if (!onRegistryGet) return;
    setListError("");
    try {
      setSelectedDetail(await onRegistryGet(entry.kind, entry.name, entry.version));
    } catch (caught) {
      setListError(caught instanceof Error ? caught.message : String(caught));
    }
  };

  const useEntry = (entry: RegistryEntry) => {
    setName(entry.name);
    setVersion(entry.version);
  };

  React.useEffect(() => {
    if (onRegistryList) void listEntries();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kind, onRegistryList]);

  return (
    <section aria-label="Registry actions" className="card">
      <div className="section-heading">
        <div>
          <h2>Registry actions</h2>
          <p className="muted">Validate, publish, reindex, retire, and set trust status for registry artifacts.</p>
        </div>
        <span className="chip state-ok">{kind}</span>
      </div>

      <div className="form-group">
        <label className="field-label" htmlFor="registry-draft-path">
          Draft path
        </label>
        <input
          id="registry-draft-path"
          aria-label="Registry draft path"
          className="mono"
          value={path}
          onChange={(event) => setPath(event.currentTarget.value)}
          placeholder="data/proposals/example.yaml"
        />
      </div>
      <div className="form-group">
        <label className="field-label" htmlFor="registry-kind-select">
          Kind
        </label>
        <select
          id="registry-kind-select"
          aria-label="Registry kind"
          value={kind}
          onChange={(event) => setKind(event.currentTarget.value)}
        >
          <option value="workflows">workflows</option>
          <option value="capabilities">capabilities</option>
          <option value="agents">agents</option>
          <option value="skills">skills</option>
          <option value="mcp">mcp</option>
          <option value="model-profiles">model-profiles</option>
          <option value="voice-profiles">voice-profiles</option>
          <option value="semantic-memories">semantic-memories</option>
        </select>
      </div>
      {onRegistryList && (
        <div aria-label="Registry browser" style={{ marginBottom: "var(--space-4)" }}>
          <div className="action-cluster" style={{ marginTop: 0, marginBottom: "var(--space-2)" }}>
            <button type="button" className="btn btn-secondary" onClick={() => void listEntries()}>
              List
            </button>
            {entries.length > 0 && (
              <input
                aria-label="Filter registry entries"
                className="mono"
                value={filterQuery}
                onChange={(event) => setFilterQuery(event.currentTarget.value)}
                placeholder="Filter entries..."
                style={{ maxWidth: "200px", padding: "var(--space-1) var(--space-2)", fontSize: "var(--text-xs)" }}
              />
            )}
          </div>
          {listError && <p role="alert">{listError}</p>}
          {entries.length > 0 && filteredEntries.length === 0 && (
            <p className="empty">No entries match &quot;{filterQuery}&quot;.</p>
          )}
          {filteredEntries.length > 0 && (
            <ul className="list">
              {filteredEntries.map((entry) => (
                <li key={`${entry.kind}/${entry.name}@${entry.version}`} className="row">
                  <span className="mono">
                    {entry.kind}/{entry.name}@{entry.version}
                  </span>
                  <span className={`chip ${stateClass(entry.source)}`}>{entry.source}</span>
                  {entry.trust_status && (
                    <span className={`chip ${stateClass(entry.trust_status)}`}>{entry.trust_status}</span>
                  )}
                  {entry.digest && <span className="mono row-reason">{entry.digest.slice(0, 18)}</span>}
                  {onRegistryGet && (
                    <button type="button" className="btn btn-secondary" onClick={() => void viewEntry(entry)}>
                      View
                    </button>
                  )}
                  <button type="button" className="btn btn-secondary" onClick={() => useEntry(entry)}>
                    Use
                  </button>
                  {entry.kind === "workflows" && onWorkflowRun && (
                    <button type="button" className="btn btn-primary" onClick={() => onWorkflowRun(`${entry.name}@${entry.version}`)}>
                      Run
                    </button>
                  )}
                </li>
              ))}
            </ul>
          )}
          {selectedDetail && <RegistryObjectSummary detail={selectedDetail} onWorkflowRun={onWorkflowRun} />}
        </div>
      )}
      <div className="section-heading" style={{ marginTop: "var(--space-4)" }}>
        <div>
          <h3>Entity management</h3>
          <p className="muted">Inspect, retire, or set trust status for a specific entity.</p>
        </div>
      </div>
      <div className="form-group">
        <label className="field-label" htmlFor="registry-name">
          Name
        </label>
        <input
          id="registry-name"
          aria-label="Registry name"
          className="mono"
          value={name}
          onChange={(event) => setName(event.currentTarget.value)}
        />
      </div>
      <div className="form-group">
        <label className="field-label" htmlFor="registry-version">
          Version
        </label>
        <input
          id="registry-version"
          aria-label="Registry version"
          className="mono"
          value={version}
          onChange={(event) => setVersion(event.currentTarget.value)}
        />
      </div>
      <div className="form-group">
        <label className="field-label" htmlFor="registry-trust-status">
          Trust status
        </label>
        <input
          id="registry-trust-status"
          aria-label="Registry trust status"
          value={trustStatus}
          onChange={(event) => setTrustStatus(event.currentTarget.value)}
        />
      </div>
      <div className="action-cluster">
        <button
          type="button"
          className="btn btn-primary"
          disabled={busy}
          onClick={() => void runAction(() => onRegistryValidate(path, kind || undefined))}
        >
          Validate
        </button>
        <button
          type="button"
          className="btn btn-primary"
          disabled={busy}
          onClick={() => void runAction(() => onRegistryPublish(path, kind))}
        >
          Publish
        </button>
        <button
          type="button"
          className="btn btn-primary"
          disabled={busy}
          onClick={() => void runAction(() => onRegistryReindex())}
        >
          Reindex
        </button>
        <button
          type="button"
          className="btn btn-danger"
          disabled={busy}
          onClick={() => void runAction(() => onRegistryRetire(kind, name, version))}
        >
          Retire
        </button>
        <button
          type="button"
          className="btn btn-secondary"
          disabled={busy}
          onClick={() => void runAction(() => onRegistryTrust(kind, name, version, trustStatus))}
        >
          Set trust
        </button>
      </div>
      {error && (
        <div style={{ display: "flex", alignItems: "center", gap: "var(--space-2)", marginTop: "var(--space-2)" }}>
          <p role="alert" style={{ margin: 0 }}>{error}</p>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            style={{ fontSize: "11px", padding: "1px 6px" }}
            onClick={() => setError("")}
            title="Dismiss error"
          >
            Dismiss
          </button>
        </div>
      )}
      {result && (
        <pre aria-label="Registry action result" className="pre-scroll" style={{ marginTop: "var(--space-3)" }}>
          {result}
        </pre>
      )}
    </section>
  );
}
