import { fireEvent, render, screen } from "@testing-library/react";
import React from "react";
import { describe, expect, it, vi } from "vitest";
import { ApprovalConfirmation } from "../src/renderer/ApprovalConfirmation.js";

describe("ApprovalConfirmation", () => {
  it("displays the exact action digest and risk class", () => {
    render(
      <ApprovalConfirmation
        approvalId="ap-1"
        actionDigest="sha256:deadbeef"
        riskClass="R2"
        voiceConfirmed={false}
        onApprove={vi.fn()}
        onReject={vi.fn()}
      />,
    );
    expect(screen.getByText("sha256:deadbeef")).toBeTruthy();
    expect(screen.getByText(/R2/)).toBeTruthy();
  });

  it("displays the machine action preview when supplied", () => {
    render(
      <ApprovalConfirmation
        approvalId="ap-1"
        actionDigest="sha256:deadbeef"
        riskClass="R2"
        preview={{
          machine_action: {
            kind: "agent_node",
            capability_ref: "demo_capability@1.0.0",
            target: { adapter: "codex" },
          },
          machine_action_digest: "sha256:deadbeef",
        }}
        voiceConfirmed={false}
        onApprove={vi.fn()}
        onReject={vi.fn()}
      />,
    );

    expect(screen.getByLabelText("Action preview")).toHaveTextContent("agent_node demo_capability@1.0.0");
    expect(screen.getByText(/codex/)).toBeTruthy();
  });

  it("R2 approval attempted by voice alone is refused - onApprove is never auto-called", () => {
    const onApprove = vi.fn();
    render(
      <ApprovalConfirmation
        approvalId="ap-1"
        actionDigest="sha256:deadbeef"
        riskClass="R2"
        voiceConfirmed={true}
        onApprove={onApprove}
        onReject={vi.fn()}
      />,
    );
    expect(onApprove).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent(/cannot approve/i);
  });

  it("R2 approval proceeds only after a real on-screen click", () => {
    const onApprove = vi.fn();
    render(
      <ApprovalConfirmation
        approvalId="ap-1"
        actionDigest="sha256:deadbeef"
        riskClass="R2"
        voiceConfirmed={true}
        onApprove={onApprove}
        onReject={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByText("Approve"));
    expect(onApprove).toHaveBeenCalledWith("ap-1");
  });

  it("R0 approval acknowledged by voice alone auto-approves with no click needed", () => {
    const onApprove = vi.fn();
    render(
      <ApprovalConfirmation
        approvalId="ap-2"
        actionDigest="sha256:cafef00d"
        riskClass="R0"
        voiceConfirmed={true}
        onApprove={onApprove}
        onReject={vi.fn()}
      />,
    );
    expect(onApprove).toHaveBeenCalledWith("ap-2");
  });

  it("reject button calls onReject with a reason", () => {
    const onReject = vi.fn();
    render(
      <ApprovalConfirmation
        approvalId="ap-1"
        actionDigest="sha256:deadbeef"
        riskClass="R2"
        voiceConfirmed={false}
        onApprove={vi.fn()}
        onReject={onReject}
      />,
    );
    fireEvent.click(screen.getByText("Reject"));
    expect(onReject).toHaveBeenCalledWith("ap-1", expect.any(String));
  });
});
