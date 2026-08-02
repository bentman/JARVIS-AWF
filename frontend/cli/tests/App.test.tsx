import { render } from "ink-testing-library";
import React from "react";
import { describe, expect, it, vi } from "vitest";
import { App } from "../src/App.js";
import { DEFAULT_SETTINGS } from "../src/settings.js";

function makeFakeClient() {
  return {
    close: vi.fn(),
    runStart: vi.fn().mockResolvedValue({ run_id: "run-1", status: "SUCCEEDED" }),
  } as any;
}

// Interactive input-driven behavior (typing, submitting a command) is not
// exercised here: ink-testing-library's fake stdin does not reliably drive
// Ink 7's internal keypress pipeline (`internal_eventEmitter`) in this
// dependency combination, so a synthetic stdin.write() never reaches
// ink-text-input's useInput handler. That behavior is instead validated by
// a real PTY-driven subprocess run of the compiled CLI (see CHANGE_LOG).
describe("App", () => {
  it("renders the ready message and input prompt on first frame", () => {
    const { lastFrame } = render(<App client={makeFakeClient()} settings={DEFAULT_SETTINGS} />);
    const frame = lastFrame();
    expect(frame).toContain("AWF-CLI ready");
    expect(frame).toContain(">");
  });
});
