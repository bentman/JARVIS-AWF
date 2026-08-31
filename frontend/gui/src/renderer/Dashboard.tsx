import React from "react";
import { ApprovalsView } from "./ApprovalsView.js";
import { OperatorWorkQueue } from "./OperatorWorkQueue.js";
import { Overview } from "./Overview.js";
import { RunsView } from "./RunsView.js";

export interface RunSummary {
  run_id: string;
  workflow_ref: string;
  status: string;
  created_at: string;
  updated_at: string;
  outcome?: RunOutcome;
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
  preview?: {
    machine_action?: Record<string, unknown>;
    machine_action_digest?: string;
    kind?: string;
    improvement_id?: string;
    human_summary?: string;
    scope_classification?: "localized" | "broad";
    safety_assessment?: string;
    proposal_review?: Record<string, unknown>;
    diff_stats?: FileDiffPreview[];
    verdict_artifact_id?: string | null;
    proposal?: ImprovementSummary;
  } | null;
}

export interface FileDiffPreview {
  path: string;
  additions: number;
  deletions: number;
  is_binary: boolean;
  preview_lines: string[];
  truncated: boolean;
  total_lines: number;
}

export interface NextActionInfo {
  action: string;
  label: string;
  command: string;
  description?: string;
}

export interface ImprovementSummary {
  improvement_id: string;
  run_id: string;
  target_branch?: string;
  status: string;
  summary: string;
  human_summary?: string;
  scope_classification?: "localized" | "broad";
  safety_assessment?: string;
  proposal_review?: Record<string, unknown>;
  diff_stats?: FileDiffPreview[];
  next_action?: NextActionInfo;
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

export interface OperatorWorkItem {
  item_id: string;
  kind: string;
  title: string;
  status: string;
  priority: number;
  description: string;
  command: string;
  source: string;
  run_id?: string | null;
  step_id?: string | null;
  approval_id?: string | null;
  improvement_id?: string | null;
  artifact_id?: string | null;
  created_at?: string | null;
  primary_action?: OperatorAction;
  secondary_actions?: OperatorAction[];
}

export interface OperatorAction {
  kind: string;
  label: string;
  command: string;
  description?: string | null;
  run_id?: string | null;
  approval_id?: string | null;
  improvement_id?: string | null;
  artifact_id?: string | null;
  workflow_ref?: string | null;
  registry_kind?: string | null;
  registry_name?: string | null;
  registry_version?: string | null;
}

export interface OperatorInputField {
  name: string;
  type: string;
  required: boolean;
  enum?: unknown[] | null;
  description?: string | null;
  default?: unknown;
}

export interface OperatorInputSchemaSummary {
  type: string;
  required: string[];
  fields: OperatorInputField[];
}

export interface OperatorStartOption {
  workflow_ref: string;
  name: string;
  version: string;
  source?: string | null;
  trust_status?: string | null;
  digest?: string | null;
  status: string;
  description: string;
  input_schema: Record<string, unknown>;
  input_schema_summary: OperatorInputSchemaSummary;
  primary_action: OperatorAction;
}

export interface OperatorNextAction {
  label: string;
  command: string;
  description: string;
  kind: string;
  run_id?: string | null;
  approval_id?: string | null;
  improvement_id?: string | null;
  primary_action?: OperatorAction;
}

export interface OperatorTimelineItem {
  kind: string;
  status: string;
  title: string;
  description: string;
  occurred_at: string | null;
  step_id?: string | null;
  event_id?: string;
  approval_id?: string;
  artifact_id?: string;
  node_id?: string;
  failure_class?: string | null;
  action_digest?: string;
  payload?: Record<string, unknown>;
}

export interface RunOutcome {
  run_id: string;
  workflow_ref: string;
  status: string;
  response_text: string;
  evidence: { artifact_id?: string; type?: string; path?: string }[];
  artifacts: { artifact_id?: string; type?: string; path?: string; complete?: boolean }[];
  failures: { step_id?: string; node_id?: string; failure_class?: string | null; output?: unknown }[];
  pending_approvals: { approval_id?: string; risk_class?: string | null; action_digest?: string }[];
  created_at?: string;
  updated_at?: string;
  next_action: string;
}

export interface DoctorCheck {
  name: string;
  status: "ok" | "warn" | "error";
  summary: string;
  detail: Record<string, unknown>;
  next_action?: string | null;
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
  doctor?: {
    status: "ok" | "warn" | "error";
    checks: DoctorCheck[];
    next_actions: string[];
    first_run_command: string;
  };
  operator_work_items?: OperatorWorkItem[];
  operator_next_actions?: OperatorNextAction[];
  operator_start_options?: OperatorStartOption[];
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
  outcome?: RunOutcome;
  artifacts: ArtifactSummary[];
  timeline: Record<string, unknown>;
  operator_timeline?: OperatorTimelineItem[];
  operator_work_items?: OperatorWorkItem[];
  operator_next_actions?: OperatorNextAction[];
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
  onApprove?: (approvalId: string) => Promise<void>;
  onReject?: (approvalId: string, reason: string) => Promise<void>;
  onImprovementRequestMerge?: (improvementId: string) => Promise<unknown>;
  onImprovementMerge?: (improvementId: string, approvalId: string) => Promise<unknown>;
  onImprovementReject?: (improvementId: string, reason?: string) => Promise<unknown>;
  refreshing: boolean;
}

export interface ImprovementProposalsProps {
  improvements: ImprovementSummary[];
  onArtifactRead?: (artifactId: string) => Promise<ArtifactSummary & { content: string }>;
  onRequestMerge?: (improvementId: string) => Promise<unknown>;
  onMerge?: (improvementId: string, approvalId: string) => Promise<unknown>;
  onReject?: (improvementId: string, reason?: string) => Promise<unknown>;
}

/** Shared between `Dashboard` (the standalone composition `Dashboard.test.tsx`
 * renders) and `App.tsx`'s Proposals view - single source of truth for the
 * "Improvement proposals" section so it isn't duplicated. */
export function ImprovementProposals({
  improvements,
  onArtifactRead,
  onRequestMerge,
  onMerge,
  onReject,
}: ImprovementProposalsProps): React.JSX.Element {
  const [openArtifact, setOpenArtifact] = React.useState<{ id: string; content: string } | null>(null);
  const [expandedDiffs, setExpandedDiffs] = React.useState<Record<string, boolean>>({});

  const viewArtifact = async (artifactId: string) => {
    if (!onArtifactRead) return;
    const artifact = await onArtifactRead(artifactId);
    setOpenArtifact({ id: artifactId, content: artifact.content });
  };

  const toggleDiff = (id: string) => {
    setExpandedDiffs((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  return (
    <section aria-label="Improvement proposals" className="card">
      <h2>Improvement proposals</h2>
      {improvements.length === 0 ? (
        <p className="empty">No improvement proposals.</p>
      ) : (
        <ul className="list">
          {improvements.map((proposal) => {
            const humanText = proposal.human_summary || proposal.summary;
            const scope = proposal.scope_classification || "localized";
            const diffStats = proposal.diff_stats || [];
            const isDiffCollapsed = expandedDiffs[proposal.improvement_id] === false;

            return (
              <li key={proposal.improvement_id} className="proposal-item" style={{ padding: "1rem", marginBottom: "1rem", border: "1px solid var(--border-color, rgba(255,255,255,0.1))", borderRadius: "6px" }}>
                <div className="proposal-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid var(--border-color, rgba(255,255,255,0.1))", paddingBottom: "0.5rem" }}>
                  <div>
                    <span className="badge badge-status" style={{ marginRight: "0.5rem" }}>
                      {proposal.status.toUpperCase()} [{scope.toUpperCase()}]
                    </span>
                    <strong style={{ fontSize: "1.1em" }}>Proposal {proposal.improvement_id}</strong>
                  </div>
                  <div className="muted mono" style={{ fontSize: "0.75em" }}>
                    → {proposal.target_branch || "main"}
                  </div>
                </div>

                <div className="proposal-narrative" style={{ marginTop: "1rem" }}>
                  <div style={{ fontSize: "0.85em", fontWeight: 600, color: "var(--text-muted, #8b949e)", textTransform: "uppercase", letterSpacing: "0.5px" }}>1. What Changed</div>
                  <div style={{ marginTop: "0.4rem", fontSize: "1em", fontWeight: 500, lineHeight: 1.5, color: "var(--text-main, #c9d1d9)" }}>
                    {humanText}
                  </div>
                </div>

                {diffStats.length > 0 && (
                  <div style={{ marginTop: "0.75rem" }}>
                    <div style={{ fontSize: "0.85em", fontWeight: 600, color: "var(--text-muted, #8b949e)", textTransform: "uppercase", letterSpacing: "0.5px" }}>2. Where It Changed</div>
                    <ul style={{ margin: "0.4rem 0 0", paddingLeft: "1.2rem" }}>
                      {diffStats.map((f) => (
                        <li key={f.path} style={{ fontFamily: "monospace", fontSize: "0.8em", color: "var(--text-secondary, #8b949e)" }}>
                          {f.path} <span style={{ color: "#2ea043" }}>+{f.additions}</span> / <span style={{ color: "#da3633" }}>-{f.deletions}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                <div style={{ marginTop: "0.75rem" }}>
                  <div style={{ fontSize: "0.85em", fontWeight: 600, color: "var(--text-muted, #8b949e)", textTransform: "uppercase", letterSpacing: "0.5px" }}>3. Validation Status</div>
                  {proposal.verdict_artifact_id ? (
                    <div style={{ marginTop: "0.4rem", fontSize: "0.85em" }}>
                      <span className="badge badge-success" style={{ marginRight: "0.5rem" }}>✓ PASSED</span>
                      <span style={{ color: "var(--text-secondary, #8b949e)" }}>All automated gate checks passed</span>
                    </div>
                  ) : (
                    <div style={{ marginTop: "0.4rem", fontSize: "0.85em" }}>
                      <span className="badge badge-warning" style={{ marginRight: "0.5rem" }}>PENDING</span>
                      <span style={{ color: "var(--text-secondary, #8b949e)" }}>Awaiting verification verdict</span>
                    </div>
                  )}
                </div>

                <div style={{ marginTop: "0.75rem" }}>
                  <div style={{ fontSize: "0.85em", fontWeight: 600, color: "var(--text-muted, #8b949e)", textTransform: "uppercase", letterSpacing: "0.5px" }}>4. Why It's Safe To Consider</div>
                  {proposal.safety_assessment && (
                    <div style={{ marginTop: "0.4rem", padding: "0.5rem", background: "var(--bg-subtle, rgba(255,255,255,0.03))", borderLeft: "3px solid var(--accent, #58a6ff)", borderRadius: "2px", fontSize: "0.85em", lineHeight: 1.5, color: "var(--text-secondary, #8b949e)" }}>
                      {proposal.safety_assessment}
                    </div>
                  )}
                </div>

                {diffStats.length > 0 && (
                  <div className="proposal-files" style={{ marginTop: "1rem" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <div style={{ fontSize: "0.85em", fontWeight: 600, color: "var(--text-muted, #8b949e)", textTransform: "uppercase", letterSpacing: "0.5px" }}>Diff Preview</div>
                      <button
                        type="button"
                        className="btn btn-secondary btn-sm"
                        style={{ fontSize: "0.75em", padding: "0.15rem 0.4rem" }}
                        onClick={() => toggleDiff(proposal.improvement_id)}
                      >
                        {isDiffCollapsed ? "Show" : "Hide"}
                      </button>
                    </div>

                    {!isDiffCollapsed && (
                      <div className="diff-preview-box" style={{ marginTop: "0.5rem", background: "var(--bg-subtle, #161b22)", padding: "0.5rem", borderRadius: "4px" }}>
                        {diffStats.map((f) => (
                          <div key={f.path} style={{ marginBottom: "0.5rem" }}>
                            <strong style={{ fontSize: "0.8em", color: "var(--text-muted, #8b949e)" }}>{f.path}</strong>
                            <pre aria-label="Diff preview" className="pre-scroll" style={{ fontSize: "0.8em", margin: "0.25rem 0", background: "rgba(0,0,0,0.2)" }}>
                              {f.preview_lines && f.preview_lines.length > 0
                                ? f.preview_lines.join("\n")
                                : "(binary or unchanged)"}
                            </pre>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}

                {proposal.next_action && (
                  <div style={{
                    marginTop: "1rem",
                    padding: "0.75rem",
                    background: "var(--bg-action, rgba(88, 166, 255, 0.08))",
                    border: "1px solid var(--accent, #58a6ff)",
                    borderRadius: "6px",
                    fontSize: "0.9em"
                  }}>
                    <div style={{ fontWeight: 600, color: "var(--accent, #58a6ff)", marginBottom: "0.5rem" }}>
                      ▶ NEXT ACTION: {proposal.next_action.label}
                    </div>
                    {proposal.next_action.description && (
                      <div style={{ marginBottom: "0.5rem", color: "var(--text-main, #c9d1d9)", fontSize: "0.95em", lineHeight: 1.4 }}>
                        {proposal.next_action.description}
                      </div>
                    )}
                    {proposal.next_action.command && (
                      <div style={{ backgroundColor: "rgba(0, 0, 0, 0.3)", padding: "0.4rem", borderRadius: "3px", fontFamily: "monospace", fontSize: "0.85em" }}>
                        <code>{proposal.next_action.command}</code>
                      </div>
                    )}
                  </div>
                )}

                <div className="proposal-details" style={{ marginTop: "0.5rem", fontSize: "0.8em" }}>
                  <div className="muted">
                    <span>Digest: <code>{proposal.diff_digest}</code></span>
                    {onArtifactRead && (
                      <button
                        type="button"
                        className="btn btn-secondary btn-sm"
                        style={{ marginLeft: "0.5rem", fontSize: "0.75em", padding: "0.15rem 0.4rem" }}
                        onClick={() => void viewArtifact(proposal.patch_artifact_id)}
                      >
                        View raw patch artifact
                      </button>
                    )}
                  </div>

                  {proposal.approval && (
                    <div style={{ marginTop: "0.25rem" }}>
                      <span className="muted">Approval:</span> <code>{proposal.approval.approval_id}</code> ({proposal.approval.status})
                    </div>
                  )}
                </div>

                <div className="proposal-actions" style={{ marginTop: "0.75rem", display: "flex", gap: "0.5rem" }}>
                  {proposal.status === "ready_for_review" && onRequestMerge && (
                    <button
                      type="button"
                      className="btn btn-primary"
                      onClick={() => void onRequestMerge(proposal.improvement_id)}
                    >
                      Request merge approval
                    </button>
                  )}
                  {proposal.approval?.status === "approved" && onMerge && (
                    <button
                      type="button"
                      className="btn btn-primary"
                      onClick={() => void onMerge(proposal.improvement_id, proposal.approval!.approval_id)}
                    >
                      Merge improvement
                    </button>
                  )}
                  {proposal.status !== "merged" && proposal.status !== "rejected" && onReject && (
                    <button
                      type="button"
                      className="btn btn-danger"
                      onClick={() => void onReject(proposal.improvement_id, "Rejected by operator")}
                    >
                      Reject proposal
                    </button>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      )}
      {openArtifact && (
        <div style={{ marginTop: "1rem" }}>
          <button type="button" className="btn btn-secondary" onClick={() => setOpenArtifact(null)}>
            Close artifact
          </button>
          <pre aria-label="Artifact content" className="pre-scroll" style={{ marginTop: "0.5rem" }}>
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
  onApprove,
  onReject,
  onImprovementRequestMerge,
  onImprovementMerge,
  onImprovementReject,
  refreshing,
}: DashboardProps): React.JSX.Element {
  return (
    <div role="region" aria-label="Dashboard">
      <h1>Control center</h1>
      <button className="btn btn-secondary" onClick={onRefresh} disabled={refreshing}>
        {refreshing ? "Refreshing..." : "Refresh"}
      </button>
      <OperatorWorkQueue
        items={controlSummary?.operator_work_items ?? []}
        onRunDetail={onRunDetail}
      />
      <Overview controlSummary={controlSummary} onLlmModels={onLlmModels} />
      <RunsView
        runs={runs}
        selectedRunDetail={selectedRunDetail}
        onRunDetail={onRunDetail}
        onArtifactRead={onArtifactRead}
        onApprove={onApprove}
        onReject={onReject}
        onImprovementRequestMerge={onImprovementRequestMerge}
        onImprovementMerge={onImprovementMerge}
        onImprovementReject={onImprovementReject}
      />
      <ApprovalsView approvals={approvals} onApprove={onApprove} onReject={onReject} />
      <ImprovementProposals
        improvements={improvements}
        onArtifactRead={onArtifactRead}
        onRequestMerge={onImprovementRequestMerge}
        onMerge={onImprovementMerge}
        onReject={onImprovementReject}
      />
    </div>
  );
}
