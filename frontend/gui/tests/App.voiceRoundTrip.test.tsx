import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "../src/renderer/App.js";

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
    delete (window as any).SpeechRecognition;
    delete (window as any).webkitSpeechRecognition;
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

  it("captures live speech recognition results during push to talk", async () => {
    const props = liveVoiceProps();
    let recognition: any;
    (window as any).SpeechRecognition = vi.fn(function FakeSpeechRecognition(this: any) {
      recognition = {
        continuous: false,
        interimResults: false,
        lang: "",
        onresult: null,
        onerror: null,
        start: vi.fn(),
        stop: vi.fn(),
      };
      return recognition;
    });
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: { getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [{ stop: vi.fn() }] }) },
    });
    render(<App onApprove={vi.fn()} onReject={vi.fn()} {...props} />);

    fireEvent.click(screen.getByText("Start voice session"));
    expect(await screen.findByText(/Voice session: vs-1/)).toBeTruthy();
    fireEvent.click(screen.getByText("Push to talk"));
    await waitFor(() => expect(recognition.start).toHaveBeenCalled());

    recognition.onresult({
      resultIndex: 0,
      results: {
        length: 1,
        0: { isFinal: true, 0: { transcript: "Hello from microphone." } },
      },
    });

    expect(await screen.findByDisplayValue("Hello from microphone.")).toBeTruthy();
  });

  it("does not render live voice controls when session handlers are absent", () => {
    render(<App onApprove={vi.fn()} onReject={vi.fn()} />);
    expect(screen.queryByRole("group", { name: "Voice session" })).toBeNull();
  });
});
