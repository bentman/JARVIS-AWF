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
  approvalApprove: "awf:approvalApprove",
  approvalReject: "awf:approvalReject",
} as const;

/** Registers IPC handlers that delegate to the same ProtocolClient the CLI
 * uses (Section 16.3: "the protocol adds no authority"). The renderer never
 * gets direct access to the client or to Node - only these narrow, typed
 * channels via the preload's contextBridge. */
export function registerIpcHandlers(ipcMain: IpcMainLike, client: ProtocolClient): void {
  ipcMain.handle(CHANNELS.runStatus, (_event, runId) => client.runStatus(runId as string));
  ipcMain.handle(CHANNELS.runList, () => client.runList());
  ipcMain.handle(CHANNELS.approvalList, () => client.approvalList());
  ipcMain.handle(CHANNELS.approvalApprove, (_event, approvalId) =>
    client.approvalApprove(approvalId as string),
  );
  ipcMain.handle(CHANNELS.approvalReject, (_event, approvalId, reason) =>
    client.approvalReject(approvalId as string, reason as string),
  );
}
