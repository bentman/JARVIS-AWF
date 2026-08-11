import React, { useEffect, useRef, useState } from "react";
import { ApprovalConfirmation } from "./ApprovalConfirmation.js";
import { ApprovalsView } from "./ApprovalsView.js";
import {
  ImprovementProposals,
  type ApprovalSummary,
  type ArtifactSummary,
  type ControlRunDetail,
  type ControlSummary,
  type ImprovementSummary,
  type LlmModelsReport,
  type RunSummary,
} from "./Dashboard.js";
import { MemoryPanel, type MemorySearchResult } from "./MemoryPanel.js";
import { Overview } from "./Overview.js";
import { ProposalReview, type ProposalSummary } from "./ProposalReview.js";
import { RegistryActions, type RegistryEntry } from "./RegistryActions.js";
import { RunsView } from "./RunsView.js";
import { stateClass } from "./state.js";
import { ArchiveIcon, ChatIcon, DatabaseIcon, PlayIcon, ShieldIcon, SparkleIcon, ZapIcon, type IconProps } from "./icons.js";
import { Transcript, type TranscriptEntry } from "./Transcript.js";
import { VoiceActivation, type VoiceActivationHandle, type VoiceSessionResult, type VoiceSubmitTextResult } from "./VoiceActivation.js";
import type { RiskClass } from "../voiceApproval.js";

export interface PendingApproval {
  approvalId: string;
  actionDigest: string;
  riskClass: RiskClass;
}

export interface VoiceSessionFns {
  onVoiceSessionStart?: (title?: string, wakeEnabled?: boolean) => Promise<VoiceSessionResult>;
  onVoicePushToTalkStart?: (voiceSessionId: string, turnId: string) => Promise<VoiceSessionResult>;
  onVoicePushToTalkStop?: (voiceSessionId: string, turnId: string) => Promise<VoiceSessionResult>;
  onVoiceInterrupt?: (voiceSessionId: string, turnId: string) => Promise<VoiceSessionResult>;
  onVoiceSubmitText?: (
    voiceSessionId: string,
    text: string,
    workflowRef: string,
    voiceProfileRef: string | undefined,
    turnId: string,
  ) => Promise<VoiceSubmitTextResult>;
  onVoiceSpeakText?: (
    text: string,
    voiceId: string | undefined,
    responseAudioOutPath: string,
  ) => Promise<{ response_audio_path: string }>;
}

export interface AppProps extends VoiceSessionFns {
  initialTranscript?: TranscriptEntry[];
  pendingApproval?: PendingApproval;
  voiceConfirmed?: boolean;
  onApprove: (approvalId: string) => void;
  onReject: (approvalId: string, reason: string) => void;
  onRunList?: () => Promise<RunSummary[]>;
  onApprovalList?: () => Promise<ApprovalSummary[]>;
  onImprovementList?: () => Promise<ImprovementSummary[]>;
  onControlSummary?: () => Promise<ControlSummary>;
  onControlRunDetail?: (runId: string) => Promise<ControlRunDetail>;
  onRegistryValidate?: (path: string, kind?: string) => Promise<unknown>;
  onRegistryPublish?: (path: string, kind: string) => Promise<unknown>;
  onRegistryReindex?: () => Promise<unknown>;
  onRegistryRetire?: (kind: string, name: string, version: string) => Promise<unknown>;
  onRegistryTrust?: (kind: string, name: string, version: string, status: string) => Promise<unknown>;
  onRegistryList?: (kind: string) => Promise<RegistryEntry[]>;
  onRegistryGet?: (kind: string, name: string, version: string) => Promise<Record<string, unknown>>;
  onArtifactRead?: (artifactId: string) => Promise<ArtifactSummary & { content: string }>;
  onLlmModels?: () => Promise<LlmModelsReport>;
  onProposalGet?: (proposalId: string) => Promise<ProposalSummary>;
  onProposalPublish?: (proposalId: string, digest: string) => Promise<unknown>;
  onProposalReject?: (proposalId: string, reason?: string) => Promise<unknown>;
  onMemorySearch?: (query: string) => Promise<MemorySearchResult>;
  onMemoryBlock?: (ref: string) => Promise<unknown>;
  onMemoryPublish?: (proposalId: string, digest: string) => Promise<unknown>;
  onMemoryReject?: (proposalId: string, reason?: string) => Promise<unknown>;
}

type ViewName = "chat" | "status" | "runs" | "approvals" | "proposals" | "memory" | "registry";

// An approval whose node never declared `riskClass` (Section 12.2) has no
// real value to show - treated as R2 here too, the same safe-never-R0/R1
// default `op_approval_approve` itself uses, not silently downgraded to
// something voice could auto-approve.
function toPendingApproval(approval: ApprovalSummary): PendingApproval {
  return {
    approvalId: approval.approval_id,
    actionDigest: approval.action_digest,
    riskClass: (approval.risk_class as RiskClass | null) ?? "R2",
  };
}

export function App({
  initialTranscript = [],
  pendingApproval,
  voiceConfirmed = false,
  onApprove,
  onReject,
  onVoiceSessionStart,
  onVoicePushToTalkStart,
  onVoicePushToTalkStop,
  onVoiceInterrupt,
  onVoiceSubmitText,
  onVoiceSpeakText,
  onRunList,
  onApprovalList,
  onImprovementList,
  onControlSummary,
  onControlRunDetail,
  onRegistryValidate,
  onRegistryPublish,
  onRegistryReindex,
  onRegistryRetire,
  onRegistryTrust,
  onRegistryList,
  onRegistryGet,
  onArtifactRead,
  onLlmModels,
  onProposalGet,
  onProposalPublish,
  onProposalReject,
  onMemorySearch,
  onMemoryBlock,
  onMemoryPublish,
  onMemoryReject,
}: AppProps): React.JSX.Element {
  const [entries, setEntries] = useState<TranscriptEntry[]>(initialTranscript);
  const nextId = useRef(initialTranscript.length);
  const voiceRef = useRef<VoiceActivationHandle | null>(null);
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [approvals, setApprovals] = useState<ApprovalSummary[]>([]);
  const [improvements, setImprovements] = useState<ImprovementSummary[]>([]);
  const [controlSummary, setControlSummary] = useState<ControlSummary | undefined>(undefined);
  const [selectedRunDetail, setSelectedRunDetail] = useState<ControlRunDetail | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [view, setView] = useState<ViewName | undefined>(undefined);

  const refresh = async () => {
    if (!onControlSummary && !onRunList && !onApprovalList && !onImprovementList) return;
    setRefreshing(true);
    try {
      if (onControlSummary) {
        const summary = await onControlSummary();
        setControlSummary(summary);
        setRuns(summary.runs);
        setApprovals(summary.approvals);
        setImprovements(summary.improvements);
        return;
      }
      const [nextRuns, nextApprovals, nextImprovements] = await Promise.all([
        onRunList ? onRunList() : Promise.resolve(runs),
        onApprovalList ? onApprovalList() : Promise.resolve(approvals),
        onImprovementList ? onImprovementList() : Promise.resolve(improvements),
      ]);
      setRuns(nextRuns);
      setApprovals(nextApprovals);
      setImprovements(nextImprovements);
    } finally {
      setRefreshing(false);
    }
  };

  const handleRunDetail = async (runId: string) => {
    if (!onControlRunDetail) return;
    setSelectedRunDetail(await onControlRunDetail(runId));
  };

  useEffect(() => {
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleVoiceSubmit = async (
    voiceSessionId: string,
    text: string,
    workflowRef: string,
    voiceProfileRef: string | undefined,
    turnId: string,
  ) => {
    if (!onVoiceSubmitText) throw new Error("voice submit is not available");
    const result = await onVoiceSubmitText(voiceSessionId, text, workflowRef, voiceProfileRef, turnId);
    setEntries((prev) => [
      ...prev,
      { id: nextId.current++, speaker: "Operator (voice)", text: result.recognized_text },
      {
        id: nextId.current++,
        speaker: result.voice?.voice_profile_ref ?? "AWF",
        text: result.response_text,
      },
    ]);
    if (onVoiceSpeakText) {
      const spoken = await onVoiceSpeakText(
        result.response_text,
        result.voice?.voice_id,
        "/tmp/awf-gui-live-response.wav",
      );
      if (typeof Audio !== "undefined") {
        void new Audio(spoken.response_audio_path).play().catch(() => undefined);
      }
    }
    return result;
  };

const handleComposerSend = (text: string) => {
    setEntries((prev) => [...prev, { id: nextId.current++, speaker: "Operator", text }]);
  };
  const handleApprove = (approvalId: string) => {
    onApprove(approvalId);
    void refresh();
  };

  const handleReject = (approvalId: string, reason: string) => {
    onReject(approvalId, reason);
    void refresh();
  };

  // An explicit `pendingApproval` prop wins (a caller with its own source
  // of truth); otherwise the first real pending approval from the fetched
  // list is what the operator actually sees and can act on.
  const effectivePendingApproval = pendingApproval ?? (approvals.length > 0 ? toPendingApproval(approvals[0]) : undefined);

  const statusAvailable = !!(onControlSummary || onRunList || onApprovalList || onImprovementList);
  const runsAvailable = statusAvailable;
  const approvalsAvailable = statusAvailable;
  const proposalsAvailable = !!(onProposalGet && onProposalPublish && onProposalReject);
  const memoryAvailable = !!(onMemorySearch && onMemoryBlock && onMemoryPublish && onMemoryReject);
  const registryAvailable = !!(
    onRegistryValidate &&
    onRegistryPublish &&
    onRegistryReindex &&
    onRegistryRetire &&
    onRegistryTrust
  );
  const voiceAvailable = !!(
    onVoiceSessionStart &&
    onVoicePushToTalkStart &&
    onVoicePushToTalkStop &&
    onVoiceInterrupt &&
    onVoiceSubmitText
  );

  const views: { name: ViewName; label: string; badge?: number; icon: React.FC<IconProps> }[] = [
    // The first page is always the chat + voice surface (ADR-0025): a
    // scrollable conversation window that voice and typed chat share.
    // Status/diagnostics live behind their own nav button, never below it.
    { name: "chat" as const, label: "Chat", icon: ChatIcon },
    ...(statusAvailable ? [{ name: "status" as const, label: "Status", icon: SparkleIcon }] : []),
    ...(runsAvailable ? [{ name: "runs" as const, label: "Runs", icon: PlayIcon }] : []),
    ...(approvalsAvailable
      ? [{ name: "approvals" as const, label: "Approvals", icon: ShieldIcon, badge: approvals.length || undefined }]
      : []),
    ...(proposalsAvailable
      ? [
          {
            name: "proposals" as const,
            label: "Proposals",
            icon: ZapIcon,
            badge: improvements.length || undefined,
          },
        ]
      : []),
    ...(memoryAvailable ? [{ name: "memory" as const, label: "Memory", icon: ArchiveIcon }] : []),
    ...(registryAvailable ? [{ name: "registry" as const, label: "Registry", icon: DatabaseIcon }] : []),
  ];
  const activeView = view && views.some((v) => v.name === view) ? view : views[0]?.name;

  const readinessEntries = controlSummary ? Object.values(controlSummary.readiness.readiness) : [];
  const readinessOverall =
    readinessEntries.length > 0 && readinessEntries.every((entry) => entry.ready) ? "ready" : "not ready";
  const llmState = controlSummary?.llm.status?.state ?? "idle";

  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand">
          <span className="brand-badge" aria-hidden="true">
            A
          </span>
          <span className="brand-text">
            <span className="brand-line">
              <span className="mono">AWF</span>
              <span className="system-pill">System active</span>
            </span>
            <span className="brand-tag">Agentic Workflow Fabric</span>
          </span>
        </div>
        <nav aria-label="Views">
          <ul className="nav-list">
            {views.map((v) => (
              <li key={v.name}>
                <button
                  type="button"
                  className="btn nav-item"
                  aria-current={v.name === activeView ? "page" : undefined}
                  onClick={() => setView(v.name)}
                >
                  {v.icon && <v.icon size={13} className="nav-icon" />}
                  {v.label}
                  {v.badge !== undefined && <span className="rail-badge">{v.badge}</span>}
                </button>
              </li>
            ))}
          </ul>
        </nav>
        <div className="status-bar" role="status" aria-label="Status">
          <span className="mono">{controlSummary?.readiness.profile_id ?? "no profile"}</span>
          <span className={`chip ${stateClass(readinessOverall)}`}>{readinessOverall}</span>
          <span className={`chip ${stateClass(llmState)}`}>{llmState}</span>
          <span className="chip">
            {approvals.length} pending approval{approvals.length === 1 ? "" : "s"}
          </span>
        </div>
        <button type="button" className="btn btn-secondary" onClick={() => void refresh()} disabled={refreshing}>
          {refreshing ? "Refreshing..." : "Refresh"}
        </button>
      </header>
      <main className="main">
          {activeView === "chat" && (
            <div className="chat-page">
              <div className="chat-frame">
                <Transcript
                  entries={entries}
                  onSend={handleComposerSend}
                  onMic={voiceAvailable ? () => voiceRef.current?.togglePushToTalk() : undefined}
                />
                {voiceAvailable && (
                  <VoiceActivation
                    ref={voiceRef}
                    onSessionStart={onVoiceSessionStart!}
                    onPushToTalkStart={onVoicePushToTalkStart!}
                    onPushToTalkStop={onVoicePushToTalkStop!}
                    onInterrupt={onVoiceInterrupt!}
                    onSubmitText={handleVoiceSubmit}
                  />
                )}
              </div>
            </div>
          )}
          {activeView === "status" && statusAvailable && (
            <>
              <div className="view-header">
                <div>
                  <div className="view-kicker">
                    <SparkleIcon size={12} />
                    Resident Mind
                  </div>
                  <h1 className="view-title">Control center</h1>
                </div>
              </div>
              <Overview controlSummary={controlSummary} onLlmModels={onLlmModels} />
            </>
          )}
          {activeView === "runs" && (
            <RunsView
              runs={runs}
              selectedRunDetail={selectedRunDetail}
              onRunDetail={onControlRunDetail ? (runId: string) => void handleRunDetail(runId) : undefined}
              onArtifactRead={onArtifactRead}
            />
          )}
          {activeView === "approvals" && <ApprovalsView approvals={approvals} />}
          {activeView === "proposals" && (
            <>
              {onProposalGet && onProposalPublish && onProposalReject && (
                <ProposalReview
                  onProposalGet={onProposalGet}
                  onProposalPublish={onProposalPublish}
                  onProposalReject={onProposalReject}
                />
              )}
              <ImprovementProposals improvements={improvements} onArtifactRead={onArtifactRead} />
            </>
          )}
          {activeView === "memory" && onMemorySearch && onMemoryBlock && onMemoryPublish && onMemoryReject && (
            <MemoryPanel
              onMemorySearch={onMemorySearch}
              onMemoryBlock={onMemoryBlock}
              onMemoryPublish={onMemoryPublish}
              onMemoryReject={onMemoryReject}
            />
          )}
          {activeView === "registry" &&
            onRegistryValidate &&
            onRegistryPublish &&
            onRegistryReindex &&
            onRegistryRetire &&
            onRegistryTrust && (
              <RegistryActions
                onRegistryValidate={onRegistryValidate}
                onRegistryPublish={onRegistryPublish}
                onRegistryReindex={onRegistryReindex}
                onRegistryRetire={onRegistryRetire}
                onRegistryTrust={onRegistryTrust}
                onRegistryList={onRegistryList}
                onRegistryGet={onRegistryGet}
              />
            )}

      </main>
      {effectivePendingApproval && (
        <ApprovalConfirmation
          approvalId={effectivePendingApproval.approvalId}
          actionDigest={effectivePendingApproval.actionDigest}
          riskClass={effectivePendingApproval.riskClass}
          voiceConfirmed={voiceConfirmed}
          onApprove={handleApprove}
          onReject={handleReject}
        />
      )}
    </div>
  );
}
