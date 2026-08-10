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
            approval_id: "ap-1",
            run_id: "run-1",
            step_id: "step-1",
            action_digest: "sha256:deadbeef",
            status: "pending",
            reason: null,
            requested_at: "t",
            decided_at: null,
            risk_class: "R2",
          },
        ]}
        improvements={[
          {
            improvement_id: "imp-1",
            run_id: "run-1",
            status: "ready_for_review",
            summary: "Focused fix",
            diff_digest: "sha256:feedface",
            patch_artifact_id: "patch-1",
            verdict_artifact_id: "verdict-1",
            merge_commit: null,
            approval: { approval_id: "ap-2", status: "pending" },
          },
        ]}
        controlSummary={{
          runs: [],
          approvals: [],
          improvements: [],
          recent_verdicts: [],
          registry_counts: { skills: 2, workflows: 1 },
          llm: {
            servers: { default_server: "llama-server" },
            status: { state: "stopped", server_id: "llama-server", profile_id: "linux-x64-cpu" },
          },
          readiness: {
            profile_id: "linux-x64-cpu",
            readiness: { stt: { device: "cpu", ready: true, reason: "available" } },
          },
        }}
        onRefresh={vi.fn()}
        refreshing={false}
      />,
    );

    expect(screen.getByText(/demo@1.0.0/)).toBeTruthy();
    expect(screen.getByText(/sha256:deadbeef/)).toBeTruthy();
    expect(screen.getByText(/R2/)).toBeTruthy();
    expect(screen.getByText(/Focused fix/)).toBeTruthy();
    expect(screen.getByText(/sha256:feedface/)).toBeTruthy();
    expect(screen.getByText("Profile: linux-x64-cpu")).toBeTruthy();
    expect(screen.getByText("State: stopped")).toBeTruthy();
    expect(screen.getByText("skills: 2")).toBeTruthy();
  });

  it("shows empty-state text, not nothing, when there is no data", () => {
    render(<Dashboard runs={[]} approvals={[]} onRefresh={vi.fn()} refreshing={false} />);

    expect(screen.getByText("No runs yet.")).toBeTruthy();
    expect(screen.getByText("No pending approvals.")).toBeTruthy();
    expect(screen.getByText("No improvement proposals.")).toBeTruthy();
  });

  it("clicking Refresh calls onRefresh", () => {
    const onRefresh = vi.fn();
    render(<Dashboard runs={[]} approvals={[]} onRefresh={onRefresh} refreshing={false} />);

    fireEvent.click(screen.getByText("Refresh"));

    expect(onRefresh).toHaveBeenCalled();
  });

  it("requests and renders selected run detail", () => {
    const onRunDetail = vi.fn();
    render(
      <Dashboard
        runs={[
          { run_id: "run-1", workflow_ref: "demo@1.0.0", status: "SUCCEEDED", created_at: "t", updated_at: "t" },
        ]}
        approvals={[]}
        selectedRunDetail={{
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
        }}
        onRefresh={vi.fn()}
        onRunDetail={onRunDetail}
        refreshing={false}
      />,
    );

    fireEvent.click(screen.getByText("View details"));

    expect(onRunDetail).toHaveBeenCalledWith("run-1");
    expect(screen.getByText(/check: SUCCEEDED/)).toBeTruthy();
  });
});
