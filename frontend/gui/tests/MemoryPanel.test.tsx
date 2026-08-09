import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import React from "react";
import { describe, expect, it, vi } from "vitest";
import { MemoryPanel } from "../src/renderer/MemoryPanel.js";

describe("MemoryPanel", () => {
  it("searches memory and exposes manual block/publish/reject actions", async () => {
    const onMemorySearch = vi.fn().mockResolvedValue({
      semantic: [{ ref: "pref@1.0.0", score: 1, confidence: 0.9, object: {} }],
      episodic: [{ event_id: "e1", reason_code: "targeted-check" }],
    });
    const onMemoryBlock = vi.fn().mockResolvedValue({});
    const onMemoryPublish = vi.fn().mockResolvedValue({});
    const onMemoryReject = vi.fn().mockResolvedValue({});

    render(
      <MemoryPanel
        onMemorySearch={onMemorySearch}
        onMemoryBlock={onMemoryBlock}
        onMemoryPublish={onMemoryPublish}
        onMemoryReject={onMemoryReject}
      />,
    );

    fireEvent.change(screen.getByLabelText("Search memory"), { target: { value: "targeted" } });
    fireEvent.click(screen.getByText("Search"));

    await waitFor(() => expect(onMemorySearch).toHaveBeenCalledWith("targeted"));
    expect(await screen.findByText(/pref@1.0.0/)).toBeTruthy();

    fireEvent.click(screen.getByText("Block"));
    await waitFor(() => expect(onMemoryBlock).toHaveBeenCalledWith("pref@1.0.0"));

    fireEvent.change(screen.getByLabelText("Proposal id"), { target: { value: "p1" } });
    fireEvent.change(screen.getByLabelText("Digest"), { target: { value: "abc" } });
    fireEvent.click(screen.getByText("Publish memory"));
    await waitFor(() => expect(onMemoryPublish).toHaveBeenCalledWith("p1", "abc"));

    fireEvent.change(screen.getByLabelText("Reject reason"), { target: { value: "not useful" } });
    fireEvent.click(screen.getByText("Reject memory"));
    await waitFor(() => expect(onMemoryReject).toHaveBeenCalledWith("p1", "not useful"));
  });
});
