import React, { useState } from "react";

export interface RunSummary {
  run_id: string;
  workflow_ref: string;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface ApprovalSummary {
  approval_id: string;
  run_id: string;
  step_id: string;
  action_digest: string;
  status: string;
  reason: string | null;
  requested_at: string;
  decided_at: string | null;
  risk_class: string | null;
  preview?: { machine_action?: Record<string, unknown>; machine_action_digest?: string } | null;
}

export interface ImprovementSummary {
  improvement_id: string;
  run_id: string;
  status: string;
  summary: string;
  diff_digest: string;
  patch_artifact_id: string;
  verdict_artifact_id: string | null;
  merge_commit: string | null;
  approval?: { approval_id: string; status: string } | null;
  changed_paths?: Record<string, unknown>[];
}

export interface ArtifactSummary {
  artifact_id: string;
  run_id: string;
  step_id: string;
  sha256: string;
  relative_path: string;
  media_type: string;
  artifact_type: string;
  complete: number;
  created_at: string;
}

export interface ControlSummary {
  runs: RunSummary[];
  approvals: ApprovalSummary[];
  improvements: ImprovementSummary[];
  recent_verdicts: ArtifactSummary[];
  registry_counts: Record<string, number>;
  llm: {
    servers?: {
      default_server?: string;
      host_profile_id?: string;
      current_selection?: Record<string, unknown> | null;
      error?: string;
    };
    status?: {
      state?: string;
      server_id?: string | null;
      profile_id?: string | null;
      model_path?: string | null;
      reason?: string | null;
      error?: string;
    };
  };
  readiness: {
    profile_id: string | null;
    inventory: Record<string, unknown> | null;
    tokens: string[];
    readiness: Record<string, { device: string; ready: boolean; reason: string }>;
    error?: string;
  };
}

export interface LlmModelsReport {
  local_models?: Record<string, unknown>[];
  ollama_models?: Record<string, unknown>[];
  ollama_models_error?: string;
  error?: string;
}

export interface ControlRunDetail {
  run: {
    run_id: string;
    workflow_ref: string;
    status: string;
    steps: { step_id: string; node_id: string; status: string; attempt: number }[];
  };
  artifacts: ArtifactSummary[];
  timeline: Record<string, unknown>;
  improvements: ImprovementSummary[];
  verdicts: ArtifactSummary[];
}

export interface DashboardProps {
  runs: RunSummary[];
  approvals: ApprovalSummary[];
  improvements?: ImprovementSummary[];
  controlSummary?: ControlSummary;
  selectedRunDetail?: ControlRunDetail | null;
  onRefresh: () => void;
  onRunDetail?: (runId: string) => void;
  onArtifactRead?: (artifactId: string) => Promise<ArtifactSummary & { content: string }>;
  onLlmModels?: () => Promise<LlmModelsReport>;
  refreshing: boolean;
}

/** `awf/run.list` and `awf/approval.list` were already real, working IPC
 * channels - `registerIpcHandlers` called the same `ProtocolClient` the CLI
 * uses - but nothing in the renderer ever called them. This is that
 * caller: real run/approval state, not dead plumbing. */
export function Dashboard({
  runs,
  approvals,
  improvements = [],
  controlSummary,
  selectedRunDetail,
  onRefresh,
  onRunDetail,
  onArtifactRead,
  onLlmModels,
  refreshing,
}: DashboardProps): React.JSX.Element {
  const registryCounts = controlSummary?.registry_counts ?? {};
  const readiness = controlSummary?.readiness;
  const llmStatus = controlSummary?.llm.status;
  const llmServers = controlSummary?.llm.servers;
  const [openArtifact, setOpenArtifact] = useState<{ id: string; content: string } | null>(null);
  const [models, setModels] = useState<LlmModelsReport | null>(null);

  const viewArtifact = async (artifactId: string) => {
    if (!onArtifactRead) return;
    const artifact = await onArtifactRead(artifactId);
    setOpenArtifact({ id: artifactId, content: artifact.content });
  };

  const loadModels = async () => {
    if (!onLlmModels) return;
    setModels(await onLlmModels());
  };

  return (
    <div role="region" aria-label="Dashboard">
      <h1>Control center</h1>
      <button onClick={onRefresh} disabled={refreshing}>
        {refreshing ? "Refreshing..." : "Refresh"}
      </button>
      <section aria-label="System readiness">
        <h2>System readiness</h2>
        {readiness ? (
          <>
            <div>Profile: {readiness.profile_id ?? "unknown"}</div>
            {readiness.error && <div>Readiness error: {readiness.error}</div>}
            <ul>
              {Object.entries(readiness.readiness).map(([name, result]) => (
                <li key={name}>
                  {name}: {result.device} - {result.ready ? "ready" : "not ready"} ({result.reason})
                </li>
              ))}
            </ul>
            {readiness.tokens.length > 0 && <div>Tokens: {readiness.tokens.join(", ")}</div>}
            {readiness.inventory && <pre>{JSON.stringify(readiness.inventory, null, 2)}</pre>}
          </>
        ) : (
          <p>No readiness data.</p>
        )}
      </section>
      <section aria-label="LLM status">
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
          <p>No LLM status.</p>
        )}
        {onLlmModels && (
          <div>
            <button type="button" onClick={() => void loadModels()}>
              Load models
            </button>
            {models && (
              <>
                {models.local_models && models.local_models.length > 0 && (
                  <div>
                    <h3>Local models</h3>
                    <ul>
                      {models.local_models.map((model, index) => (
                        <li key={index}>{JSON.stringify(model)}</li>
                      ))}
                    </ul>
                  </div>
                )}
                {models.ollama_models && models.ollama_models.length > 0 && (
                  <div>
                    <h3>Ollama models</h3>
                    <ul>
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
      <section aria-label="Registry">
        <h2>Registry</h2>
        {Object.keys(registryCounts).length === 0 ? (
          <p>No registry counts.</p>
        ) : (
          <ul>
            {Object.entries(registryCounts).map(([kind, count]) => (
              <li key={kind}>
                {kind}: {count}
              </li>
            ))}
          </ul>
        )}
      </section>
      <section aria-label="Runs">
        <h2>Runs</h2>
        {runs.length === 0 ? (
          <p>No runs yet.</p>
        ) : (
          <ul>
            {runs.map((run) => (
              <li key={run.run_id}>
                {run.workflow_ref} - {run.status} ({run.run_id})
                {onRunDetail && <button onClick={() => onRunDetail(run.run_id)}>View details</button>}
              </li>
            ))}
          </ul>
        )}
      </section>
      <section aria-label="Selected run detail">
        <h2>Selected run detail</h2>
        {selectedRunDetail ? (
          <>
            <div>
              {selectedRunDetail.run.workflow_ref} - {selectedRunDetail.run.status}
            </div>
            <ul>
              {selectedRunDetail.run.steps.map((step) => (
                <li key={step.step_id}>
                  {step.node_id}: {step.status} (attempt {step.attempt})
                </li>
              ))}
            </ul>
            {selectedRunDetail.artifacts.length > 0 && (
              <div>
                <h3>Artifacts</h3>
                <ul>
                  {selectedRunDetail.artifacts.map((artifact) => (
                    <li key={artifact.artifact_id}>
                      {artifact.relative_path} ({artifact.artifact_type})
                      {onArtifactRead && (
                        <button type="button" onClick={() => void viewArtifact(artifact.artifact_id)}>
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
                <ul>
                  {selectedRunDetail.verdicts.map((verdict) => (
                    <li key={verdict.artifact_id}>
                      {verdict.relative_path} ({verdict.artifact_type})
                      {onArtifactRead && (
                        <button type="button" onClick={() => void viewArtifact(verdict.artifact_id)}>
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
                <pre>{JSON.stringify(selectedRunDetail.timeline, null, 2)}</pre>
              </div>
            )}
            {openArtifact && (
              <div>
                <button type="button" onClick={() => setOpenArtifact(null)}>
                  Close
                </button>
                <pre aria-label="Artifact content">{openArtifact.content}</pre>
              </div>
            )}
          </>
        ) : (
          <p>No run selected.</p>
        )}
      </section>
      <section aria-label="Pending approvals">
        <h2>Pending approvals</h2>
        {approvals.length === 0 ? (
          <p>No pending approvals.</p>
        ) : (
          <ul>
            {approvals.map((approval) => (
              <li key={approval.approval_id}>
                {approval.action_digest} - {approval.risk_class ?? "unknown risk class"} ({approval.approval_id})
                {approval.preview?.machine_action && (
                  <pre>{JSON.stringify(approval.preview.machine_action, null, 2)}</pre>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>
      <section aria-label="Improvement proposals">
        <h2>Improvement proposals</h2>
        {improvements.length === 0 ? (
          <p>No improvement proposals.</p>
        ) : (
          <ul>
            {improvements.map((proposal) => (
              <li key={proposal.improvement_id}>
                {proposal.summary} - {proposal.status} ({proposal.improvement_id})
                <div>
                  Diff: {proposal.diff_digest}
                  {onArtifactRead && (
                    <button type="button" onClick={() => void viewArtifact(proposal.patch_artifact_id)}>
                      View diff
                    </button>
                  )}
                </div>
                {proposal.verdict_artifact_id && (
                  <div>
                    Verdict: {proposal.verdict_artifact_id}
                    {onArtifactRead && (
                      <button
                        type="button"
                        onClick={() => void viewArtifact(proposal.verdict_artifact_id as string)}
                      >
                        View verdict
                      </button>
                    )}
                  </div>
                )}
                {proposal.approval && <div>Approval: {proposal.approval.approval_id} - {proposal.approval.status}</div>}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
