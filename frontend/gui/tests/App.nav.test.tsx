import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import React from "react";
import { describe, expect, it, vi } from "vitest";
import { App } from "../src/renderer/App.js";

describe("App top navigation (ADR-0025 control-center shell)", () => {
  it("selecting a rail view renders that view's region and hides the previously-active one", async () => {
    const onControlSummary = vi.fn().mockResolvedValue({
      runs: [],
      approvals: [],
      improvements: [],
      recent_verdicts: [],
      registry_counts: {},
      llm: {},
      readiness: { profile_id: "linux-x64-cpu", inventory: null, tokens: [], readiness: {} },
    });

    render(
      <App
        onApprove={vi.fn()}
        onReject={vi.fn()}
        onControlSummary={onControlSummary}
        onRegistryValidate={vi.fn()}
        onRegistryPublish={vi.fn()}
        onRegistryReindex={vi.fn()}
        onRegistryRetire={vi.fn()}
        onRegistryTrust={vi.fn()}
      />,
    );

    await waitFor(() => expect(onControlSummary).toHaveBeenCalled());
    // The launch page is chat + voice; diagnostics hide behind the Status button.
    expect(screen.queryByText("System readiness")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Status" }));
    expect(await screen.findByText("System readiness")).toBeTruthy();
    expect(screen.queryByRole("region", { name: "Registry actions" })).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Registry" }));

    expect(await screen.findByRole("region", { name: "Registry actions" })).toBeTruthy();
    expect(screen.queryByText("System readiness")).toBeNull();
  });

  it("keeps the status bar visible regardless of active view", async () => {
    const onControlSummary = vi.fn().mockResolvedValue({
      runs: [],
      approvals: [],
      improvements: [],
      recent_verdicts: [],
      registry_counts: {},
      llm: {},
      readiness: { profile_id: "linux-x64-cpu", inventory: null, tokens: [], readiness: {} },
    });

    render(
      <App
        onApprove={vi.fn()}
        onReject={vi.fn()}
        onControlSummary={onControlSummary}
        onRegistryValidate={vi.fn()}
        onRegistryPublish={vi.fn()}
        onRegistryReindex={vi.fn()}
        onRegistryRetire={vi.fn()}
        onRegistryTrust={vi.fn()}
      />,
    );

    await waitFor(() => expect(onControlSummary).toHaveBeenCalled());
    expect(screen.getByRole("status", { name: "Status" })).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Registry" }));

    expect(screen.getByRole("status", { name: "Status" })).toBeTruthy();
  });

  it("raises a count badge on the Approvals nav item when approvals are pending", async () => {
    const onControlSummary = vi.fn().mockResolvedValue({
      runs: [],
      approvals: [
        {
          approval_id: "ap-1",
          run_id: "run-1",
          step_id: "step-1",
          action_digest: "sha256:deadbeef",
          status: "pending",
          reason: null,
          requested_at: "t",
          decided_at: null,
          risk_class: "R0",
        },
      ],
      improvements: [],
      recent_verdicts: [],
      registry_counts: {},
      llm: {},
      readiness: { profile_id: "linux-x64-cpu", inventory: null, tokens: [], readiness: {} },
    });

    render(<App onApprove={vi.fn()} onReject={vi.fn()} onControlSummary={onControlSummary} />);

    await waitFor(() => expect(onControlSummary).toHaveBeenCalled());
    const approvalsButton = await screen.findByText("Approvals");
    expect(approvalsButton.closest("button")).toHaveTextContent("1");
  });

  it("does not list a view whose callbacks are absent", async () => {
    const onControlSummary = vi.fn().mockResolvedValue({
      runs: [],
      approvals: [],
      improvements: [],
      recent_verdicts: [],
      registry_counts: {},
      llm: {},
      readiness: { profile_id: "linux-x64-cpu", inventory: null, tokens: [], readiness: {} },
    });

    render(<App onApprove={vi.fn()} onReject={vi.fn()} onControlSummary={onControlSummary} />);

    await waitFor(() => expect(onControlSummary).toHaveBeenCalled());
    // The chat page is always listed first, even when most views are absent.
    expect(screen.getByRole("button", { name: "Chat" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Registry" })).toBeNull();
  });
});

describe("App first page (chat + voice, ADR-0025)", () => {
  function voiceProps() {
    return {
      onVoiceSessionStart: vi
        .fn()
        .mockResolvedValue({ voice_session_id: "vs-1", memory_session_id: "vs-1", state: "idle" }),
      onVoicePushToTalkStart: vi
        .fn()
        .mockResolvedValue({ voice_session_id: "vs-1", memory_session_id: "vs-1", state: "listening" }),
      onVoicePushToTalkStop: vi
        .fn()
        .mockResolvedValue({ voice_session_id: "vs-1", memory_session_id: "vs-1", state: "transcribing" }),
      onVoiceInterrupt: vi
        .fn()
        .mockResolvedValue({ voice_session_id: "vs-1", memory_session_id: "vs-1", state: "idle" }),
      onVoiceSubmitText: vi.fn().mockResolvedValue({
        voice_session_id: "vs-1",
        state: "speaking",
        recognized_text: "hi",
        response_text: "hello",
      }),
      onVoiceSpeakText: vi.fn(),
      initialTranscript: [
        { id: 0, speaker: "Operator", text: "run demo" },
        { id: 1, speaker: "Builder", text: "done" },
      ],
    };
  }

  it("launches on the Chat page: a scrollable chat window beside a voice button panel", () => {
    render(<App onApprove={vi.fn()} onReject={vi.fn()} {...voiceProps()} />);
    // The chat window is the first page's log surface.
    expect(screen.getByRole("log", { name: "Chat log" })).toBeTruthy();
    // The voice control is a simple group with buttons - no orb.
    expect(screen.getByRole("group", { name: "Voice session" })).toBeTruthy();
    // The Chat nav item is the active first page.
    expect(screen.getByRole("button", { name: "Chat" }).getAttribute("aria-current")).toBe("page");
  });

  it("has no pulsing orb or canvas anywhere on the first page", () => {
    render(<App onApprove={vi.fn()} onReject={vi.fn()} {...voiceProps()} />);
    expect(document.querySelector("canvas")).toBeNull();
    expect(screen.queryByText(/orb/i)).toBeNull();
  });

  it("keeps diagnostics off the first page even when status data is available", async () => {
    const onControlSummary = vi.fn().mockResolvedValue({
      runs: [],
      approvals: [],
      improvements: [],
      recent_verdicts: [],
      registry_counts: {},
      llm: {},
      readiness: { profile_id: "linux-x64-cpu", inventory: null, tokens: [], readiness: {} },
    });

    render(
      <App onApprove={vi.fn()} onReject={vi.fn()} {...voiceProps()} onControlSummary={onControlSummary} />,
    );

    await waitFor(() => expect(onControlSummary).toHaveBeenCalled());
    expect(screen.getByRole("log", { name: "Chat log" })).toBeTruthy();
    expect(screen.queryByText("System readiness")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Status" }));
    expect(await screen.findByText("System readiness")).toBeTruthy();
  });

  it("renders voice (STT/TTS) and typed chat in the same conversation stream", async () => {
    render(
      <App
        onApprove={vi.fn()}
        onReject={vi.fn()}
        {...voiceProps()}
        onVoiceSpeakText={undefined}
      />,
    );
    const log = screen.getByRole("log", { name: "Chat log" });

    // A voice round trip lands in the shared stream.
    fireEvent.click(screen.getByText("Start voice session"));
    expect(await screen.findByText(/Voice session: vs-1/)).toBeTruthy();
    fireEvent.change(screen.getByPlaceholderText("workflow@1.0.0"), {
      target: { value: "demo@1.0.0" },
    });
    fireEvent.change(screen.getByRole("textbox", { name: "Final recognized text" }), {
      target: { value: "hi" },
    });
    fireEvent.click(screen.getByText("Submit voice text"));
    expect(await screen.findByText("hello")).toBeTruthy();

    // Typed chat lands in the very same stream.
    fireEvent.change(screen.getByRole("textbox", { name: "Message" }), {
      target: { value: "typed follow-up" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    expect(log.textContent).toContain("Operator (voice):");
    expect(log.textContent).toContain("hello");
    expect(log.textContent).toContain("typed follow-up");
  });
});

