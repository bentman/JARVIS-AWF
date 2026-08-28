import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "../src/renderer/App.js";

// `blobToWav16` needs a real AudioContext, which jsdom does not provide.
// Its encoding contract is covered directly in `wav.test.ts`; here we only
// care that push-to-talk routes the recording through it to
// `window.awf.voiceTranscribe` and lands the result in the transcript.
const blobToWav16Mock = vi.fn().mockResolvedValue(new ArrayBuffer(8));
vi.mock("../src/renderer/wav.js", () => ({
  STT_SAMPLE_RATE: 16000,
  encodeWav16: vi.fn(),
  blobToWav16: (...args: unknown[]) => blobToWav16Mock(...args),
}));

function liveVoiceProps() {
  return {
    onVoiceSessionStart: vi.fn().mockResolvedValue({ voice_session_id: "vs-1", memory_session_id: "vs-1", state: "idle" }),
    onVoicePushToTalkStart: vi.fn().mockResolvedValue({
      voice_session_id: "vs-1",
      memory_session_id: "vs-1",
      state: "listening",
    }),
    onVoicePushToTalkStop: vi.fn().mockResolvedValue({
      voice_session_id: "vs-1",
      memory_session_id: "vs-1",
      state: "transcribing",
    }),
    onVoiceInterrupt: vi.fn().mockResolvedValue({
      voice_session_id: "vs-1",
      memory_session_id: "vs-1",
      state: "listening",
    }),
    onVoiceSubmitText: vi.fn().mockResolvedValue({
      voice_session_id: "vs-1",
      state: "speaking",
      recognized_text: "Hello world.",
      response_text: "Workflow voice-demo@1.0.0 finished with status SUCCEEDED.",
      run: { run_id: "run-voice-1" },
      voice: { voice_profile_ref: "narrator@1.0.0", voice_id: "bf_isabella" },
    }),
    onVoiceSpeakText: vi.fn().mockResolvedValue({ response_audio_path: "host-temp/awf-gui-live-response.wav" }),
  };
}

describe("App live voice session (text-first invariant)", () => {
  afterEach(() => {
    delete (globalThis as any).MediaRecorder;
    delete (window as any).awf;
    blobToWav16Mock.mockClear();
  });

  it("renders recognized voice text and response text in the visible transcript", async () => {
    const props = liveVoiceProps();
    const onControlRunDetail = vi.fn().mockResolvedValue({
      run: { run_id: "run-voice-1", workflow_ref: "voice-demo@1.0.0", status: "SUCCEEDED", steps: [] },
      artifacts: [],
      verdicts: [],
      timeline: {},
    });
    render(<App onApprove={vi.fn()} onReject={vi.fn()} {...props} onControlRunDetail={onControlRunDetail} />);

    fireEvent.click(screen.getByText("Start voice session"));
    expect(await screen.findByText(/Voice session: vs-1/)).toBeTruthy();

    fireEvent.change(screen.getByRole("textbox", { name: "Final recognized text" }), {
      target: { value: "Hello world." },
    });
    fireEvent.click(screen.getByText("Submit voice text"));

    expect(props.onVoiceSubmitText).toHaveBeenCalledWith(
      "vs-1",
      "Hello world.",
      "assistant-default@1.0.0",
      "narrator@1.0.0",
      expect.stringMatching(/^turn-/),
    );
    expect(await screen.findByText(/Operator \(voice\):/)).toBeTruthy();
    expect(screen.getByText(/Workflow voice-demo@1\.0\.0 finished/)).toBeTruthy();
    expect(props.onVoiceSpeakText).toHaveBeenCalledWith(
      "Workflow voice-demo@1.0.0 finished with status SUCCEEDED.",
      "bf_isabella",
    );
    expect(onControlRunDetail).toHaveBeenCalledWith("run-voice-1");
  });

  it("lets the backend apply the default workflow when the field is empty", async () => {
    const props = liveVoiceProps();
    render(<App onApprove={vi.fn()} onReject={vi.fn()} {...props} />);

    fireEvent.click(screen.getByText("Start voice session"));
    expect(await screen.findByText(/Voice session: vs-1/)).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Default workflow"), {
      target: { value: "" },
    });
    fireEvent.change(screen.getByRole("textbox", { name: "Final recognized text" }), {
      target: { value: "Hello world." },
    });
    fireEvent.click(screen.getByText("Submit voice text"));

    expect(props.onVoiceSubmitText).toHaveBeenCalledWith(
      "vs-1",
      "Hello world.",
      undefined,
      "narrator@1.0.0",
      expect.stringMatching(/^turn-/),
    );
  });

  it("transcribes the push-to-talk recording through awf-speech, not a browser recognizer", async () => {
    const props = liveVoiceProps();
    let recorder: any;
    (globalThis as any).MediaRecorder = vi.fn(function FakeMediaRecorder(this: any) {
      recorder = {
        mimeType: "audio/webm",
        state: "inactive",
        ondataavailable: null as ((event: { data: Blob }) => void) | null,
        onstop: null as (() => void) | null,
        start: vi.fn(() => {
          recorder.state = "recording";
        }),
        stop: vi.fn(() => {
          recorder.state = "inactive";
          recorder.ondataavailable?.({ data: new Blob([new Uint8Array([1, 2, 3])]) });
          recorder.onstop?.();
        }),
      };
      return recorder;
    });
    const voiceTranscribe = vi.fn().mockResolvedValue({ text: "Hello from microphone.", language: "en" });
    (window as any).awf = { voiceTranscribe };
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: { getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [{ stop: vi.fn() }] }) },
    });
    render(<App onApprove={vi.fn()} onReject={vi.fn()} {...props} />);

    fireEvent.click(screen.getByText("Start voice session"));
    expect(await screen.findByText(/Voice session: vs-1/)).toBeTruthy();
    fireEvent.click(screen.getByText("Push to talk"));
    await waitFor(() => expect(recorder.start).toHaveBeenCalled());

    fireEvent.click(screen.getByText("Stop talking"));

    expect(await screen.findByDisplayValue("Hello from microphone.")).toBeTruthy();
    expect(blobToWav16Mock).toHaveBeenCalledTimes(1);
    expect(voiceTranscribe).toHaveBeenCalledWith(expect.any(ArrayBuffer));
  });

  it("does not render live voice controls when session handlers are absent", () => {
    render(<App onApprove={vi.fn()} onReject={vi.fn()} />);
    expect(screen.queryByRole("group", { name: "Voice session" })).toBeNull();
  });
});
