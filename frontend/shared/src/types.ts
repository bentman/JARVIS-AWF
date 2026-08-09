/** Section 16.3 method surface - exhaustive. Adding a method is a change to
 * this list; a frontend needing an unlisted method fixes this file, never
 * reads `data/` directly. */
export type MethodName =
  | "awf/run.start"
  | "awf/run.status"
  | "awf/run.list"
  | "awf/run.resume"
  | "awf/approval.list"
  | "awf/approval.approve"
  | "awf/approval.reject"
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
  | "awf/episodic.search"
  | "awf/episodic.timeline"
  | "awf/secret.set"
  | "awf/secret.listNames"
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
