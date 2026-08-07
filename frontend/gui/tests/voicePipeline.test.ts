import { EventEmitter } from "node:events";
import { beforeEach, describe, expect, it, vi } from "vitest";

const spawnMock = vi.fn();
vi.mock("node:child_process", () => {
  const mod = { spawn: (...args: unknown[]) => spawnMock(...args) };
  return { ...mod, default: mod };
});

function makeFakeChild() {
  const child = new EventEmitter() as EventEmitter & { stdout: EventEmitter; stderr: EventEmitter };
  child.stdout = new EventEmitter();
  child.stderr = new EventEmitter();
  return child;
}

describe("runVoiceRoundTrip", () => {
  beforeEach(() => {
    spawnMock.mockReset();
  });

  it("spawns awf-speech round-trip with the expected arguments", async () => {
    const { runVoiceRoundTrip } = await import("../src/main/voicePipeline.js");
    const child = makeFakeChild();
    spawnMock.mockReturnValue(child);

    const promise = runVoiceRoundTrip({
      cwd: "/repo",
      wakeAudioPath: "/repo/hey_jarvis.wav",
      commandAudioPath: "/repo/hello_world.wav",
      voiceId: "am_michael",
      responseAudioOutPath: "/tmp/out.wav",
    });

    expect(spawnMock).toHaveBeenCalledWith(
      "awf-speech",
      [
        "round-trip",
        "/repo/hey_jarvis.wav",
        "/repo/hello_world.wav",
        "--voice-id",
        "am_michael",
        "--response-audio-out",
        "/tmp/out.wav",
      ],
      { cwd: "/repo" },
    );

    child.stdout.emit(
      "data",
      Buffer.from(
        JSON.stringify({
          wake_detected: true,
          wake_score: 0.96,
          speech_segments: [[0.64, 1.34]],
          command_text: "Hello world.",
          command_language: "en",
          response_text: "Acknowledged: Hello world.",
          response_audio_path: "/tmp/out.wav",
        }) + "\n",
      ),
    );
    child.emit("close", 0);

    const result = await promise;
    expect(result.command_text).toBe("Hello world.");
    expect(result.wake_detected).toBe(true);
  });

  it("omits --voice-id entirely when voiceId is not supplied, letting the CLI resolve its own default", async () => {
    const { runVoiceRoundTrip } = await import("../src/main/voicePipeline.js");
    const child = makeFakeChild();
    spawnMock.mockReturnValue(child);

    const promise = runVoiceRoundTrip({
      cwd: "/repo",
      wakeAudioPath: "/repo/hey_jarvis.wav",
      commandAudioPath: "/repo/hello_world.wav",
      responseAudioOutPath: "/tmp/out.wav",
    });

    expect(spawnMock).toHaveBeenCalledWith(
      "awf-speech",
      [
        "round-trip",
        "/repo/hey_jarvis.wav",
        "/repo/hello_world.wav",
        "--response-audio-out",
        "/tmp/out.wav",
      ],
      { cwd: "/repo" },
    );

    child.stdout.emit(
      "data",
      Buffer.from(
        JSON.stringify({
          wake_detected: true,
          wake_score: 0.96,
          speech_segments: [[0.64, 1.34]],
          command_text: "Hello world.",
          command_language: "en",
          response_text: "Acknowledged: Hello world.",
          response_audio_path: "/tmp/out.wav",
        }) + "\n",
      ),
    );
    child.emit("close", 0);

    await promise;
  });

  it("rejects with the pipeline's error message when the wake word never fires", async () => {
    const { runVoiceRoundTrip } = await import("../src/main/voicePipeline.js");
    const child = makeFakeChild();
    spawnMock.mockReturnValue(child);

    const promise = runVoiceRoundTrip({
      cwd: "/repo",
      wakeAudioPath: "/repo/not_a_wake_word.wav",
      commandAudioPath: "/repo/hello_world.wav",
      responseAudioOutPath: "/tmp/out.wav",
    });

    child.stdout.emit(
      "data",
      Buffer.from(JSON.stringify({ error: "wake word did not fire on ..." }) + "\n"),
    );
    child.emit("close", 1);

    await expect(promise).rejects.toThrow(/wake word did not fire/);
  });

  it("rejects when the subprocess produces no valid JSON", async () => {
    const { runVoiceRoundTrip } = await import("../src/main/voicePipeline.js");
    const child = makeFakeChild();
    spawnMock.mockReturnValue(child);

    const promise = runVoiceRoundTrip({
      cwd: "/repo",
      wakeAudioPath: "/repo/x.wav",
      commandAudioPath: "/repo/y.wav",
      responseAudioOutPath: "/tmp/out.wav",
    });

    child.stderr.emit("data", Buffer.from("Traceback (most recent call last): ..."));
    child.emit("close", 1);

    await expect(promise).rejects.toThrow(/no valid JSON/);
  });
});

describe("registerVoiceIpcHandler", () => {
  it("wires the voice channel to runVoiceRoundTrip with the given defaults", async () => {
    const { registerVoiceIpcHandler, VOICE_CHANNEL } = await import("../src/main/voicePipeline.js");
    const child = makeFakeChild();
    spawnMock.mockReturnValue(child);

    const handlers = new Map<string, (...args: unknown[]) => unknown>();
    const ipcMain = {
      handle: (channel: string, listener: (...args: unknown[]) => unknown) => {
        handlers.set(channel, listener);
      },
    };

    registerVoiceIpcHandler(ipcMain, { command: "awf-speech", cwd: "/repo" });

    const promise = handlers.get(VOICE_CHANNEL)?.(
      {},
      "/repo/wake.wav",
      "/repo/cmd.wav",
      "bf_emma",
      "/tmp/out.wav",
    );

    expect(spawnMock).toHaveBeenCalledWith(
      "awf-speech",
      expect.arrayContaining(["/repo/wake.wav", "/repo/cmd.wav", "--voice-id", "bf_emma"]),
      { cwd: "/repo" },
    );

    child.stdout.emit(
      "data",
      Buffer.from(
        JSON.stringify({
          wake_detected: true,
          wake_score: 0.9,
          speech_segments: [],
          command_text: "hi",
          command_language: "en",
          response_text: "ok",
          response_audio_path: "/tmp/out.wav",
        }),
      ),
    );
    child.emit("close", 0);

    await promise;
  });
});
