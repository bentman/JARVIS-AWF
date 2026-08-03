import { fireEvent, render, screen } from "@testing-library/react";
import React from "react";
import { describe, expect, it, vi } from "vitest";
import { App } from "../src/renderer/App.js";

describe("App voice round trip (text-first invariant)", () => {
  it("renders both the recognized command and the response as visible transcript text", async () => {
    const onVoiceRoundTrip = vi.fn().mockResolvedValue({
      command_text: "Hello world.",
      response_text: "Acknowledged: Hello world.",
    });

    render(
      <App onApprove={vi.fn()} onReject={vi.fn()} onVoiceRoundTrip={onVoiceRoundTrip} />,
    );

    fireEvent.change(screen.getByPlaceholderText("/path/to/hey_jarvis.wav"), {
      target: { value: "/fixtures/hey_jarvis.wav" },
    });
    fireEvent.change(screen.getByPlaceholderText("/path/to/command.wav"), {
      target: { value: "/fixtures/hello_world.wav" },
    });
    fireEvent.click(screen.getByText("Activate"));

    expect(onVoiceRoundTrip).toHaveBeenCalledWith("/fixtures/hey_jarvis.wav", "/fixtures/hello_world.wav");

    expect(await screen.findByText(/Operator \(voice\):/)).toBeTruthy();
    expect(screen.getByText(/Acknowledged: Hello world\./)).toBeTruthy();
  });

  it("shows an error message inline when the round trip rejects (e.g. wake word did not fire)", async () => {
    const onVoiceRoundTrip = vi.fn().mockRejectedValue(new Error("wake word did not fire on x.wav"));

    render(<App onApprove={vi.fn()} onReject={vi.fn()} onVoiceRoundTrip={onVoiceRoundTrip} />);

    fireEvent.change(screen.getByPlaceholderText("/path/to/hey_jarvis.wav"), {
      target: { value: "/fixtures/not_wake_word.wav" },
    });
    fireEvent.change(screen.getByPlaceholderText("/path/to/command.wav"), {
      target: { value: "/fixtures/hello_world.wav" },
    });
    fireEvent.click(screen.getByText("Activate"));

    expect(await screen.findByRole("alert")).toHaveTextContent(/wake word did not fire/);
  });

  it("does not render the voice activation controls when no handler is supplied", () => {
    render(<App onApprove={vi.fn()} onReject={vi.fn()} />);
    expect(screen.queryByRole("group", { name: "Voice activation" })).toBeNull();
  });
});
