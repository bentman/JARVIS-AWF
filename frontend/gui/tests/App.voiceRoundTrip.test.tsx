import { fireEvent, render, screen } from "@testing-library/react";
import React from "react";
import { describe, expect, it, vi } from "vitest";
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

  it("shows a clear error when no default workflow is supplied", async () => {
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

    expect(await screen.findByRole("alert")).toHaveTextContent(/Set a default workflow/);
    expect(props.onVoiceSubmitText).not.toHaveBeenCalled();
  });

  it("does not render live voice controls when session handlers are absent", () => {
    render(<App onApprove={vi.fn()} onReject={vi.fn()} />);
    expect(screen.queryByRole("group", { name: "Voice session" })).toBeNull();
  });
});
