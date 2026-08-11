import { ChildProcessTransport, ProtocolClient } from "@awf/protocol-client";
import { app, BrowserWindow, ipcMain } from "electron";
import { existsSync } from "node:fs";
import path from "node:path";
import { registerIpcHandlers } from "./ipc.js";
import { registerVoiceIpcHandler, registerVoiceSessionIpcHandlers, registerVoiceSpeakIpcHandler } from "./voicePipeline.js";

/**
 * Resolves a backend console-script name to its `backend/.venv` path when
 * present, so the GUI works without the operator activating the venv or
 * adding it to PATH (per docs/QuickStart-*.md, the venv is never installed
 * into a system interpreter). Falls back to the bare name for PATH lookup.
 */
function resolveBackendCommand(repoRoot: string, name: string): string {
  const venvBin = path.join(repoRoot, "backend", ".venv", process.platform === "win32" ? "Scripts" : "bin");
  const candidate = path.join(venvBin, process.platform === "win32" ? `${name}.exe` : name);
  return existsSync(candidate) ? candidate : name;
}

function createClient(repoRoot: string): ProtocolClient {
  const transport = new ChildProcessTransport({
    command: process.env.AWF_CORE_COMMAND ?? resolveBackendCommand(repoRoot, "awf"),
    cwd: repoRoot,
  });
  return new ProtocolClient(transport);
}

function createWindow(client: ProtocolClient, repoRoot: string): void {
  const win = new BrowserWindow({
    width: 1360,
    height: 820,
    minWidth: 1180,
    minHeight: 640,
    backgroundColor: "#070b12",
    webPreferences: {
      preload: path.join(import.meta.dirname, "..", "preload", "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  const speechCommand = process.env.AWF_SPEECH_COMMAND ?? resolveBackendCommand(repoRoot, "awf-speech");

  registerIpcHandlers(ipcMain, client);
  registerVoiceIpcHandler(ipcMain, {
    command: speechCommand,
    cwd: repoRoot,
  });
  registerVoiceSessionIpcHandlers(ipcMain, client);
  registerVoiceSpeakIpcHandler(ipcMain, {
    command: speechCommand,
    cwd: repoRoot,
  });
  void win.loadFile(path.join(import.meta.dirname, "..", "renderer", "index.html"));
}

// dist/main/main.js -> dist/main -> dist -> gui -> frontend -> repo root.
// npm workspace scripts run with cwd set to the workspace package dir
// (frontend/gui), not the repo root, so process.cwd() cannot be trusted here.
const DEFAULT_REPO_ROOT = path.join(import.meta.dirname, "..", "..", "..", "..");

app.whenReady().then(() => {
  const repoRoot = process.env.AWF_REPO_ROOT ?? DEFAULT_REPO_ROOT;
  const client = createClient(repoRoot);
  createWindow(client, repoRoot);

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow(client, repoRoot);
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});
