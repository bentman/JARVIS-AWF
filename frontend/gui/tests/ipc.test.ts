import { describe, expect, it, vi } from "vitest";
import { CHANNELS, registerIpcHandlers, type IpcMainLike } from "../src/main/ipc.js";

function makeFakeIpcMain(): { ipcMain: IpcMainLike; handlers: Map<string, (...args: unknown[]) => unknown> } {
  const handlers = new Map<string, (...args: unknown[]) => unknown>();
  const ipcMain: IpcMainLike = {
    handle: (channel, listener) => {
      handlers.set(channel, listener as (...args: unknown[]) => unknown);
    },
  };
  return { ipcMain, handlers };
}

function makeFakeClient() {
  return {
    runStatus: vi.fn().mockResolvedValue({ run_id: "run-1" }),
    runList: vi.fn().mockResolvedValue([]),
    approvalList: vi.fn().mockResolvedValue([]),
    approvalDetail: vi.fn().mockResolvedValue({ approval: { approval_id: "ap-1" }, preview: null }),
    approvalApprove: vi.fn().mockResolvedValue({ status: "approved" }),
    approvalReject: vi.fn().mockResolvedValue({ status: "rejected" }),
    proposalGet: vi.fn().mockResolvedValue({ proposal_id: "p1" }),
    proposalPublish: vi.fn().mockResolvedValue({ status: "published" }),
    proposalReject: vi.fn().mockResolvedValue({ status: "rejected" }),
    memorySearch: vi.fn().mockResolvedValue({ semantic: [], episodic: [] }),
    memoryGet: vi.fn().mockResolvedValue({ ref: "pref@1.0.0" }),
    memoryPropose: vi.fn().mockResolvedValue({ proposal_id: "p1" }),
    memoryPublish: vi.fn().mockResolvedValue({ status: "published" }),
    memoryReject: vi.fn().mockResolvedValue({ status: "rejected" }),
    memoryBlock: vi.fn().mockResolvedValue({ trust_status: "blocked" }),
  } as any;
}

describe("registerIpcHandlers", () => {
  it("wires every channel to the matching ProtocolClient method", async () => {
    const { ipcMain, handlers } = makeFakeIpcMain();
    const client = makeFakeClient();

    registerIpcHandlers(ipcMain, client);

    await handlers.get(CHANNELS.runStatus)?.({}, "run-1");
    expect(client.runStatus).toHaveBeenCalledWith("run-1");

    await handlers.get(CHANNELS.approvalApprove)?.({}, "ap-1");
    expect(client.approvalApprove).toHaveBeenCalledWith("ap-1");

    await handlers.get(CHANNELS.approvalReject)?.({}, "ap-1", "not safe");
    expect(client.approvalReject).toHaveBeenCalledWith("ap-1", "not safe");

    await handlers.get(CHANNELS.runList)?.({});
    expect(client.runList).toHaveBeenCalled();

    await handlers.get(CHANNELS.approvalList)?.({});
    expect(client.approvalList).toHaveBeenCalled();

    await handlers.get(CHANNELS.approvalDetail)?.({}, "ap-1");
    expect(client.approvalDetail).toHaveBeenCalledWith("ap-1");

    await handlers.get(CHANNELS.proposalGet)?.({}, "p1");
    expect(client.proposalGet).toHaveBeenCalledWith("p1");

    await handlers.get(CHANNELS.proposalPublish)?.({}, "p1", "abc");
    expect(client.proposalPublish).toHaveBeenCalledWith("p1", "abc");

    await handlers.get(CHANNELS.proposalReject)?.({}, "p1", "not useful");
    expect(client.proposalReject).toHaveBeenCalledWith("p1", "not useful");

    await handlers.get(CHANNELS.memorySearch)?.({}, "targeted", "default@1.0.0");
    expect(client.memorySearch).toHaveBeenCalledWith("targeted", "default@1.0.0");

    await handlers.get(CHANNELS.memoryGet)?.({}, "pref@1.0.0");
    expect(client.memoryGet).toHaveBeenCalledWith("pref@1.0.0");

    await handlers.get(CHANNELS.memoryPublish)?.({}, "p1", "abc");
    expect(client.memoryPublish).toHaveBeenCalledWith("p1", "abc");

    await handlers.get(CHANNELS.memoryReject)?.({}, "p1", "not useful");
    expect(client.memoryReject).toHaveBeenCalledWith("p1", "not useful");

    await handlers.get(CHANNELS.memoryBlock)?.({}, "pref@1.0.0");
    expect(client.memoryBlock).toHaveBeenCalledWith("pref@1.0.0");
  });
});
