import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import React from "react";
import { describe, expect, it, vi } from "vitest";
import { Transcript } from "../src/renderer/Transcript.js";

describe("Transcript", () => {
  it("renders every entry as a visible bubble (text-first invariant)", () => {
    render(
      <Transcript
        entries={[
          { id: 0, speaker: "Operator", text: "run the demo workflow" },
          { id: 1, speaker: "Builder", text: "Started produce-gate-repair-demo@1.0.0" },
        ]}
      />,
    );
    expect(screen.getByText(/run the demo workflow/)).toBeTruthy();
    expect(screen.getByText(/Started produce-gate-repair-demo/)).toBeTruthy();
    // operator (user) bubbles align right with an avatar; agent bubbles left.
    expect(document.querySelectorAll(".bubble").length).toBe(2);
    expect(document.querySelectorAll(".avatar").length).toBe(2);
    expect(document.querySelector(".bubble-user")).toBeTruthy();
    expect(document.querySelector(".bubble-agent")).toBeTruthy();
  });

  it("renders an empty chat window with no entries", () => {
    render(<Transcript entries={[]} />);
    expect(screen.getByRole("log")).toBeTruthy();
  });

  it("shows a composer with a mic button, an input, and a Send button", () => {
    render(<Transcript entries={[]} onSend={vi.fn()} onMic={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Push to talk" })).toBeTruthy();
    expect(screen.getByRole("textbox", { name: "Message" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Send" })).toBeTruthy();
  });

  it("Send appends the typed text via onSend and clears the input", async () => {
    const onSend = vi.fn();
    render(<Transcript entries={[]} onSend={onSend} />);
    const input = screen.getByRole("textbox", { name: "Message" }) as HTMLInputElement;
    fireEvent.change(input, { target: { value: "hello awf" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(onSend).toHaveBeenCalledWith("hello awf");
    await waitFor(() =>
      expect((screen.getByRole("textbox", { name: "Message" }) as HTMLInputElement).value).toBe(""),
    );
  });

  it("mic button triggers onMic", () => {
    const onMic = vi.fn();
    render(<Transcript entries={[]} onMic={onMic} />);
    fireEvent.click(screen.getByRole("button", { name: "Push to talk" }));
    expect(onMic).toHaveBeenCalled();
  });
});
