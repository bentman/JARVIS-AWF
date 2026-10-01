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
import { EvidencePanel } from "./EvidencePanel.js";
import { MemoryPanel, type MemorySearchResult } from "./MemoryPanel.js";
import { OperatorWorkQueue } from "./OperatorWorkQueue.js";
import { Overview } from "./Overview.js";
import { ProposalReview, type ProposalSummary } from "./ProposalReview.js";
import { RegistryActions, type RegistryEntry } from "./RegistryActions.js";
import { RunTimeline } from "./RunTimeline.js";
import { RunsView } from "./RunsView.js";
import { StartWorkPanel } from "./StartWorkPanel.js";
import { stateClass } from "./state.js";
import { ChatIcon, DatabaseIcon, SparkleIcon, type IconProps } from "./icons.js";
import { Transcript, type TranscriptEntry } from "./Transcript.js";
import { VoiceActivation, type VoiceActivationHandle, type VoiceSessionResult, type VoiceSubmitTextResult } from "./VoiceActivation.js";
import type { RiskClass } from "../voiceApproval.js";
import type { Settings } from "@awf/protocol-client";

export interface PendingApproval {
  approvalId: string;
  actionDigest: string;
  riskClass: RiskClass;
  preview?: { machine_action?: Record<string, unknown>; machine_action_digest?: string } | null;
}

export interface VoiceSessionFns {
  onVoiceSessionStart?: (title?: string, wakeEnabled?: boolean) => Promise<VoiceSessionResult>;
  onVoicePushToTalkStart?: (voiceSessionId: string, turnId: string) => Promise<VoiceSessionResult>;
  onVoicePushToTalkStop?: (voiceSessionId: string, turnId: string) => Promise<VoiceSessionResult>;
  onVoiceInterrupt?: (voiceSessionId: string, turnId: string) => Promise<VoiceSessionResult>;
  onVoiceEvent?: (
    voiceSessionId: string,
    frameType: string,
    payload?: Record<string, unknown>,
    turnId?: string,
  ) => Promise<VoiceSessionResult>;
  onVoiceSubmitText?: (
    voiceSessionId: string,
    text: string,
    workflowRef: string | undefined,
    voiceProfileRef: string | undefined,
    turnId: string,
  ) => Promise<VoiceSubmitTextResult>;
  onVoiceSpeakText?: (
    text: string,
    voiceId: string | undefined,
    responseAudioOutPath?: string,
  ) => Promise<{ response_audio_path: string }>;
}

export interface TextSubmitResult {
  run_id: string;
  status: string;
  outputs?: {
    response_text?: string;
    [key: string]: unknown;
  };
  reason?: string;
  error?: string;
  [key: string]: unknown;
}

export interface AppProps extends VoiceSessionFns {
  initialSettings?: Settings;
  onGetSettings?: () => Promise<Settings>;
  initialTranscript?: TranscriptEntry[];
  pendingApproval?: PendingApproval;
  voiceConfirmed?: boolean;
  onApprove: (approvalId: string) => void;
  onReject: (approvalId: string, reason: string) => void;
  onTextSubmit?: (text: string, workflowRef: string) => Promise<TextSubmitResult>;
  onRunStart?: (workflowRef: string, input?: Record<string, unknown>, asyncExecution?: boolean) => Promise<TextSubmitResult>;
  onIntentDispatch?: (text: string, options?: { voiceSessionId?: string; turnId?: string; async?: boolean }) => Promise<Record<string, unknown>>;
  onIntentClassify?: (text: string) => Promise<Record<string, unknown>>;
  onRunList?: () => Promise<RunSummary[]>;
  onApprovalList?: () => Promise<ApprovalSummary[]>;
  onApprovalDetail?: (approvalId: string) => Promise<{ approval: ApprovalSummary; preview?: PendingApproval["preview"] }>;
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
  onImprovementRequestMerge?: (improvementId: string) => Promise<unknown>;
  onImprovementMerge?: (improvementId: string, approvalId: string) => Promise<unknown>;
  onImprovementReject?: (improvementId: string, reason?: string) => Promise<unknown>;
  onMemorySearch?: (query: string) => Promise<MemorySearchResult>;
  onMemoryBlock?: (ref: string) => Promise<unknown>;
  onMemoryPublish?: (proposalId: string, digest: string) => Promise<unknown>;
  onMemoryReject?: (proposalId: string, reason?: string) => Promise<unknown>;
}

// Three destinations, matching the CLI: do the work, talk to it, curate what
// it knows. Runs, approvals, and proposals are sections of Operate because
// they are the same queue an operator is already working through.
type ViewName = "operate" | "chat" | "library";

export const DEFAULT_CHAT_WORKFLOW_REF = "assistant-default@1.0.0";

// An approval whose node never declared `riskClass` (Section 12.2) has no
// real value to show - treated as R2 here too, the same safe-never-R0/R1
// default `op_approval_approve` itself uses, not silently downgraded to
// something voice could auto-approve.
function toPendingApproval(approval: ApprovalSummary): PendingApproval {
  return {
    approvalId: approval.approval_id,
    actionDigest: approval.action_digest,
    riskClass: (approval.risk_class as RiskClass | null) ?? "R2",
    preview: approval.preview,
  };
}

export function App({
  initialSettings,
  onGetSettings,
  initialTranscript = [],
  pendingApproval,
  voiceConfirmed = false,
  onApprove,
  onReject,
  onTextSubmit,
  onRunStart,
  onIntentDispatch,
  onIntentClassify,
  onVoiceSessionStart,
  onVoicePushToTalkStart,
  onVoicePushToTalkStop,
  onVoiceInterrupt,
  onVoiceEvent,
  onVoiceSubmitText,
  onVoiceSpeakText,
  onRunList,
  onApprovalList,
  onApprovalDetail,
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
  onImprovementRequestMerge,
  onImprovementMerge,
  onImprovementReject,
  onMemorySearch,
  onMemoryBlock,
  onMemoryPublish,
  onMemoryReject,
}: AppProps): React.JSX.Element {
  const [settings, setSettings] = useState<Settings | undefined>(initialSettings);
  const [entries, setEntries] = useState<TranscriptEntry[]>(initialTranscript);
  const nextId = useRef(initialTranscript.length);
  const voiceRef = useRef<VoiceActivationHandle | null>(null);
  const activeAudioRef = useRef<HTMLAudioElement | null>(null);
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [approvals, setApprovals] = useState<ApprovalSummary[]>([]);
  const [improvements, setImprovements] = useState<ImprovementSummary[]>([]);
  const [controlSummary, setControlSummary] = useState<ControlSummary | undefined>(undefined);
  const [selectedRunDetail, setSelectedRunDetail] = useState<ControlRunDetail | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [view, setView] = useState<ViewName | undefined>(undefined);
  const [chatWorkflowRef, setChatWorkflowRef] = useState(
    initialSettings?.defaultWorkflow ?? DEFAULT_CHAT_WORKFLOW_REF,
  );
  const [workflowOptions, setWorkflowOptions] = useState<string[]>([
    initialSettings?.defaultWorkflow ?? DEFAULT_CHAT_WORKFLOW_REF,
  ]);
  const [chatSubmitting, setChatSubmitting] = useState(false);
  const [chatSubmitError, setChatSubmitError] = useState<string | null>(null);
  const [approvalPreview, setApprovalPreview] = useState<PendingApproval["preview"]>(undefined);
  const refreshInFlight = useRef<Promise<void> | null>(null);

  useEffect(() => {
    if (onGetSettings && !initialSettings) {
      void onGetSettings()
        .then((loaded) => {
          if (!loaded) return;
          setSettings(loaded);
          if (loaded.defaultWorkflow) {
            setChatWorkflowRef(loaded.defaultWorkflow);
            setWorkflowOptions((prev) =>
              prev.includes(loaded.defaultWorkflow!) ? prev : [...prev, loaded.defaultWorkflow!],
            );
          }
          if (loaded.theme && typeof document !== "undefined") {
            document.documentElement.setAttribute("data-theme", loaded.theme);
          }
        })
        .catch(() => {});
    } else if (initialSettings?.theme && typeof document !== "undefined") {
      document.documentElement.setAttribute("data-theme", initialSettings.theme);
    }
  }, [onGetSettings, initialSettings]);

  const refresh = async () => {
    if (!onControlSummary && !onRunList && !onApprovalList && !onImprovementList) return;
    if (refreshInFlight.current) {
      return refreshInFlight.current;
    }
    setRefreshing(true);
    const inFlight = (async () => {
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
        refreshInFlight.current = null;
      }
    })();
    refreshInFlight.current = inFlight;
    return inFlight;
  };

  const activePollingRunId = useRef<string | null>(null);

  const pollRunProgress = (runId: string, onComplete?: (detail: ControlRunDetail) => void) => {
    activePollingRunId.current = runId;
    const pollInterval = 400;
    const poll = async () => {
      if (activePollingRunId.current !== runId) return;
      try {
        if (onControlRunDetail) {
          const detail = await onControlRunDetail(runId);
          if (activePollingRunId.current === runId) {
            setSelectedRunDetail(detail);
            const status = detail.run?.status;
            if (status && status !== "RUNNING") {
              activePollingRunId.current = null;
              void refresh();
              onComplete?.(detail);
              return;
            }
          }
        }
      } catch {
        // Polling retry
      }
      if (activePollingRunId.current === runId) {
        setTimeout(poll, pollInterval);
      }
    };
    setTimeout(poll, pollInterval);
  };

  useEffect(() => {
    return () => {
      activePollingRunId.current = null;
    };
  }, []);

  const handleRunDetail = async (runId: string) => {
    if (!onControlRunDetail) return;
    const detail = await onControlRunDetail(runId);
    setSelectedRunDetail(detail);
    if (detail.run?.status === "RUNNING" && activePollingRunId.current !== runId) {
      pollRunProgress(runId);
    }
    if (typeof window !== "undefined") {
      setTimeout(() => {
        const el = document.getElementById("selected-run-inspector");
        if (typeof el?.scrollIntoView === "function") {
          el.scrollIntoView({ behavior: "smooth" });
        }
      }, 50);
    }
  };

  const handleStartWorkflow = async (workflowRef: string, input: Record<string, unknown>) => {
    if (!onRunStart && !onTextSubmit) throw new Error("workflow start is not available");
    const result = onRunStart
      ? await onRunStart(workflowRef, input)
      : await onTextSubmit!(typeof input.objective === "string" ? input.objective : "", workflowRef);
    await refresh();
    if (result.run_id) {
      void handleRunDetail(result.run_id).catch(() => undefined);
      if (result.status === "RUNNING") {
        pollRunProgress(result.run_id);
      }
    }
    return { run_id: result.run_id, status: result.status };
  };

  const focusStartWorkflow = (workflowRef?: string | null) => {
    if (workflowRef) setChatWorkflowRef(workflowRef);
  };

  const focusApproval = (_approvalId: string, runId?: string | null) => {
    if (runId) {
      void handleRunDetail(runId).catch(() => undefined);
    } else {
      setView("operate");
    }
  };

  const focusImprovement = (_improvementId: string, runId?: string | null) => {
    if (runId) {
      void handleRunDetail(runId).catch(() => undefined);
    } else {
      setView("operate");
    }
  };

  useEffect(() => {
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!onRegistryList) return;
    void onRegistryList("workflows")
      .then((entries) => {
        const refs = entries.map((entry) => `${entry.name}@${entry.version}`);
        setWorkflowOptions(Array.from(new Set([DEFAULT_CHAT_WORKFLOW_REF, ...refs])).sort());
      })
      .catch(() => undefined);
  }, [onRegistryList]);

  const handleVoicePushToTalkStart = async (voiceSessionId: string, turnId: string) => {
    if (activeAudioRef.current) {
      activeAudioRef.current.pause();
      activeAudioRef.current.currentTime = 0;
      activeAudioRef.current = null;
    }
    if (onVoicePushToTalkStart) {
      return onVoicePushToTalkStart(voiceSessionId, turnId);
    }
    throw new Error("voice push to talk is not available");
  };

  const handleVoiceInterrupt = async (voiceSessionId: string, turnId: string) => {
    if (activeAudioRef.current) {
      activeAudioRef.current.pause();
      activeAudioRef.current.currentTime = 0;
      activeAudioRef.current = null;
    }
    if (onVoiceInterrupt) {
      return onVoiceInterrupt(voiceSessionId, turnId);
    }
    throw new Error("voice interrupt is not available");
  };

  const handleVoiceSubmit = async (
    voiceSessionId: string,
    text: string,
    workflowRef: string | undefined,
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
      );
      if (typeof Audio !== "undefined") {
        if (activeAudioRef.current) {
          activeAudioRef.current.pause();
          activeAudioRef.current = null;
        }
        const audio = new Audio(spoken.response_audio_path);
        activeAudioRef.current = audio;
        audio.onended = () => {
          activeAudioRef.current = null;
          if (onVoiceEvent) {
            void onVoiceEvent(voiceSessionId, "tts.done", {}, turnId).catch(() => undefined);
          }
        };
        void audio.play().catch(() => undefined);
      }
    }
    if (result.run?.run_id) {
      void handleRunDetail(result.run.run_id).catch(() => undefined);
    }
    return result;
  };

  const handleComposerSend = async (text: string) => {
    setChatSubmitError(null);
    if (!onTextSubmit && !onIntentDispatch) {
      setEntries((prev) => [...prev, { id: nextId.current++, speaker: "Operator", text }]);
      return;
    }
    if (!chatWorkflowRef.trim() && !onIntentDispatch) {
      setChatSubmitError("Set a workflow before sending typed chat.");
      return false;
    }
    setChatSubmitting(true);
    try {
      if ((chatWorkflowRef.trim() === DEFAULT_CHAT_WORKFLOW_REF || !chatWorkflowRef.trim()) && onIntentDispatch) {
        const dispatchResult = await onIntentDispatch(text, { async: true });
        const responseText = String(dispatchResult.response_text ?? "");
        const runId = dispatchResult.run_id as string | undefined;
        const status = String(dispatchResult.status ?? "");
        const outcome = dispatchResult.outcome as { next_action?: string } | undefined;
        const nextAction = outcome?.next_action ? ` Next: ${outcome.next_action}` : "";
        const runSuffix = runId && !responseText.includes(runId) ? ` (run ${runId})` : "";
        setEntries((prev) => [
          ...prev,
          { id: nextId.current++, speaker: "Operator", text },
          {
            id: nextId.current++,
            speaker: "AWF",
            text: `${responseText || "Request processed."}${runSuffix}.${nextAction}`,
          },
        ]);
        void refresh();
        if (runId) {
          void handleRunDetail(runId).catch(() => undefined);
          if (status === "RUNNING") {
            pollRunProgress(runId, (finalDetail) => {
              const runOutcome = finalDetail.outcome;
              const completedText =
                runOutcome?.response_text ??
                `Workflow ${finalDetail.run?.workflow_ref ?? runId} finished with status ${finalDetail.run?.status}.`;
              const next = runOutcome?.next_action ? ` Next: ${runOutcome.next_action}` : "";
              setEntries((prev) => [
                ...prev,
                {
                  id: nextId.current++,
                  speaker: "AWF",
                  text: `${completedText}${next}`,
                },
              ]);
            });
          }
        }
        return;
      }
      if (!onTextSubmit) {
        setChatSubmitError("Text submit handler is not available.");
        return false;
      }
      const result = await onTextSubmit(text, chatWorkflowRef.trim());
      const responseText =
        result.outputs?.response_text ??
        result.reason ??
        result.error ??
        `Workflow ${chatWorkflowRef.trim()} finished with status ${result.status}.`;
      const outcome = result.outcome as { next_action?: string } | undefined;
      const nextAction = outcome?.next_action ? ` Next: ${outcome.next_action}` : "";
      setEntries((prev) => [
        ...prev,
        { id: nextId.current++, speaker: "Operator", text },
        {
          id: nextId.current++,
          speaker: "AWF",
          text: `${responseText} (run ${result.run_id}).${nextAction}`,
        },
      ]);
      void refresh();
      if (result.run_id) {
        void handleRunDetail(result.run_id).catch(() => undefined);
        if (result.status === "RUNNING") {
          pollRunProgress(result.run_id, (finalDetail) => {
            const runOutcome = finalDetail.outcome;
            const completedText =
              runOutcome?.response_text ??
              `Workflow ${finalDetail.run?.workflow_ref ?? result.run_id} finished with status ${finalDetail.run?.status}.`;
            const next = runOutcome?.next_action ? ` Next: ${runOutcome.next_action}` : "";
            setEntries((prev) => [
              ...prev,
              {
                id: nextId.current++,
                speaker: "AWF",
                text: `${completedText}${next}`,
              },
            ]);
          });
        }
      }
    } catch (err) {
      setChatSubmitError((err as Error).message);
      return false;
    } finally {
      setChatSubmitting(false);
    }
  };
  const handleApprove = async (approvalId: string) => {
    onApprove(approvalId);
    await refresh();
  };

  const handleReject = async (approvalId: string, reason: string) => {
    onReject(approvalId, reason);
    await refresh();
  };

  // An explicit `pendingApproval` prop wins (a caller with its own source
  // of truth); otherwise the first real pending approval from the fetched
  // list is what the operator actually sees and can act on.
  const effectivePendingApproval = pendingApproval ?? (approvals.length > 0 ? toPendingApproval(approvals[0]) : undefined);

  useEffect(() => {
    setApprovalPreview(undefined);
    if (!effectivePendingApproval || effectivePendingApproval.preview || !onApprovalDetail) return;
    void onApprovalDetail(effectivePendingApproval.approvalId)
      .then((detail) => setApprovalPreview(detail.preview ?? null))
      .catch(() => setApprovalPreview(null));
  }, [effectivePendingApproval?.approvalId, effectivePendingApproval?.preview, onApprovalDetail]);

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

  const operateBadge =
    (controlSummary?.operator_work_items?.length ?? 0) || approvals.length + improvements.length || undefined;
  const views: { name: ViewName; label: string; badge?: number; icon: React.FC<IconProps> }[] = [
    ...(statusAvailable
      ? [{ name: "operate" as const, label: "Operate", icon: SparkleIcon, badge: operateBadge }]
      : []),
    { name: "chat" as const, label: "Chat", icon: ChatIcon },
    ...(registryAvailable || memoryAvailable
      ? [{ name: "library" as const, label: "Library", icon: DatabaseIcon }]
      : []),
  ];
  const activeView = view && views.some((v) => v.name === view) ? view : views[0]?.name;

  const readinessEntries = controlSummary ? Object.values(controlSummary.readiness.readiness) : [];
  const readinessOverall =
    readinessEntries.length > 0 && readinessEntries.every((entry) => entry.ready) ? "ready" : "not ready";
  const llmState = controlSummary?.llm.status?.state ?? "idle";

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const isMac = typeof navigator !== "undefined" && /mac/i.test(navigator.platform);
      const mod = isMac ? e.metaKey : e.ctrlKey;

      if (mod && (e.key === "1" || e.key === "2" || e.key === "3")) {
        e.preventDefault();
        if (e.key === "1" && statusAvailable) setView("operate");
        else if (e.key === "2") setView("chat");
        else if (e.key === "3" && (registryAvailable || memoryAvailable)) setView("library");
        return;
      }

      if (mod && (e.key === "k" || e.key === "K")) {
        e.preventDefault();
        const active = view ?? "operate";
        if (active === "chat") {
          const composer = document.querySelector<HTMLInputElement>(".composer-input");
          composer?.focus();
        } else if (active === "library") {
          const search = document.querySelector<HTMLInputElement>("input[type='search'], .memory-search input");
          search?.focus();
        } else {
          const startWork = document.querySelector<HTMLInputElement>(".start-work-panel input");
          startWork?.focus();
        }
        return;
      }

      if (e.key === "Escape") {
        if (selectedRunDetail) {
          e.preventDefault();
          setSelectedRunDetail(null);
        }
        return;
      }

      if (mod && e.key === "Enter") {
        if (effectivePendingApproval) {
          e.preventDefault();
          void handleApprove(effectivePendingApproval.approvalId);
        }
        return;
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [view, selectedRunDetail, effectivePendingApproval, statusAvailable, registryAvailable, memoryAvailable]);

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
            {views.map((v, idx) => (
              <li key={v.name}>
                <button
                  type="button"
                  className="btn nav-item"
                  aria-label={v.label}
                  aria-current={v.name === activeView ? "page" : undefined}
                  onClick={() => setView(v.name)}
                >
                  {v.icon && <v.icon size={13} className="nav-icon" />}
                  {v.label}
                  <span className="kbd-hint">Ctrl+{idx + 1}</span>
                  {v.badge !== undefined && <span className="rail-badge">{v.badge}</span>}
                </button>
              </li>
            ))}
          </ul>
        </nav>
        <div className="status-bar" role="status" aria-label="Status">
          <span className="mono">{controlSummary?.readiness.profile_id ?? "no profile"}</span>
          <button
            type="button"
            className={`chip chip-btn ${stateClass(readinessOverall)}`}
            onClick={() => {
              setView("operate");
              if (typeof window !== "undefined") {
                setTimeout(() => {
                  const el = document.querySelector(".overview, [aria-label='System readiness']");
                  if (typeof el?.scrollIntoView === "function") {
                    el.scrollIntoView({ behavior: "smooth" });
                  }
                }, 50);
              }
            }}
            title="Inspect system readiness"
            aria-label={`Readiness: ${readinessOverall}`}
          >
            {readinessOverall}
          </button>
          <span className={`chip ${stateClass(llmState)}`}>{llmState}</span>
          <button
            type="button"
            className="chip chip-btn"
            onClick={() => {
              setView("operate");
              if (typeof window !== "undefined") {
                setTimeout(() => {
                  const el = document.querySelector("[aria-label='Approvals']");
                  if (typeof el?.scrollIntoView === "function") {
                    el.scrollIntoView({ behavior: "smooth" });
                  }
                }, 50);
              }
            }}
            title="Jump to pending approvals"
            aria-label={`${approvals.length} pending approvals`}
          >
            {approvals.length} pending approval{approvals.length === 1 ? "" : "s"}
          </button>
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
                  workflowRef={chatWorkflowRef}
                  workflowOptions={workflowOptions}
                  onWorkflowRefChange={setChatWorkflowRef}
                  submitting={chatSubmitting}
                  submitError={chatSubmitError}
                  onSend={handleComposerSend}
                  onMic={voiceAvailable ? () => voiceRef.current?.togglePushToTalk() : undefined}
                  onRunSelect={(runId) => {
                    setView("operate");
                    if (onControlRunDetail) {
                      void handleRunDetail(runId);
                    }
                  }}
                />
                {voiceAvailable && (
                  <VoiceActivation
                    ref={voiceRef}
                    defaultWorkflowRef={chatWorkflowRef || DEFAULT_CHAT_WORKFLOW_REF}
                    workflowOptions={workflowOptions}
                    onSessionStart={onVoiceSessionStart!}
                    onPushToTalkStart={handleVoicePushToTalkStart}
                    onPushToTalkStop={onVoicePushToTalkStop!}
                    onInterrupt={handleVoiceInterrupt}
                    onVoiceEvent={onVoiceEvent}
                    onSubmitText={handleVoiceSubmit}
                  />
                )}
              </div>
            </div>
          )}
          {activeView === "operate" && statusAvailable && (
            <>
              <div className="view-header">
                <div>
                  <div className="view-kicker">
                    <SparkleIcon size={12} />
                    Resident Mind
                  </div>
                  <h1 className="view-title">Operate</h1>
                </div>
                <div className="view-actions">
                  <button type="button" className="btn btn-secondary" onClick={() => setView("chat")}>
                    Jump to Chat
                  </button>
                </div>
              </div>
              <OperatorWorkQueue
                items={controlSummary?.operator_work_items ?? []}
                onRunDetail={onControlRunDetail ? (runId: string) => void handleRunDetail(runId) : undefined}
                onApprovalReview={focusApproval}
                onImprovementReview={focusImprovement}
                onDoctor={() => void refresh()}
                onLlmModels={onLlmModels ? () => void onLlmModels() : undefined}
                onStartWorkflow={focusStartWorkflow}
              />
              <StartWorkPanel
                options={controlSummary?.operator_start_options ?? []}
                workflowOptions={workflowOptions}
                selectedWorkflowRef={controlSummary?.operator_start_options?.[0]?.workflow_ref ?? chatWorkflowRef}
                onWorkflowRefChange={setChatWorkflowRef}
                onStart={onRunStart || onTextSubmit ? handleStartWorkflow : undefined}
              />
              {selectedRunDetail && (
                <>
                  <RunTimeline
                    detail={selectedRunDetail}
                    onClose={() => setSelectedRunDetail(null)}
                    onApprove={handleApprove}
                    onReject={handleReject}
                    onImprovementRequestMerge={onImprovementRequestMerge}
                    onImprovementMerge={onImprovementMerge}
                    onImprovementReject={onImprovementReject}
                  />
                  <EvidencePanel
                    artifacts={selectedRunDetail.artifacts}
                    verdicts={selectedRunDetail.verdicts}
                    onArtifactRead={onArtifactRead}
                  />
                </>
              )}
              {approvalsAvailable && (
                <ApprovalsView approvals={approvals} onApprove={handleApprove} onReject={handleReject} />
              )}
              {proposalsAvailable && (
                <>
                  {onProposalGet && onProposalPublish && onProposalReject && (
                    <ProposalReview
                      onProposalGet={onProposalGet}
                      onProposalPublish={onProposalPublish}
                      onProposalReject={onProposalReject}
                    />
                  )}
                  <ImprovementProposals
                    improvements={improvements}
                    onArtifactRead={onArtifactRead}
                    onRequestMerge={onImprovementRequestMerge}
                    onMerge={onImprovementMerge}
                    onReject={onImprovementReject}
                  />
                </>
              )}
              {runsAvailable && (
                <RunsView
                  runs={runs}
                  selectedRunDetail={null}
                  onRunDetail={onControlRunDetail ? (runId: string) => void handleRunDetail(runId) : undefined}
                  onArtifactRead={onArtifactRead}
                  onApprove={handleApprove}
                  onReject={handleReject}
                  onImprovementRequestMerge={onImprovementRequestMerge}
                  onImprovementMerge={onImprovementMerge}
                  onImprovementReject={onImprovementReject}
                />
              )}
              <Overview controlSummary={controlSummary} onLlmModels={onLlmModels} />
            </>
          )}
          {activeView === "library" && (
            <>
              <div className="view-header">
                <div>
                  <div className="view-kicker">
                    <DatabaseIcon size={12} />
                    Registry & Memory Fabric
                  </div>
                  <h1 className="view-title">Library</h1>
                </div>
                <div className="view-actions">
                  <button type="button" className="btn btn-secondary" onClick={() => setView("operate")}>
                    View Operations
                  </button>
                </div>
              </div>
              {registryAvailable &&
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
                    onWorkflowRun={(workflowRef) => {
                      setChatWorkflowRef(workflowRef);
                      setView("operate");
                    }}
                  />
                )}
              {memoryAvailable && onMemorySearch && onMemoryBlock && onMemoryPublish && onMemoryReject && (
                <MemoryPanel
                  onMemorySearch={onMemorySearch}
                  onMemoryBlock={onMemoryBlock}
                  onMemoryPublish={onMemoryPublish}
                  onMemoryReject={onMemoryReject}
                />
              )}
            </>
          )}

      </main>
      {effectivePendingApproval && (
        <ApprovalConfirmation
          approvalId={effectivePendingApproval.approvalId}
          actionDigest={effectivePendingApproval.actionDigest}
          riskClass={effectivePendingApproval.riskClass}
          preview={effectivePendingApproval.preview ?? approvalPreview}
          voiceConfirmed={voiceConfirmed}
          onApprove={handleApprove}
          onReject={handleReject}
        />
      )}
    </div>
  );
}
