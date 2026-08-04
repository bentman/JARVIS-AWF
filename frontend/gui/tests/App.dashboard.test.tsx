import { render, screen, waitFor } from "@testing-library/react";
import React from "react";
import { describe, expect, it, vi } from "vitest";
import { App } from "../src/renderer/App.js";

describe("App dashboard wiring (runList/approvalList IPC channels)", () => {
  it("calls onRunList/onApprovalList on mount and renders the results", async () => {
    const onRunList = vi.fn().mockResolvedValue([
      { run_id: "run-1", workflow_ref: "demo@1.0.0", status: "SUCCEEDED", created_at: "t", updated_at: "t" },
    ]);
    const onApprovalList = vi.fn().mockResolvedValue([]);

    render(
      <App onApprove={vi.fn()} onReject={vi.fn()} onRunList={onRunList} onApprovalList={onApprovalList} />,
    );

    await waitFor(() => expect(onRunList).toHaveBeenCalled());
    expect(onApprovalList).toHaveBeenCalled();
    expect(await screen.findByText(/demo@1.0.0/)).toBeTruthy();
  });

  it("a pending approval from approvalList reaches the on-screen ApprovalConfirmation UI", async () => {
    const onApprovalList = vi.fn().mockResolvedValue([
      {
        approval_id: "ap-1", run_id: "run-1", step_id: "step-1", action_digest: "sha256:deadbeef",
        status: "pending", reason: null, requested_at: "t", decided_at: null, risk_class: "R2",
      },
    ]);

    render(
      <App
        onApprove={vi.fn()}
        onReject={vi.fn()}
        onRunList={vi.fn().mockResolvedValue([])}
        onApprovalList={onApprovalList}
      />,
    );

    expect(await screen.findByRole("dialog", { name: "Approval confirmation" })).toBeTruthy();
    expect(screen.getByText("sha256:deadbeef")).toBeTruthy();
  });

  it("an approval with no stored risk_class renders as R2, never silently as R0/R1", async () => {
    const onApprovalList = vi.fn().mockResolvedValue([
      {
        approval_id: "ap-1", run_id: "run-1", step_id: "step-1", action_digest: "sha256:deadbeef",
        status: "pending", reason: null, requested_at: "t", decided_at: null, risk_class: null,
      },
    ]);

    render(
      <App
        onApprove={vi.fn()}
        onReject={vi.fn()}
        onRunList={vi.fn().mockResolvedValue([])}
        onApprovalList={onApprovalList}
      />,
    );

    expect(await screen.findByText(/R2/)).toBeTruthy();
  });

  it("no dashboard is rendered when neither onRunList nor onApprovalList is supplied", () => {
    render(<App onApprove={vi.fn()} onReject={vi.fn()} />);
    expect(screen.queryByRole("region", { name: "Dashboard" })).toBeNull();
  });
});
