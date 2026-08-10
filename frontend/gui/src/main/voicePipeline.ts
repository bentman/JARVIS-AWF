import { spawn } from "node:child_process";
import type { ProtocolClient } from "@awf/protocol-client";
import type { IpcMainLike } from "./ipc.js";

export const VOICE_CHANNEL = "awf:voiceRoundTrip";
export const VOICE_SESSION_CHANNELS = {
  start: "awf:voiceSessionStart",
  stop: "awf:voiceSessionStop",
  pushToTalkStart: "awf:voicePushToTalkStart",
  pushToTalkStop: "awf:voicePushToTalkStop",
  interrupt: "awf:voiceInterrupt",
  submitText: "awf:voiceSubmitText",
  speakText: "awf:voiceSpeakText",
} as const;

export interface VoiceRoundTripResult {
  wake_detected: boolean;
  wake_score: number;
  speech_segments: [number, number][];
  command_text: string;
  command_language: string;
  response_text: string;
  response_audio_path: string;
}

export interface RunVoiceRoundTripOptions {
  /** Path to the `awf-speech` executable; defaults to resolving via PATH. */
  command?: string;
  cwd: string;
  wakeAudioPath: string;
  commandAudioPath: string;
  voiceId?: string;
  responseAudioOutPath: string;
}

export interface VoiceSpeakTextResult {
  response_text: string;
  voice_id: string;
  response_audio_path: string;
}

export interface RunVoiceSpeakTextOptions {
  command?: string;
  cwd: string;
  text: string;
  voiceId?: string;
  responseAudioOutPath: string;
}

function parseLastJsonLine<T>(stdout: string, stderr: string, code: number | null): T {
  const lastLine = stdout.trim().split("\n").filter(Boolean).pop() ?? "";
  try {
    return JSON.parse(lastLine) as T;
  } catch {
    throw new Error(`voice pipeline produced no valid JSON (exit ${code}): ${stderr || stdout}`);
  }
}

/** Spawns the real Python voice pipeline (`backend/src/awf/speech/cli.py`,
 * via the `awf-speech` console script) as a subprocess - the same pattern
 * already used to spawn `awf serve --stdio` (Section 16.3).
 *
 * This is push-to-talk-by-file: the caller supplies a pre-recorded
 * wake-word audio file and a pre-recorded command audio file, rather than a
 * live microphone stream. Live `getUserMedia` capture is a renderer-side
 * concern separate from this module.
 */
export function runVoiceRoundTrip(options: RunVoiceRoundTripOptions): Promise<VoiceRoundTripResult> {
  return new Promise((resolve, reject) => {
    const args = [
      "round-trip",
      options.wakeAudioPath,
      options.commandAudioPath,
      ...(options.voiceId ? ["--voice-id", options.voiceId] : []),
      "--response-audio-out",
      options.responseAudioOutPath,
    ];
    const child = spawn(options.command ?? "awf-speech", args, { cwd: options.cwd });

    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk: Buffer) => {
      stdout += chunk.toString();
    });
    child.stderr.on("data", (chunk: Buffer) => {
      stderr += chunk.toString();
    });

    child.on("error", (err) => reject(err));

    child.on("close", (code) => {
      try {
        const parsed = parseLastJsonLine<(VoiceRoundTripResult & { error?: undefined }) | { error: string }>(
          stdout,
          stderr,
          code,
        );
        if (parsed.error) {
          reject(new Error(parsed.error));
          return;
        }
        resolve(parsed as VoiceRoundTripResult);
      } catch (err) {
        reject(err);
        return;
      }
    });
  });
}

export function runVoiceSpeakText(options: RunVoiceSpeakTextOptions): Promise<VoiceSpeakTextResult> {
  return new Promise((resolve, reject) => {
    const args = [
      "synthesize",
      options.text,
      ...(options.voiceId ? ["--voice-id", options.voiceId] : []),
      "--response-audio-out",
      options.responseAudioOutPath,
    ];
    const child = spawn(options.command ?? "awf-speech", args, { cwd: options.cwd });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk: Buffer) => {
      stdout += chunk.toString();
    });
    child.stderr.on("data", (chunk: Buffer) => {
      stderr += chunk.toString();
    });
    child.on("error", (err) => reject(err));
    child.on("close", (code) => {
      try {
        resolve(parseLastJsonLine<VoiceSpeakTextResult>(stdout, stderr, code));
      } catch (err) {
        reject(err);
      }
    });
  });
}

export function registerVoiceIpcHandler(
  ipcMain: IpcMainLike,
  defaults: Pick<RunVoiceRoundTripOptions, "command" | "cwd">,
): void {
  ipcMain.handle(VOICE_CHANNEL, (_event, wakeAudioPath, commandAudioPath, voiceId, responseAudioOutPath) =>
    runVoiceRoundTrip({
      ...defaults,
      wakeAudioPath: wakeAudioPath as string,
      commandAudioPath: commandAudioPath as string,
      voiceId: voiceId as string | undefined,
      responseAudioOutPath: responseAudioOutPath as string,
    }),
  );
}

export function registerVoiceSessionIpcHandlers(ipcMain: IpcMainLike, client: ProtocolClient): void {
  ipcMain.handle(VOICE_SESSION_CHANNELS.start, (_event, title, wakeEnabled) =>
    client.voiceSessionStart(title as string | undefined, Boolean(wakeEnabled)),
  );
  ipcMain.handle(VOICE_SESSION_CHANNELS.stop, (_event, voiceSessionId, reason) =>
    client.voiceSessionClose(voiceSessionId as string, reason as string | undefined),
  );
  ipcMain.handle(VOICE_SESSION_CHANNELS.pushToTalkStart, (_event, voiceSessionId, turnId) =>
    client.voiceEvent(voiceSessionId as string, "vad.speech_started", {}, turnId as string | undefined),
  );
  ipcMain.handle(VOICE_SESSION_CHANNELS.pushToTalkStop, (_event, voiceSessionId, turnId) =>
    client.voiceEvent(voiceSessionId as string, "vad.speech_stopped", {}, turnId as string | undefined),
  );
  ipcMain.handle(VOICE_SESSION_CHANNELS.interrupt, (_event, voiceSessionId, turnId) =>
    client.voiceEvent(voiceSessionId as string, "interruption", {}, turnId as string | undefined),
  );
  ipcMain.handle(VOICE_SESSION_CHANNELS.submitText, (_event, voiceSessionId, text, workflowRef, voiceProfileRef, turnId) =>
    client.voiceSubmitText({
      voiceSessionId: voiceSessionId as string,
      text: text as string,
      workflowRef: workflowRef as string,
      voiceProfileRef: voiceProfileRef as string | undefined,
      turnId: turnId as string | undefined,
    }),
  );
}

export function registerVoiceSpeakIpcHandler(
  ipcMain: IpcMainLike,
  defaults: Pick<RunVoiceSpeakTextOptions, "command" | "cwd">,
): void {
  ipcMain.handle(VOICE_SESSION_CHANNELS.speakText, (_event, text, voiceId, responseAudioOutPath) =>
    runVoiceSpeakText({
      ...defaults,
      text: text as string,
      voiceId: voiceId as string | undefined,
      responseAudioOutPath: responseAudioOutPath as string,
    }),
  );
}
