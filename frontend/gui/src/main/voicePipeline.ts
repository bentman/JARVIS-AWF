import { spawn } from "node:child_process";
import type { IpcMainLike } from "./ipc.js";

export const VOICE_CHANNEL = "awf:voiceRoundTrip";

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
      const lastLine = stdout.trim().split("\n").filter(Boolean).pop() ?? "";
      let parsed: (VoiceRoundTripResult & { error?: undefined }) | { error: string };
      try {
        parsed = JSON.parse(lastLine);
      } catch {
        reject(new Error(`voice pipeline produced no valid JSON (exit ${code}): ${stderr || stdout}`));
        return;
      }
      if (parsed.error) {
        reject(new Error(parsed.error));
        return;
      }
      resolve(parsed as VoiceRoundTripResult);
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
