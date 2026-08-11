import { contextBridge, ipcRenderer } from "electron";
import { CHANNELS } from "../main/ipc.js";
import { VOICE_CHANNEL, VOICE_SESSION_CHANNELS } from "../main/voicePipeline.js";

/** The only surface the renderer can reach - no direct Node/Electron
 * access, matching contextIsolation. Every call is one of the narrow IPC
 * channels registered in `main/ipc.ts`/`main/voicePipeline.ts`, which
 * themselves only call the same ProtocolClient methods the CLI uses, or
 * spawn the same `awf-speech` subprocess described there. */
contextBridge.exposeInMainWorld("awf", {
  runStart: (workflowRef: string, input: Record<string, unknown> = {}) =>
    ipcRenderer.invoke(CHANNELS.runStart, workflowRef, input),
  controlSummary: () => ipcRenderer.invoke(CHANNELS.controlSummary),
  controlRunDetail: (runId: string) => ipcRenderer.invoke(CHANNELS.controlRunDetail, runId),
  systemReadiness: () => ipcRenderer.invoke(CHANNELS.systemReadiness),
  llmServers: () => ipcRenderer.invoke(CHANNELS.llmServers),
  llmModels: () => ipcRenderer.invoke(CHANNELS.llmModels),
  llmServeStatus: () => ipcRenderer.invoke(CHANNELS.llmServeStatus),
  registryValidate: (path: string, kind?: string) => ipcRenderer.invoke(CHANNELS.registryValidate, path, kind),
  registryPublish: (path: string, kind: string) => ipcRenderer.invoke(CHANNELS.registryPublish, path, kind),
  registryReindex: () => ipcRenderer.invoke(CHANNELS.registryReindex),
  registryRetire: (kind: string, name: string, version: string) =>
    ipcRenderer.invoke(CHANNELS.registryRetire, kind, name, version),
  registryTrust: (kind: string, name: string, version: string, status: string) =>
    ipcRenderer.invoke(CHANNELS.registryTrust, kind, name, version, status),
  registryList: (kind: string) => ipcRenderer.invoke(CHANNELS.registryList, kind),
  registryGet: (kind: string, name: string, version: string) =>
    ipcRenderer.invoke(CHANNELS.registryGet, kind, name, version),
  artifactList: (runId: string) => ipcRenderer.invoke(CHANNELS.artifactList, runId),
  artifactRead: (artifactId: string) => ipcRenderer.invoke(CHANNELS.artifactRead, artifactId),
  runStatus: (runId: string) => ipcRenderer.invoke(CHANNELS.runStatus, runId),
  runList: () => ipcRenderer.invoke(CHANNELS.runList),
  approvalList: () => ipcRenderer.invoke(CHANNELS.approvalList),
  approvalDetail: (approvalId: string) => ipcRenderer.invoke(CHANNELS.approvalDetail, approvalId),
  approvalApprove: (approvalId: string) => ipcRenderer.invoke(CHANNELS.approvalApprove, approvalId),
  approvalReject: (approvalId: string, reason: string) =>
    ipcRenderer.invoke(CHANNELS.approvalReject, approvalId, reason),
  proposalGet: (proposalId: string) => ipcRenderer.invoke(CHANNELS.proposalGet, proposalId),
  proposalPublish: (proposalId: string, digest: string) =>
    ipcRenderer.invoke(CHANNELS.proposalPublish, proposalId, digest),
  proposalReject: (proposalId: string, reason?: string) =>
    ipcRenderer.invoke(CHANNELS.proposalReject, proposalId, reason),
  improvementList: () => ipcRenderer.invoke(CHANNELS.improvementList),
  improvementGet: (improvementId: string) => ipcRenderer.invoke(CHANNELS.improvementGet, improvementId),
  improvementRequestMerge: (improvementId: string) =>
    ipcRenderer.invoke(CHANNELS.improvementRequestMerge, improvementId),
  improvementMerge: (improvementId: string, approvalId: string) =>
    ipcRenderer.invoke(CHANNELS.improvementMerge, improvementId, approvalId),
  improvementReject: (improvementId: string, reason?: string) =>
    ipcRenderer.invoke(CHANNELS.improvementReject, improvementId, reason),
  memorySearch: (query: string, profile?: string) => ipcRenderer.invoke(CHANNELS.memorySearch, query, profile),
  memoryGet: (ref: string) => ipcRenderer.invoke(CHANNELS.memoryGet, ref),
  memoryPropose: (path: string, summary?: string) => ipcRenderer.invoke(CHANNELS.memoryPropose, path, summary),
  memoryPublish: (proposalId: string, digest: string) =>
    ipcRenderer.invoke(CHANNELS.memoryPublish, proposalId, digest),
  memoryReject: (proposalId: string, reason?: string) =>
    ipcRenderer.invoke(CHANNELS.memoryReject, proposalId, reason),
  memoryBlock: (ref: string) => ipcRenderer.invoke(CHANNELS.memoryBlock, ref),
  voiceRoundTrip: (
    wakeAudioPath: string,
    commandAudioPath: string,
    voiceId: string,
    responseAudioOutPath: string,
  ) => ipcRenderer.invoke(VOICE_CHANNEL, wakeAudioPath, commandAudioPath, voiceId, responseAudioOutPath),
  voiceSessionStart: (title?: string, wakeEnabled = false) =>
    ipcRenderer.invoke(VOICE_SESSION_CHANNELS.start, title, wakeEnabled),
  voiceSessionStop: (voiceSessionId: string, reason?: string) =>
    ipcRenderer.invoke(VOICE_SESSION_CHANNELS.stop, voiceSessionId, reason),
  voicePushToTalkStart: (voiceSessionId: string, turnId?: string) =>
    ipcRenderer.invoke(VOICE_SESSION_CHANNELS.pushToTalkStart, voiceSessionId, turnId),
  voicePushToTalkStop: (voiceSessionId: string, turnId?: string) =>
    ipcRenderer.invoke(VOICE_SESSION_CHANNELS.pushToTalkStop, voiceSessionId, turnId),
  voiceInterrupt: (voiceSessionId: string, turnId?: string) =>
    ipcRenderer.invoke(VOICE_SESSION_CHANNELS.interrupt, voiceSessionId, turnId),
  voiceSubmitText: (
    voiceSessionId: string,
    text: string,
    workflowRef: string,
    voiceProfileRef?: string,
    turnId?: string,
  ) => ipcRenderer.invoke(VOICE_SESSION_CHANNELS.submitText, voiceSessionId, text, workflowRef, voiceProfileRef, turnId),
  voiceSpeakText: (text: string, voiceId: string | undefined, responseAudioOutPath?: string) =>
    ipcRenderer.invoke(VOICE_SESSION_CHANNELS.speakText, text, voiceId, responseAudioOutPath),
});
