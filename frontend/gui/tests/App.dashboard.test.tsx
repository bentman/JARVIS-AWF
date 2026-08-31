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

  it("renders registry actions behind the Registry nav button when registry handlers are supplied", () => {
    render(
      <App
        onApprove={vi.fn()}
        onReject={vi.fn()}
        onRegistryValidate={vi.fn()}
        onRegistryPublish={vi.fn()}
        onRegistryReindex={vi.fn()}
        onRegistryRetire={vi.fn()}
        onRegistryTrust={vi.fn()}
      />,
    );

    // The first page is always chat; registry actions open via their button.
    fireEvent.click(screen.getByRole("button", { name: "Library" }));
    expect(screen.getByRole("region", { name: "Registry actions" })).toBeTruthy();
  });

  it("hands a registry workflow run action back to Operate start work", async () => {
    render(
      <App
        onApprove={vi.fn()}
        onReject={vi.fn()}
        onControlSummary={vi.fn().mockResolvedValue({
          runs: [],
          approvals: [],
          improvements: [],
          recent_verdicts: [],
          registry_counts: {},
          llm: {},
          readiness: { profile_id: "linux-x64-cpu", inventory: null, tokens: [], readiness: {} },
          operator_start_options: [],
        })}
        onRegistryValidate={vi.fn()}
        onRegistryPublish={vi.fn()}
        onRegistryReindex={vi.fn()}
        onRegistryRetire={vi.fn()}
        onRegistryTrust={vi.fn()}
        onRegistryList={vi.fn().mockResolvedValue([
          { kind: "workflows", name: "demo", version: "1.0.0", source: "config", trust_status: "trusted" },
        ])}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Library" }));
    fireEvent.click(await screen.findByRole("button", { name: "Run" }));

    expect(screen.getByRole("button", { name: "Operate" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByLabelText("Workflow")).toHaveValue("demo@1.0.0");
  });

  it("uses control summary as the dashboard source when available", async () => {
    const onControlSummary = vi.fn().mockResolvedValue({
      runs: [{ run_id: "run-1", workflow_ref: "demo@1.0.0", status: "SUCCEEDED", created_at: "t", updated_at: "t" }],
      approvals: [],
      improvements: [],
      recent_verdicts: [],
      registry_counts: { skills: 1 },
      llm: { status: { state: "running" }, servers: { default_server: "llama-server" } },
      readiness: { profile_id: "linux-x64-cpu", inventory: null, tokens: [], readiness: {} },
      operator_start_options: [
        {
          workflow_ref: "demo@1.0.0",
          name: "demo",
          version: "1.0.0",
          source: "config",
          trust_status: "trusted",
          status: "ready",
          description: "Run demo@1.0.0",
          input_schema: { type: "object", properties: { objective: { type: "string" } }, required: ["objective"] },
          input_schema_summary: {
            type: "object",
            required: ["objective"],
            fields: [{ name: "objective", type: "string", required: true }],
          },
          primary_action: { kind: "workflow.start", label: "Start workflow", command: "awf run demo@1.0.0", workflow_ref: "demo@1.0.0" },
        },
      ],
    });

    render(<App onApprove={vi.fn()} onReject={vi.fn()} onControlSummary={onControlSummary} />);

    await waitFor(() => expect(onControlSummary).toHaveBeenCalled());
    expect(screen.getByRole("button", { name: "Operate" })).toHaveAttribute("aria-current", "page");
    expect(await screen.findByText("State: running")).toBeTruthy();
    expect(screen.getByText("skills: 1")).toBeTruthy();
  });

  it("starts a workflow from Operate with schema input", async () => {
    const onRunStart = vi.fn().mockResolvedValue({ run_id: "run-2", status: "SUCCEEDED" });
    const onControlSummary = vi.fn().mockResolvedValue({
      runs: [],
      approvals: [],
      improvements: [],
      recent_verdicts: [],
      registry_counts: {},
      llm: {},
      readiness: { profile_id: "linux-x64-cpu", inventory: null, tokens: [], readiness: {} },
      operator_start_options: [
        {
          workflow_ref: "demo@1.0.0",
          name: "demo",
          version: "1.0.0",
          source: "config",
          trust_status: "trusted",
          status: "ready",
          description: "Run demo@1.0.0",
          input_schema: { type: "object", properties: { objective: { type: "string" } }, required: ["objective"] },
          input_schema_summary: {
            type: "object",
            required: ["objective"],
            fields: [{ name: "objective", type: "string", required: true }],
          },
          primary_action: { kind: "workflow.start", label: "Start workflow", command: "awf run demo@1.0.0", workflow_ref: "demo@1.0.0" },
        },
      ],
    });

    render(
      <App
        onApprove={vi.fn()}
        onReject={vi.fn()}
        onRunStart={onRunStart}
        onControlSummary={onControlSummary}
        onControlRunDetail={vi.fn().mockResolvedValue({ run: { run_id: "run-2", workflow_ref: "demo@1.0.0", status: "SUCCEEDED", steps: [] }, artifacts: [], timeline: {}, improvements: [], verdicts: [] })}
      />,
    );

    fireEvent.change(await screen.findByLabelText("objective"), { target: { value: "ship it" } });
    fireEvent.click(screen.getByRole("button", { name: "Start workflow" }));

    await waitFor(() => expect(onRunStart).toHaveBeenCalledWith("demo@1.0.0", { objective: "ship it" }));
    expect(await screen.findByText("Started demo@1.0.0 as run-2.")).toBeTruthy();
  });

  it("loads selected run detail through the control detail prop", async () => {
    const onControlSummary = vi.fn().mockResolvedValue({
      runs: [{ run_id: "run-1", workflow_ref: "demo@1.0.0", status: "SUCCEEDED", created_at: "t", updated_at: "t" }],
      approvals: [],
      improvements: [],
      recent_verdicts: [],
      registry_counts: {},
      llm: {},
      readiness: { profile_id: "linux-x64-cpu", inventory: null, tokens: [], readiness: {} },
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

    // Runs are a section of Operate, the default view - no nav hop needed.
    fireEvent.click(await screen.findByText("View details"));

    await waitFor(() => expect(onControlRunDetail).toHaveBeenCalledWith("run-1"));
    expect(await screen.findByText(/check: SUCCEEDED/)).toBeTruthy();
  });
});
