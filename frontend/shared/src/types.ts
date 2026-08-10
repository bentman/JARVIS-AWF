/** Section 16.3 method surface - exhaustive. Adding a method is a change to
 * this list; a frontend needing an unlisted method fixes this file, never
 * reads `data/` directly. */
export type MethodName =
  | "awf/run.start"
  | "awf/run.status"
  | "awf/run.list"
  | "awf/run.resume"
  | "awf/approval.list"
  | "awf/approval.detail"
  | "awf/approval.approve"
  | "awf/approval.reject"
  | "awf/machine.actionPreview"
  | "awf/improvement.list"
  | "awf/improvement.get"
  | "awf/improvement.prepare"
  | "awf/improvement.markReady"
  | "awf/improvement.requestMerge"
  | "awf/improvement.merge"
  | "awf/improvement.reject"
  | "awf/artifact.list"
  | "awf/artifact.read"
  | "awf/registry.list"
  | "awf/registry.get"
  | "awf/registry.validate"
  | "awf/registry.publish"
  | "awf/registry.reindex"
  | "awf/registry.retire"
  | "awf/registry.trust"
  | "awf/workflow.authorDraft"
  | "awf/proposal.get"
  | "awf/proposal.update"
  | "awf/proposal.publish"
  | "awf/proposal.reject"
  | "awf/memory.search"
  | "awf/memory.get"
  | "awf/memory.propose"
  | "awf/memory.publish"
  | "awf/memory.reject"
  | "awf/memory.block"
  | "awf/session.start"
  | "awf/session.append"
  | "awf/session.show"
  | "awf/session.summarize"
  | "awf/voice.sessionStart"
  | "awf/voice.event"
  | "awf/voice.sessionClose"
  | "awf/voice.submitText"
  | "awf/episodic.search"
  | "awf/episodic.timeline"
  | "awf/secret.set"
  | "awf/secret.listNames"
  | "awf/control.summary"
  | "awf/control.runDetail"
  | "awf/system.readiness"
  | "awf/llm.servers"
  | "awf/llm.models"
  | "awf/llm.serveStatus"
  | "awf/events.subscribe";

export interface JsonRpcRequest {
  jsonrpc: "2.0";
  id: number;
  method: MethodName;
  params?: Record<string, unknown>;
}

export interface JsonRpcError {
  code: number;
  message: string;
}

export interface JsonRpcResponse<T = unknown> {
  jsonrpc: "2.0";
  id: number | null;
  result?: T;
  error?: JsonRpcError;
}

export interface RunStep {
  step_id: string;
  run_id: string;
  node_id: string;
  attempt: number;
  status: string;
  output_json: string | null;
  started_at: string;
  ended_at: string | null;
}

export interface RunStatus {
  run_id: string;
  workflow_ref: string;
  status: string;
  steps: RunStep[];
  [key: string]: unknown;
}

export interface RunSummary {
  run_id: string;
  workflow_ref: string;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface RunStartResult {
  run_id: string;
  status: string;
  repairs_used?: number;
  verdict_artifact_id?: string | null;
  [key: string]: unknown;
}

export interface Approval {
  approval_id: string;
  run_id: string;
  step_id: string;
  action_digest: string;
  status: string;
  reason: string | null;
  requested_at: string;
  decided_at: string | null;
  risk_class?: string | null;
  preview?: MachineActionPreview | null;
}

export type RiskClass = "R0" | "R1" | "R2" | "R3";

export interface ApprovalApproveOptions {
  channel?: "manual" | "voice";
  riskClass?: RiskClass;
}

export interface MachineActionPreview {
  machine_action: Record<string, unknown>;
  machine_action_digest: string;
}

export interface ApprovalDetail {
  approval: Approval;
  preview: MachineActionPreview | null;
}

export interface ImprovementProposal {
  improvement_id: string;
  run_id: string;
  target_repo: string;
  target_branch: string;
  base_commit: string;
  candidate_branch: string;
  candidate_commit: string;
  diff_digest: string;
  patch_artifact_id: string;
  status: "draft" | "ready_for_review" | "approved" | "merged" | "rejected" | "abandoned";
  summary: string;
  changed_paths: Record<string, unknown>[];
  verdict_artifact_id: string | null;
  validation_artifact_ids: string[];
  merge_commit: string | null;
  created_at: string;
  updated_at: string;
  decided_at: string | null;
  closed_at: string | null;
  approval: Approval | null;
  merge_action_digest: string;
  events: Record<string, unknown>[];
}

export interface Artifact {
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

export interface RegistryEntry {
  source: "config" | "data";
  kind: string;
  name: string;
  version: string;
  trust_status?: string | null;
  digest?: string | null;
}

export interface ReadinessResult {
  device: string;
  ready: boolean;
  reason: string;
}

export interface SystemReadiness {
  profile_id: string | null;
  inventory: Record<string, unknown> | null;
  tokens: string[];
  readiness: Record<string, ReadinessResult>;
  error?: string;
}

export interface LlmServersReport {
  default_server?: string;
  host_profile_id?: string;
  current_selection?: Record<string, unknown> | null;
  servers?: Record<string, Record<string, unknown>>;
  error?: string;
}

export interface LlmModelsReport {
  local_models?: Record<string, unknown>[];
  ollama_models?: Record<string, unknown>[];
  ollama_models_error?: string;
  error?: string;
}

export interface LlmServeStatus {
  state?: string;
  server_id?: string | null;
  base_url?: string | null;
  model_path?: string | null;
  profile_id?: string | null;
  pid?: number | null;
  reason?: string | null;
  error?: string;
  [key: string]: unknown;
}

export interface ControlSummary {
  runs: RunSummary[];
  approvals: Approval[];
  improvements: ImprovementProposal[];
  recent_verdicts: Artifact[];
  registry_counts: Record<string, number>;
  llm: {
    servers: LlmServersReport;
    status: LlmServeStatus;
  };
  readiness: SystemReadiness;
}

export interface ControlRunDetail {
  run: RunStatus;
  artifacts: Artifact[];
  timeline: Record<string, unknown>;
  improvements: ImprovementProposal[];
  verdicts: Artifact[];
}

export interface Proposal {
  proposal_id: string;
  kind: "workflows" | "semantic-memories";
  name: string;
  version: string;
  status: "draft" | "published" | "rejected";
  draft_digest: string;
  draft_path: string;
  summary: string;
  created_at: string;
  updated_at: string;
  decided_at: string | null;
  published_digest: string | null;
  rejection_reason: string | null;
  content: string;
  events: Record<string, unknown>[];
}

export type VoiceSessionState =
  | "idle"
  | "armed"
  | "listening"
  | "transcribing"
  | "submitting"
  | "speaking"
  | "recovering"
  | "closed";

export type VoiceFrameType =
  | "session.started"
  | "session.idle"
  | "session.closed"
  | "wake.detected"
  | "vad.speech_started"
  | "vad.speech_stopped"
  | "stt.partial"
  | "stt.final"
  | "core.submitted"
  | "core.output_text"
  | "tts.audio_chunk"
  | "tts.done"
  | "interruption"
  | "error";

export interface VoiceSessionResult {
  voice_session_id: string;
  memory_session_id: string;
  state: VoiceSessionState;
}

export interface VoiceSubmitTextResult {
  voice_session_id: string;
  state: VoiceSessionState;
  recognized_text: string;
  response_text: string;
  run: RunStartResult;
  voice: {
    voice_profile_ref: string;
    voice_id: string;
    engine: string;
    model: string;
    speed: number;
    privacy: { local_only: boolean };
    limits: { max_seconds_per_utterance: number };
  };
}

export interface SemanticMemorySearchHit {
  kind: "semantic-memories";
  name: string;
  version: string;
  ref: string;
  source: "config" | "data";
  digest: string | null;
  trust_status: string | null;
  score: number;
  confidence: number;
  object: Record<string, unknown>;
}

export interface EpisodicSearchHit {
  source: "events";
  score: number;
  event_id: string;
  run_id: string;
  step_id: string | null;
  event_type: string;
  actor: string;
  reason_code: string;
  payload_json: string | null;
  workflow_ref: string;
  node_id: string | null;
  created_at: string;
}

export interface MemorySearchResult {
  query: string;
  profile_ref: string;
  semantic: SemanticMemorySearchHit[];
  episodic: EpisodicSearchHit[];
  context: Record<string, unknown>;
}

export interface ActiveSession {
  session_id: string;
  title: string | null;
  status: "active" | "summarized" | "expired";
  created_at: string;
  updated_at: string;
  expires_at: string | null;
  entries?: Record<string, unknown>[];
}

export class ProtocolError extends Error {
  code: number;
  constructor(code: number, message: string) {
    super(message);
    this.code = code;
    this.name = "ProtocolError";
  }
}
