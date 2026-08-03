import { render, screen } from "@testing-library/react";
import React from "react";
import { describe, expect, it } from "vitest";
import { Transcript } from "../src/renderer/Transcript.js";

describe("Transcript", () => {
  it("renders every entry as visible text (text-first invariant)", () => {
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
  });

  it("renders an empty log with no entries", () => {
    render(<Transcript entries={[]} />);
    expect(screen.getByRole("log")).toBeTruthy();
  });
});
