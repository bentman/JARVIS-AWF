import type { ProtocolClient } from "@awf/protocol-client";

/** Minimal shape of Electron's `ipcMain` this module needs - kept narrow so
 * the IPC wiring is testable without launching a real Electron process. */
export interface IpcMainLike {
  handle(channel: string, listener: (event: unknown, ...args: unknown[]) => unknown): void;
}

export const CHANNELS = {
  runStatus: "awf:runStatus",
  runList: "awf:runList",
  approvalList: "awf:approvalList",
  approvalDetail: "awf:approvalDetail",
  approvalApprove: "awf:approvalApprove",
  approvalReject: "awf:approvalReject",
  proposalGet: "awf:proposalGet",
  proposalPublish: "awf:proposalPublish",
  proposalReject: "awf:proposalReject",
  memorySearch: "awf:memorySearch",
  memoryGet: "awf:memoryGet",
  memoryPropose: "awf:memoryPropose",
  memoryPublish: "awf:memoryPublish",
  memoryReject: "awf:memoryReject",
  memoryBlock: "awf:memoryBlock",
} as const;

/** Registers IPC handlers that delegate to the same ProtocolClient the CLI
 * uses (Section 16.3: "the protocol adds no authority"). The renderer never
 * gets direct access to the client or to Node - only these narrow, typed
 * channels via the preload's contextBridge. */
export function registerIpcHandlers(ipcMain: IpcMainLike, client: ProtocolClient): void {
  ipcMain.handle(CHANNELS.runStatus, (_event, runId) => client.runStatus(runId as string));
  ipcMain.handle(CHANNELS.runList, () => client.runList());
  ipcMain.handle(CHANNELS.approvalList, () => client.approvalList());
  ipcMain.handle(CHANNELS.approvalDetail, (_event, approvalId) => client.approvalDetail(approvalId as string));
  ipcMain.handle(CHANNELS.approvalApprove, (_event, approvalId) =>
    client.approvalApprove(approvalId as string),
  );
  ipcMain.handle(CHANNELS.approvalReject, (_event, approvalId, reason) =>
    client.approvalReject(approvalId as string, reason as string),
  );
  ipcMain.handle(CHANNELS.proposalGet, (_event, proposalId) => client.proposalGet(proposalId as string));
  ipcMain.handle(CHANNELS.proposalPublish, (_event, proposalId, digest) =>
    client.proposalPublish(proposalId as string, digest as string),
  );
  ipcMain.handle(CHANNELS.proposalReject, (_event, proposalId, reason) =>
    client.proposalReject(proposalId as string, reason as string | undefined),
  );
  ipcMain.handle(CHANNELS.memorySearch, (_event, query, profile) =>
    client.memorySearch(query as string, (profile as string | undefined) ?? "default@1.0.0"),
  );
  ipcMain.handle(CHANNELS.memoryGet, (_event, ref) => client.memoryGet(ref as string));
  ipcMain.handle(CHANNELS.memoryPropose, (_event, path, summary) =>
    client.memoryPropose(path as string, summary as string | undefined),
  );
  ipcMain.handle(CHANNELS.memoryPublish, (_event, proposalId, digest) =>
    client.memoryPublish(proposalId as string, digest as string),
  );
  ipcMain.handle(CHANNELS.memoryReject, (_event, proposalId, reason) =>
    client.memoryReject(proposalId as string, reason as string | undefined),
  );
  ipcMain.handle(CHANNELS.memoryBlock, (_event, ref) => client.memoryBlock(ref as string));
}
