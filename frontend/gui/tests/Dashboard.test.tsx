import { fireEvent, render, screen } from "@testing-library/react";
import React from "react";
import { describe, expect, it, vi } from "vitest";
import { Dashboard } from "../src/renderer/Dashboard.js";

describe("Dashboard", () => {
  it("shows real runs and pending approvals, not placeholders", () => {
    render(
      <Dashboard
        runs={[
          { run_id: "run-1", workflow_ref: "demo@1.0.0", status: "SUCCEEDED", created_at: "t", updated_at: "t" },
        ]}
        approvals={[
          {
            approval_id: "ap-1", run_id: "run-1", step_id: "step-1", action_digest: "sha256:deadbeef",
            status: "pending", reason: null, requested_at: "t", decided_at: null, risk_class: "R2",
          },
        ]}
        onRefresh={vi.fn()}
        refreshing={false}
      />,
    );

    expect(screen.getByText(/demo@1.0.0/)).toBeTruthy();
    expect(screen.getByText(/sha256:deadbeef/)).toBeTruthy();
    expect(screen.getByText(/R2/)).toBeTruthy();
  });

  it("shows empty-state text, not nothing, when there is no data", () => {
    render(<Dashboard runs={[]} approvals={[]} onRefresh={vi.fn()} refreshing={false} />);

    expect(screen.getByText("No runs yet.")).toBeTruthy();
    expect(screen.getByText("No pending approvals.")).toBeTruthy();
  });

  it("clicking Refresh calls onRefresh", () => {
    const onRefresh = vi.fn();
    render(<Dashboard runs={[]} approvals={[]} onRefresh={onRefresh} refreshing={false} />);

    fireEvent.click(screen.getByText("Refresh"));

    expect(onRefresh).toHaveBeenCalled();
  });
});
