import { fireEvent, render, screen, waitFor } from "@testing-library/react";
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
            inventory: { gpu_vendor: "nvidia" },
            tokens: ["cuda_available"],
            readiness: { stt: { device: "cpu", ready: true, reason: "available" } },
          },
          doctor: {
            status: "warn",
            checks: [{ name: "frontend", status: "warn", summary: "npm missing", detail: {}, next_action: "install npm" }],
            next_actions: ["install npm"],
            first_run_command: 'awf run assistant-default@1.0.0 --objective "check the system"',
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
    expect(screen.getByText("Tokens: cuda_available")).toBeTruthy();
    expect(screen.getByText(/"gpu_vendor": "nvidia"/)).toBeTruthy();
    expect(screen.getByText("Operator readiness")).toBeTruthy();
    expect(screen.getByText(/frontend: npm missing/)).toBeTruthy();
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
          outcome: {
            run_id: "run-1",
            workflow_ref: "demo@1.0.0",
            status: "SUCCEEDED",
            response_text: "Workflow produced a useful result.",
            evidence: [],
            artifacts: [],
            failures: [],
            pending_approvals: [],
            next_action: "No operator action required.",
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
    expect(screen.getByText("Workflow produced a useful result.")).toBeTruthy();
    expect(screen.getByText("Next: No operator action required.")).toBeTruthy();
  });

  it("shows the run detail timeline and lets an operator view an artifact's content", async () => {
    const onArtifactRead = vi.fn().mockResolvedValue({
      artifact_id: "artifact-1",
      run_id: "run-1",
      step_id: "s1",
      sha256: "sha256:abc",
      relative_path: "diff.patch",
      media_type: "text/x-diff",
      artifact_type: "diff",
      complete: 1,
      created_at: "t",
      content: "--- a\n+++ b\n",
    });
    render(
      <Dashboard
        runs={[]}
        approvals={[]}
        selectedRunDetail={{
          run: { run_id: "run-1", workflow_ref: "demo@1.0.0", status: "SUCCEEDED", steps: [] },
          artifacts: [
            {
              artifact_id: "artifact-1",
              run_id: "run-1",
              step_id: "s1",
              sha256: "sha256:abc",
              relative_path: "diff.patch",
              media_type: "text/x-diff",
              artifact_type: "diff",
              complete: 1,
              created_at: "t",
            },
          ],
          timeline: { events: [{ step: "s1" }] },
          improvements: [],
          verdicts: [],
        }}
        onRefresh={vi.fn()}
        onArtifactRead={onArtifactRead}
        refreshing={false}
      />,
    );

    expect(screen.getByText("Timeline")).toBeTruthy();
    expect(screen.getByText("Advanced/raw event data")).toBeTruthy();
    expect(screen.getByText(/"step": "s1"/)).not.toBeVisible();

    fireEvent.click(screen.getByText("View"));
    await waitFor(() => expect(onArtifactRead).toHaveBeenCalledWith("artifact-1"));
    expect(await screen.findByLabelText("Artifact content")).toHaveTextContent("--- a");
  });

  it("loads and renders the LLM model catalog on demand", async () => {
    const onLlmModels = vi.fn().mockResolvedValue({
      local_models: [{ name: "llama-3-8b" }],
      ollama_models: [],
    });
    render(
      <Dashboard
        runs={[]}
        approvals={[]}
        onRefresh={vi.fn()}
        onLlmModels={onLlmModels}
        refreshing={false}
      />,
    );

    fireEvent.click(screen.getByText("Load models"));
    await waitFor(() => expect(onLlmModels).toHaveBeenCalled());
    expect(await screen.findByText(/llama-3-8b/)).toBeTruthy();
  });
});
