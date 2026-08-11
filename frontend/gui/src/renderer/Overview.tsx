import React, { useState } from "react";
import type { ArtifactSummary, ControlSummary, LlmModelsReport } from "./Dashboard.js";

export interface OverviewProps {
  controlSummary?: ControlSummary;
  onLlmModels?: () => Promise<LlmModelsReport>;
}

export function Overview({ controlSummary, onLlmModels }: OverviewProps): React.JSX.Element {
  const registryCounts = controlSummary?.registry_counts ?? {};
  const readiness = controlSummary?.readiness;
  const doctor = controlSummary?.doctor;
  const llmStatus = controlSummary?.llm.status;
  const llmServers = controlSummary?.llm.servers;
  const recentVerdicts: ArtifactSummary[] = controlSummary?.recent_verdicts ?? [];
  const [models, setModels] = useState<LlmModelsReport | null>(null);

  const loadModels = async () => {
    if (!onLlmModels) return;
    setModels(await onLlmModels());
  };

  return (
    <>
      <section aria-label="Operator readiness" className="card">
        <h2>Operator readiness</h2>
        {doctor ? (
          <>
            <div>
              Status: <span className={`chip state-${doctor.status === "ok" ? "ok" : doctor.status === "warn" ? "warn" : "danger"}`}>{doctor.status}</span>
            </div>
            <ul className="list">
              {doctor.checks.map((check) => (
                <li key={check.name}>
                  <span className={`dot ${check.status === "ok" ? "state-ok" : check.status === "warn" ? "state-warn" : "state-danger"}`} />
                  {check.name}: {check.summary}
                  {check.next_action && <div className="row-reason">Next: {check.next_action}</div>}
                </li>
              ))}
            </ul>
            <div className="mono">{doctor.first_run_command}</div>
          </>
        ) : (
          <p className="empty">No operator readiness data.</p>
        )}
      </section>
      <section aria-label="System readiness" className="card">
        <h2>System readiness</h2>
        {readiness ? (
          <>
            <div>Profile: {readiness.profile_id ?? "unknown"}</div>
            {readiness.error && <div>Readiness error: {readiness.error}</div>}
            <div className="stat-grid">
              {Object.entries(readiness.readiness).map(([name, result]) => (
                <div key={name} className="stat-card">
                  <div className="stat-label">
                    <span className={`dot ${result.ready ? "state-ok" : "state-danger"}`} />
                    {name}
                  </div>
                  <div className="stat-value">{result.device}</div>
                  <div className="stat-sub">
                    {result.ready ? "ready" : "not ready"}
                    {result.reason ? ` — ${result.reason}` : ""}
                  </div>
                </div>
              ))}
            </div>
            {readiness.tokens.length > 0 && <div>Tokens: {readiness.tokens.join(", ")}</div>}
            {readiness.inventory && <pre className="pre-scroll">{JSON.stringify(readiness.inventory, null, 2)}</pre>}
          </>
        ) : (
          <p className="empty">No readiness data.</p>
        )}
      </section>
      <section aria-label="LLM status" className="card">
        <h2>LLM status</h2>
        {llmStatus ? (
          <>
            <div>State: {llmStatus.state ?? "unknown"}</div>
            {llmStatus.server_id && <div>Server: {llmStatus.server_id}</div>}
            {llmStatus.profile_id && <div>Runtime profile: {llmStatus.profile_id}</div>}
            {llmStatus.error && <div>LLM error: {llmStatus.error}</div>}
            {llmServers?.default_server && <div>Default server: {llmServers.default_server}</div>}
            {llmServers?.current_selection && (
              <div>Current selection: {JSON.stringify(llmServers.current_selection)}</div>
            )}
          </>
        ) : (
          <p className="empty">No LLM status.</p>
        )}
        {onLlmModels && (
          <div>
            <button type="button" className="btn btn-secondary" onClick={() => void loadModels()}>
              Load models
            </button>
            {models && (
              <>
                {models.local_models && models.local_models.length > 0 && (
                  <div>
                    <h3>Local models</h3>
                    <ul className="list">
                      {models.local_models.map((model, index) => (
                        <li key={index}>{JSON.stringify(model)}</li>
                      ))}
                    </ul>
                  </div>
                )}
                {models.ollama_models && models.ollama_models.length > 0 && (
                  <div>
                    <h3>Ollama models</h3>
                    <ul className="list">
                      {models.ollama_models.map((model, index) => (
                        <li key={index}>{JSON.stringify(model)}</li>
                      ))}
                    </ul>
                  </div>
                )}
                {models.error && <div>Models error: {models.error}</div>}
              </>
            )}
          </div>
        )}
      </section>
      <section aria-label="Registry" className="card">
        <h2>Registry</h2>
        {Object.keys(registryCounts).length === 0 ? (
          <p className="empty">No registry counts.</p>
        ) : (
          <ul className="list">
            {Object.entries(registryCounts).map(([kind, count]) => (
              <li key={kind}>
                {kind}: {count}
              </li>
            ))}
          </ul>
        )}
      </section>
      <section aria-label="Recent verdicts" className="card">
        <h2>Recent verdicts</h2>
        {recentVerdicts.length === 0 ? (
          <p className="empty">No recent verdicts.</p>
        ) : (
          <ul className="list">
            {recentVerdicts.map((verdict) => (
              <li key={verdict.artifact_id}>
                {verdict.relative_path} ({verdict.artifact_type})
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  );
}
