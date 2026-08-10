import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import React from "react";
import { describe, expect, it, vi } from "vitest";
import { App } from "../src/renderer/App.js";

describe("App dashboard wiring (runList/approvalList IPC channels)", () => {
  it("calls onRunList/onApprovalList on mount", async () => {
    const onRunList = vi.fn().mockResolvedValue([
      { run_id: "run-1", workflow_ref: "demo@1.0.0", status: "SUCCEEDED", created_at: "t", updated_at: "t" },
    ]);
    const onApprovalList = vi.fn().mockResolvedValue([]);

    render(
      <App onApprove={vi.fn()} onReject={vi.fn()} onRunList={onRunList} onApprovalList={onApprovalList} />,
    );

    await waitFor(() => expect(onRunList).toHaveBeenCalled());
    expect(onApprovalList).toHaveBeenCalled();
    await waitFor(() => expect(onApprovalList).toHaveBeenCalled());
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

    expect(await screen.findByRole("dialog", { name: "Approval confirmation" })).toBeTruthy();
  });

  it("no dashboard is rendered when neither onRunList nor onApprovalList is supplied", () => {
    render(<App onApprove={vi.fn()} onReject={vi.fn()} />);
    expect(screen.queryByRole("region", { name: "Dashboard" })).toBeNull();
  });

  it("uses control summary as the dashboard source when available", async () => {
    const onControlSummary = vi.fn().mockResolvedValue({
      runs: [{ run_id: "run-1", workflow_ref: "demo@1.0.0", status: "SUCCEEDED", created_at: "t", updated_at: "t" }],
      approvals: [],
      improvements: [],
      recent_verdicts: [],
      registry_counts: { skills: 1 },
      llm: { status: { state: "running" }, servers: { default_server: "llama-server" } },
      readiness: { profile_id: "linux-x64-cpu", readiness: {} },
    });

    render(<App onApprove={vi.fn()} onReject={vi.fn()} onControlSummary={onControlSummary} />);

    await waitFor(() => expect(onControlSummary).toHaveBeenCalled());
    expect(await screen.findByText("State: running")).toBeTruthy();
    expect(screen.getByText("skills: 1")).toBeTruthy();
  });

  it("loads selected run detail through the control detail prop", async () => {
    const onControlSummary = vi.fn().mockResolvedValue({
      runs: [{ run_id: "run-1", workflow_ref: "demo@1.0.0", status: "SUCCEEDED", created_at: "t", updated_at: "t" }],
      approvals: [],
      improvements: [],
      recent_verdicts: [],
      registry_counts: {},
      llm: {},
      readiness: { profile_id: "linux-x64-cpu", readiness: {} },
    });
    const onControlRunDetail = vi.fn().mockResolvedValue({
      run: {
        run_id: "run-1",
        workflow_ref: "demo@1.0.0",
        status: "SUCCEEDED",
        steps: [{ step_id: "s1", node_id: "check", status: "SUCCEEDED", attempt: 1 }],
      },
      artifacts: [],
      timeline: {},
      improvements: [],
      verdicts: [],
    });

    render(
      <App
        onApprove={vi.fn()}
        onReject={vi.fn()}
        onControlSummary={onControlSummary}
        onControlRunDetail={onControlRunDetail}
      />,
    );

    fireEvent.click(await screen.findByText("View details"));

    await waitFor(() => expect(onControlRunDetail).toHaveBeenCalledWith("run-1"));
    expect(await screen.findByText(/check: SUCCEEDED/)).toBeTruthy();
  });
});
