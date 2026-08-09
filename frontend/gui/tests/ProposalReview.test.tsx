import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import React from "react";
import { describe, expect, it, vi } from "vitest";
import { ProposalReview } from "../src/renderer/ProposalReview.js";

describe("ProposalReview", () => {
  it("loads a proposal and publishes with its current digest", async () => {
    const proposal = {
      proposal_id: "p1",
      name: "demo",
      version: "0.1.0",
      status: "draft" as const,
      draft_digest: "abc",
      draft_path: "data/proposals/workflows/p1/demo/0.1.0.yaml",
      summary: "summary",
      content: "apiVersion: awf/v1\n",
    };
    const onProposalGet = vi.fn().mockResolvedValue(proposal);
    const onProposalPublish = vi.fn().mockResolvedValue({});

    render(
      <ProposalReview
        onProposalGet={onProposalGet}
        onProposalPublish={onProposalPublish}
        onProposalReject={vi.fn()}
      />,
    );

    fireEvent.change(screen.getByLabelText("Proposal id"), { target: { value: "p1" } });
    fireEvent.click(screen.getByText("Load proposal"));

    expect(await screen.findByText("demo@0.1.0")).toBeTruthy();
    fireEvent.click(screen.getByText("Publish"));

    await waitFor(() => expect(onProposalPublish).toHaveBeenCalledWith("p1", "abc"));
  });

  it("rejects with an operator reason", async () => {
    const proposal = {
      proposal_id: "p1",
      name: "demo",
      version: "0.1.0",
      status: "draft" as const,
      draft_digest: "abc",
      draft_path: "data/proposals/workflows/p1/demo/0.1.0.yaml",
      summary: "summary",
      content: "apiVersion: awf/v1\n",
    };
    const onProposalReject = vi.fn().mockResolvedValue({});

    render(
      <ProposalReview
        onProposalGet={vi.fn().mockResolvedValue(proposal)}
        onProposalPublish={vi.fn()}
        onProposalReject={onProposalReject}
      />,
    );

    fireEvent.change(screen.getByLabelText("Proposal id"), { target: { value: "p1" } });
    fireEvent.click(screen.getByText("Load proposal"));
    await screen.findByText("demo@0.1.0");
    fireEvent.change(screen.getByLabelText("Reject reason"), { target: { value: "not useful" } });
    fireEvent.click(screen.getByText("Reject"));

    await waitFor(() => expect(onProposalReject).toHaveBeenCalledWith("p1", "not useful"));
  });
});
