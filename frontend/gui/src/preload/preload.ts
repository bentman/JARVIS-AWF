import { contextBridge, ipcRenderer } from "electron";
import { CHANNELS } from "../main/ipc.js";
import { VOICE_CHANNEL } from "../main/voicePipeline.js";

/** The only surface the renderer can reach - no direct Node/Electron
 * access, matching contextIsolation. Every call is one of the narrow IPC
 * channels registered in `main/ipc.ts`/`main/voicePipeline.ts`, which
 * themselves only call the same ProtocolClient methods the CLI uses, or
 * spawn the same `awf-speech` subprocess described there. */
contextBridge.exposeInMainWorld("awf", {
  runStatus: (runId: string) => ipcRenderer.invoke(CHANNELS.runStatus, runId),
  runList: () => ipcRenderer.invoke(CHANNELS.runList),
  approvalList: () => ipcRenderer.invoke(CHANNELS.approvalList),
  approvalApprove: (approvalId: string) => ipcRenderer.invoke(CHANNELS.approvalApprove, approvalId),
  approvalReject: (approvalId: string, reason: string) =>
    ipcRenderer.invoke(CHANNELS.approvalReject, approvalId, reason),
  proposalGet: (proposalId: string) => ipcRenderer.invoke(CHANNELS.proposalGet, proposalId),
  proposalPublish: (proposalId: string, digest: string) =>
    ipcRenderer.invoke(CHANNELS.proposalPublish, proposalId, digest),
  proposalReject: (proposalId: string, reason?: string) =>
    ipcRenderer.invoke(CHANNELS.proposalReject, proposalId, reason),
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
});
