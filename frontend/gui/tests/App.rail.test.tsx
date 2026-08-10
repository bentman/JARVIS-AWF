import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import React from "react";
import { describe, expect, it, vi } from "vitest";
import { App } from "../src/renderer/App.js";

describe("App rail navigation (ADR-0025 control-center shell)", () => {
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

  it("raises a count badge on the Approvals rail item when approvals are pending", async () => {
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
    expect(screen.queryByRole("button", { name: "Registry" })).toBeNull();
  });
});
