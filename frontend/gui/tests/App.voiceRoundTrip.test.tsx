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
      voice: { voice_profile_ref: "narrator@1.0.0", voice_id: "bf_isabella" },
    }),
  };
}

describe("App live voice session (text-first invariant)", () => {
  it("renders recognized voice text and response text in the visible transcript", async () => {
    const props = liveVoiceProps();
    render(<App onApprove={vi.fn()} onReject={vi.fn()} {...props} />);

    fireEvent.click(screen.getByText("Start voice session"));
    expect(await screen.findByText(/Voice session: vs-1/)).toBeTruthy();

    fireEvent.change(screen.getByPlaceholderText("workflow@1.0.0"), {
      target: { value: "voice-demo@1.0.0" },
    });
    fireEvent.change(screen.getByRole("textbox", { name: "Final recognized text" }), {
      target: { value: "Hello world." },
    });
    fireEvent.click(screen.getByText("Submit voice text"));

    expect(props.onVoiceSubmitText).toHaveBeenCalledWith(
      "vs-1",
      "Hello world.",
      "voice-demo@1.0.0",
      "narrator@1.0.0",
      expect.stringMatching(/^turn-/),
    );
    expect(await screen.findByText(/Operator \(voice\):/)).toBeTruthy();
    expect(screen.getByText(/Workflow voice-demo@1\.0\.0 finished/)).toBeTruthy();
  });

  it("shows a clear error when no default workflow is supplied", async () => {
    const props = liveVoiceProps();
    render(<App onApprove={vi.fn()} onReject={vi.fn()} {...props} />);

    fireEvent.click(screen.getByText("Start voice session"));
    expect(await screen.findByText(/Voice session: vs-1/)).toBeTruthy();
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
