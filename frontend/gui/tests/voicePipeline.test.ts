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

describe("runVoiceSpeakText", () => {
  beforeEach(() => {
    spawnMock.mockReset();
  });

  it("spawns awf-speech synthesize with the expected arguments", async () => {
    const { runVoiceSpeakText } = await import("../src/main/voicePipeline.js");
    const child = makeFakeChild();
    spawnMock.mockReturnValue(child);

    const promise = runVoiceSpeakText({
      cwd: "/repo",
      text: "Hello world.",
      voiceId: "bf_isabella",
      responseAudioOutPath: "/tmp/live.wav",
    });

    expect(spawnMock).toHaveBeenCalledWith(
      "awf-speech",
      ["synthesize", "Hello world.", "--voice-id", "bf_isabella", "--response-audio-out", "/tmp/live.wav"],
      { cwd: "/repo" },
    );

    child.stdout.emit(
      "data",
      Buffer.from(JSON.stringify({ response_text: "Hello world.", voice_id: "bf_isabella", response_audio_path: "/tmp/live.wav" })),
    );
    child.emit("close", 0);

    await expect(promise).resolves.toEqual({
      response_text: "Hello world.",
      voice_id: "bf_isabella",
      response_audio_path: "/tmp/live.wav",
    });
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

describe("registerVoiceSessionIpcHandlers", () => {
  it("wires live voice channels to protocol client methods", async () => {
    const { registerVoiceSessionIpcHandlers, VOICE_SESSION_CHANNELS } = await import("../src/main/voicePipeline.js");
    const handlers = new Map<string, (...args: unknown[]) => unknown>();
    const ipcMain = {
      handle: (channel: string, listener: (...args: unknown[]) => unknown) => {
        handlers.set(channel, listener);
      },
    };
    const client = {
      voiceSessionStart: vi.fn().mockResolvedValue({ voice_session_id: "vs-1", state: "idle" }),
      voiceSessionClose: vi.fn().mockResolvedValue({ voice_session_id: "vs-1", state: "closed" }),
      voiceEvent: vi.fn().mockResolvedValue({ voice_session_id: "vs-1", state: "listening" }),
      voiceSubmitText: vi.fn().mockResolvedValue({ voice_session_id: "vs-1", response_text: "ok" }),
    } as any;

    registerVoiceSessionIpcHandlers(ipcMain, client);

    await handlers.get(VOICE_SESSION_CHANNELS.start)?.({}, "Voice session", false);
    expect(client.voiceSessionStart).toHaveBeenCalledWith("Voice session", false);

    await handlers.get(VOICE_SESSION_CHANNELS.pushToTalkStart)?.({}, "vs-1", "turn-1");
    expect(client.voiceEvent).toHaveBeenCalledWith("vs-1", "vad.speech_started", {}, "turn-1");

    await handlers.get(VOICE_SESSION_CHANNELS.pushToTalkStop)?.({}, "vs-1", "turn-1");
    expect(client.voiceEvent).toHaveBeenCalledWith("vs-1", "vad.speech_stopped", {}, "turn-1");

    await handlers.get(VOICE_SESSION_CHANNELS.interrupt)?.({}, "vs-1", "turn-1");
    expect(client.voiceEvent).toHaveBeenCalledWith("vs-1", "interruption", {}, "turn-1");

    await handlers.get(VOICE_SESSION_CHANNELS.submitText)?.(
      {},
      "vs-1",
      "hello",
      "voice-demo@1.0.0",
      "narrator@1.0.0",
      "turn-1",
    );
    expect(client.voiceSubmitText).toHaveBeenCalledWith({
      voiceSessionId: "vs-1",
      text: "hello",
      workflowRef: "voice-demo@1.0.0",
      voiceProfileRef: "narrator@1.0.0",
      turnId: "turn-1",
    });

    await handlers.get(VOICE_SESSION_CHANNELS.stop)?.({}, "vs-1", "done");
    expect(client.voiceSessionClose).toHaveBeenCalledWith("vs-1", "done");
  });
});

describe("registerVoiceSpeakIpcHandler", () => {
  it("wires response speech synthesis to awf-speech synthesize", async () => {
    const { registerVoiceSpeakIpcHandler, VOICE_SESSION_CHANNELS } = await import("../src/main/voicePipeline.js");
    const child = makeFakeChild();
    spawnMock.mockReturnValue(child);
    const handlers = new Map<string, (...args: unknown[]) => unknown>();
    const ipcMain = {
      handle: (channel: string, listener: (...args: unknown[]) => unknown) => {
        handlers.set(channel, listener);
      },
    };

    registerVoiceSpeakIpcHandler(ipcMain, { command: "awf-speech", cwd: "/repo" });
    const promise = handlers.get(VOICE_SESSION_CHANNELS.speakText)?.({}, "hi", "bf_isabella", "/tmp/out.wav");

    expect(spawnMock).toHaveBeenCalledWith(
      "awf-speech",
      ["synthesize", "hi", "--voice-id", "bf_isabella", "--response-audio-out", "/tmp/out.wav"],
      { cwd: "/repo" },
    );
    child.stdout.emit(
      "data",
      Buffer.from(JSON.stringify({ response_text: "hi", voice_id: "bf_isabella", response_audio_path: "/tmp/out.wav" })),
    );
    child.emit("close", 0);

    await promise;
  });
});
