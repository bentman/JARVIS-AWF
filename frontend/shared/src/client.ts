import type { Transport } from "./transport.js";
import {
  ProtocolError,
  type Approval,
  type ApprovalApproveOptions,
  type ApprovalDetail,
  type Artifact,
  type ControlRunDetail,
  type ControlSummary,
  type ImprovementProposal,
  type JsonRpcResponse,
  type LlmModelsReport,
  type LlmServeStatus,
  type LlmServersReport,
  type EventsSnapshot,
  type MachineActionPreview,
  type MemorySearchResult,
  type MethodName,
  type Proposal,
  type RegistryEntry,
  type RunStartResult,
  type RunStatus,
  type RunSummary,
  type SystemDoctor,
  type SystemReadiness,
  type VoiceFrameType,
  type VoiceSessionResult,
  type VoiceSubmitTextResult,
} from "./types.js";

/** The single TypeScript protocol client (Section 16.3) - both frontends
 * (AWF-CLI, AWF-GUI) consume this; neither may implement its own protocol
 * layer. Every method maps 1:1 onto an `awf serve --stdio` JSON-RPC method;
 * the protocol adds no authority beyond what the core operation itself
 * grants. */
export class ProtocolClient {
  private transport: Transport;
  private nextId = 1;
  private pending = new Map<
    number,
    { resolve: (value: unknown) => void; reject: (reason: unknown) => void }
  >();

  constructor(transport: Transport) {
    this.transport = transport;
    this.transport.onLine((line) => this.handleLine(line));
    this.transport.onExit((code) => this.handleExit(code));
  }

  private handleLine(line: string): void {
    const trimmed = line.trim();
    if (!trimmed) return;
    let response: JsonRpcResponse;
    try {
      response = JSON.parse(trimmed) as JsonRpcResponse;
    } catch {
      return;
    }
    if (response.id === null || response.id === undefined) return;
    const pending = this.pending.get(response.id);
    if (!pending) return;
    this.pending.delete(response.id);
    if (response.error) {
      pending.reject(new ProtocolError(response.error.code, response.error.message));
    } else {
      pending.resolve(response.result);
    }
  }

  private handleExit(code: number | null): void {
    const error = new Error(`awf core process exited (code=${code}) before responding`);
    for (const { reject } of this.pending.values()) reject(error);
    this.pending.clear();
  }

  private call<T>(method: MethodName, params?: Record<string, unknown>): Promise<T> {
    const id = this.nextId++;
    const request = { jsonrpc: "2.0" as const, id, method, params };
    const promise = new Promise<T>((resolve, reject) => {
      this.pending.set(id, { resolve: resolve as (value: unknown) => void, reject });
    });
    this.transport.send(JSON.stringify(request));
    return promise;
  }

  runStart(workflowRef: string, input: Record<string, unknown> = {}): Promise<RunStartResult> {
    return this.call("awf/run.start", { workflow: workflowRef, input });
  }

  runStatus(runId: string): Promise<RunStatus> {
    return this.call("awf/run.status", { runId });
  }

  runList(): Promise<RunSummary[]> {
    return this.call("awf/run.list", {});
  }

  runResume(): Promise<RunStartResult[]> {
    return this.call("awf/run.resume", {});
  }

  approvalList(): Promise<Approval[]> {
    return this.call("awf/approval.list", {});
  }

  approvalDetail(approvalId: string): Promise<ApprovalDetail> {
    return this.call("awf/approval.detail", { approvalId });
  }

  approvalApprove(approvalId: string, options: ApprovalApproveOptions = {}): Promise<Approval> {
    return this.call("awf/approval.approve", { approvalId, channel: options.channel, riskClass: options.riskClass });
  }

  approvalReject(approvalId: string, reason: string): Promise<Approval> {
    return this.call("awf/approval.reject", { approvalId, reason });
  }

  machineActionPreview(approvalId: string): Promise<MachineActionPreview> {
    return this.call("awf/machine.actionPreview", { approvalId });
  }

  improvementList(status?: string): Promise<ImprovementProposal[]> {
    return this.call("awf/improvement.list", { status });
  }

  improvementGet(improvementId: string): Promise<ImprovementProposal> {
    return this.call("awf/improvement.get", { improvementId });
  }

  improvementPrepare(runId: string, summary?: string): Promise<ImprovementProposal> {
    return this.call("awf/improvement.prepare", { runId, summary });
  }

  improvementMarkReady(
    improvementId: string,
    verdictArtifactId: string,
    validationArtifactIds: string[] = [],
  ): Promise<ImprovementProposal> {
    return this.call("awf/improvement.markReady", { improvementId, verdictArtifactId, validationArtifactIds });
  }

  improvementRequestMerge(improvementId: string): Promise<Record<string, unknown>> {
    return this.call("awf/improvement.requestMerge", { improvementId });
  }

  improvementMerge(improvementId: string, approvalId: string): Promise<ImprovementProposal> {
    return this.call("awf/improvement.merge", { improvementId, approvalId });
  }

  improvementReject(improvementId: string, reason?: string): Promise<ImprovementProposal> {
    return this.call("awf/improvement.reject", { improvementId, reason });
  }

  artifactList(runId: string): Promise<Artifact[]> {
    return this.call("awf/artifact.list", { runId });
  }

  artifactRead(artifactId: string): Promise<Artifact & { content: string }> {
    return this.call("awf/artifact.read", { artifactId });
  }

  registryList(kind: string): Promise<RegistryEntry[]> {
    return this.call("awf/registry.list", { kind });
  }

  registryGet(kind: string, name: string, version: string): Promise<Record<string, unknown>> {
    return this.call("awf/registry.get", { kind, name, version });
  }

  registryValidate(path: string, kind?: string): Promise<Record<string, unknown>> {
    return this.call("awf/registry.validate", kind ? { path, kind } : { path });
  }

  registryPublish(path: string, kind: string): Promise<Record<string, unknown>> {
    return this.call("awf/registry.publish", { path, kind });
  }

  registryReindex(): Promise<Record<string, unknown>> {
    return this.call("awf/registry.reindex", {});
  }

  registryRetire(kind: string, name: string, version: string): Promise<Record<string, unknown>> {
    return this.call("awf/registry.retire", { kind, name, version });
  }

  registryTrust(kind: string, name: string, version: string, status: string): Promise<Record<string, unknown>> {
    return this.call("awf/registry.trust", { kind, name, version, status });
  }

  workflowAuthorDraft(options: {
    objective: string;
    name?: string;
    version?: string;
    profile?: string;
  }): Promise<Proposal> {
    return this.call("awf/workflow.authorDraft", options);
  }

  proposalGet(proposalId: string): Promise<Proposal> {
    return this.call("awf/proposal.get", { proposalId });
  }

  proposalUpdate(proposalId: string, content: string, summary?: string): Promise<Proposal> {
    return this.call("awf/proposal.update", { proposalId, content, summary });
  }

  proposalPublish(proposalId: string, digest: string): Promise<Record<string, unknown>> {
    return this.call("awf/proposal.publish", { proposalId, digest });
  }

  proposalReject(proposalId: string, reason?: string): Promise<Proposal> {
    return this.call("awf/proposal.reject", { proposalId, reason });
  }

  memorySearch(query: string, profile = "default@1.0.0"): Promise<MemorySearchResult> {
    return this.call("awf/memory.search", { query, profile });
  }

  memoryGet(ref: string): Promise<Record<string, unknown>> {
    return this.call("awf/memory.get", { ref });
  }

  memoryPropose(path: string, summary?: string): Promise<Proposal> {
    return this.call("awf/memory.propose", { path, summary });
  }

  memoryPublish(proposalId: string, digest: string): Promise<Record<string, unknown>> {
    return this.call("awf/memory.publish", { proposalId, digest });
  }

  memoryReject(proposalId: string, reason?: string): Promise<Proposal> {
    return this.call("awf/memory.reject", { proposalId, reason });
  }

  memoryBlock(ref: string): Promise<Record<string, unknown>> {
    return this.call("awf/memory.block", { ref });
  }

  sessionStart(title?: string, expiresAt?: string): Promise<Record<string, unknown>> {
    return this.call("awf/session.start", { title, expiresAt });
  }

  sessionAppend(
    sessionId: string,
    role: string,
    content: Record<string, unknown>,
    summary?: string,
  ): Promise<Record<string, unknown>> {
    return this.call("awf/session.append", { sessionId, role, content, summary });
  }

  sessionShow(sessionId: string): Promise<Record<string, unknown>> {
    return this.call("awf/session.show", { sessionId });
  }

  sessionSummarize(sessionId: string, summary?: string): Promise<Record<string, unknown>> {
    return this.call("awf/session.summarize", { sessionId, summary });
  }

  voiceSessionStart(title?: string, wakeEnabled = false): Promise<VoiceSessionResult> {
    return this.call("awf/voice.sessionStart", { title, wakeEnabled });
  }

  voiceEvent(
    voiceSessionId: string,
    frameType: VoiceFrameType,
    payload: Record<string, unknown> = {},
    turnId?: string,
  ): Promise<VoiceSessionResult> {
    return this.call("awf/voice.event", { voiceSessionId, frameType, payload, turnId });
  }

  voiceSessionClose(voiceSessionId: string, reason?: string): Promise<VoiceSessionResult> {
    return this.call("awf/voice.sessionClose", { voiceSessionId, reason });
  }

  voiceSubmitText(options: {
    voiceSessionId: string;
    text: string;
    workflowRef?: string;
    voiceProfileRef?: string;
    turnId?: string;
  }): Promise<VoiceSubmitTextResult> {
    return this.call("awf/voice.submitText", options);
  }

  episodicSearch(query: string, runId?: string): Promise<Record<string, unknown>[]> {
    return this.call("awf/episodic.search", { query, runId });
  }

  episodicTimeline(runId: string): Promise<Record<string, unknown>> {
    return this.call("awf/episodic.timeline", { runId });
  }

  secretSet(name: string, value: string): Promise<Record<string, unknown>> {
    return this.call("awf/secret.set", { name, value });
  }

  secretListNames(): Promise<string[]> {
    return this.call("awf/secret.listNames", {});
  }

  controlSummary(): Promise<ControlSummary> {
    return this.call("awf/control.summary", {});
  }

  controlRunDetail(runId: string): Promise<ControlRunDetail> {
    return this.call("awf/control.runDetail", { runId });
  }

  systemReadiness(): Promise<SystemReadiness> {
    return this.call("awf/system.readiness", {});
  }

  systemDoctor(): Promise<SystemDoctor> {
    return this.call("awf/system.doctor", {});
  }

  llmServers(): Promise<LlmServersReport> {
    return this.call("awf/llm.servers", {});
  }

  llmModels(): Promise<LlmModelsReport> {
    return this.call("awf/llm.models", {});
  }

  llmServeStatus(): Promise<LlmServeStatus> {
    return this.call("awf/llm.serveStatus", {});
  }

  eventsSubscribe(options: { runId?: string; limit?: number } = {}): Promise<EventsSnapshot> {
    return this.call("awf/events.subscribe", options);
  }

  close(): void {
    this.transport.close();
  }
}
