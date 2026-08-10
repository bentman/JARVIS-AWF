import React from "react";
import { ApprovalsView } from "./ApprovalsView.js";
import { Overview } from "./Overview.js";
import { RunsView } from "./RunsView.js";

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

export interface ImprovementProposalsProps {
  improvements: ImprovementSummary[];
  onArtifactRead?: (artifactId: string) => Promise<ArtifactSummary & { content: string }>;
}

/** Shared between `Dashboard` (the standalone composition `Dashboard.test.tsx`
 * renders) and `App.tsx`'s Proposals view - single source of truth for the
 * "Improvement proposals" section so it isn't duplicated. */
export function ImprovementProposals({ improvements, onArtifactRead }: ImprovementProposalsProps): React.JSX.Element {
  const [openArtifact, setOpenArtifact] = React.useState<{ id: string; content: string } | null>(null);

  const viewArtifact = async (artifactId: string) => {
    if (!onArtifactRead) return;
    const artifact = await onArtifactRead(artifactId);
    setOpenArtifact({ id: artifactId, content: artifact.content });
  };

  return (
    <section aria-label="Improvement proposals" className="card">
      <h2>Improvement proposals</h2>
      {improvements.length === 0 ? (
        <p className="empty">No improvement proposals.</p>
      ) : (
        <ul className="list">
          {improvements.map((proposal) => (
            <li key={proposal.improvement_id}>
              {proposal.summary} - {proposal.status} ({proposal.improvement_id})
              <div>
                Diff: {proposal.diff_digest}
                {onArtifactRead && (
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={() => void viewArtifact(proposal.patch_artifact_id)}
                  >
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
                      className="btn btn-secondary"
                      onClick={() => void viewArtifact(proposal.verdict_artifact_id as string)}
                    >
                      View verdict
                    </button>
                  )}
                </div>
              )}
              {proposal.approval && (
                <div>
                  Approval: {proposal.approval.approval_id} - {proposal.approval.status}
                </div>
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
  return (
    <div role="region" aria-label="Dashboard">
      <h1>Control center</h1>
      <button className="btn btn-secondary" onClick={onRefresh} disabled={refreshing}>
        {refreshing ? "Refreshing..." : "Refresh"}
      </button>
      <Overview controlSummary={controlSummary} onLlmModels={onLlmModels} />
      <RunsView
        runs={runs}
        selectedRunDetail={selectedRunDetail}
        onRunDetail={onRunDetail}
        onArtifactRead={onArtifactRead}
      />
      <ApprovalsView approvals={approvals} />
      <ImprovementProposals improvements={improvements} onArtifactRead={onArtifactRead} />
    </div>
  );
}
