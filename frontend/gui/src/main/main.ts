import { ChildProcessTransport, ProtocolClient } from "@awf/protocol-client";
import { app, BrowserWindow, ipcMain } from "electron";
import path from "node:path";
import { registerIpcHandlers } from "./ipc.js";
import { registerVoiceIpcHandler } from "./voicePipeline.js";

function createClient(repoRoot: string): ProtocolClient {
  const transport = new ChildProcessTransport({
    command: process.env.AWF_CORE_COMMAND ?? "awf",
    cwd: repoRoot,
  });
  return new ProtocolClient(transport);
}

function createWindow(client: ProtocolClient, repoRoot: string): void {
  const win = new BrowserWindow({
    width: 1000,
    height: 700,
    webPreferences: {
      preload: path.join(import.meta.dirname, "..", "preload", "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  registerIpcHandlers(ipcMain, client);
  registerVoiceIpcHandler(ipcMain, {
    command: process.env.AWF_SPEECH_COMMAND ?? "awf-speech",
    cwd: repoRoot,
  });
  void win.loadFile(path.join(import.meta.dirname, "..", "renderer", "index.html"));
}

app.whenReady().then(() => {
  const repoRoot = process.env.AWF_REPO_ROOT ?? process.cwd();
  const client = createClient(repoRoot);
  createWindow(client, repoRoot);

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow(client, repoRoot);
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});
