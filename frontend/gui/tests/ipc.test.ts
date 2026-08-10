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
    controlSummary: vi.fn().mockResolvedValue({ runs: [], approvals: [] }),
    controlRunDetail: vi.fn().mockResolvedValue({ run: { run_id: "run-1" } }),
    systemReadiness: vi.fn().mockResolvedValue({ profile_id: "linux-x64-cpu" }),
    llmServers: vi.fn().mockResolvedValue({ default_server: "llama-server" }),
    llmModels: vi.fn().mockResolvedValue({ local_models: [] }),
    llmServeStatus: vi.fn().mockResolvedValue({ state: "stopped" }),
    registryValidate: vi.fn().mockResolvedValue({ valid: true }),
    registryPublish: vi.fn().mockResolvedValue({ published: true }),
    registryReindex: vi.fn().mockResolvedValue({ indexed: true }),
    registryRetire: vi.fn().mockResolvedValue({ retired: true }),
    registryTrust: vi.fn().mockResolvedValue({ trust_status: "trusted" }),
    runStatus: vi.fn().mockResolvedValue({ run_id: "run-1" }),
    runList: vi.fn().mockResolvedValue([]),
    approvalList: vi.fn().mockResolvedValue([]),
    approvalDetail: vi.fn().mockResolvedValue({ approval: { approval_id: "ap-1" }, preview: null }),
    approvalApprove: vi.fn().mockResolvedValue({ status: "approved" }),
    approvalReject: vi.fn().mockResolvedValue({ status: "rejected" }),
    proposalGet: vi.fn().mockResolvedValue({ proposal_id: "p1" }),
    proposalPublish: vi.fn().mockResolvedValue({ status: "published" }),
    proposalReject: vi.fn().mockResolvedValue({ status: "rejected" }),
    improvementList: vi.fn().mockResolvedValue([]),
    improvementGet: vi.fn().mockResolvedValue({ improvement_id: "imp-1" }),
    improvementRequestMerge: vi.fn().mockResolvedValue({ approval: { approval_id: "ap-1" } }),
    improvementMerge: vi.fn().mockResolvedValue({ status: "merged" }),
    improvementReject: vi.fn().mockResolvedValue({ status: "rejected" }),
    memorySearch: vi.fn().mockResolvedValue({ semantic: [], episodic: [] }),
    memoryGet: vi.fn().mockResolvedValue({ ref: "pref@1.0.0" }),
    memoryPropose: vi.fn().mockResolvedValue({ proposal_id: "p1" }),
    memoryPublish: vi.fn().mockResolvedValue({ status: "published" }),
    memoryReject: vi.fn().mockResolvedValue({ status: "rejected" }),
    memoryBlock: vi.fn().mockResolvedValue({ trust_status: "blocked" }),
    voiceSessionStart: vi.fn().mockResolvedValue({ voice_session_id: "vs-1", state: "idle" }),
    voiceEvent: vi.fn().mockResolvedValue({ voice_session_id: "vs-1", state: "listening" }),
    voiceSessionClose: vi.fn().mockResolvedValue({ voice_session_id: "vs-1", state: "closed" }),
    voiceSubmitText: vi.fn().mockResolvedValue({ voice_session_id: "vs-1", response_text: "ok" }),
  } as any;
}

describe("registerIpcHandlers", () => {
  it("wires every channel to the matching ProtocolClient method", async () => {
    const { ipcMain, handlers } = makeFakeIpcMain();
    const client = makeFakeClient();

    registerIpcHandlers(ipcMain, client);

    await handlers.get(CHANNELS.controlSummary)?.({});
    expect(client.controlSummary).toHaveBeenCalled();

    await handlers.get(CHANNELS.controlRunDetail)?.({}, "run-1");
    expect(client.controlRunDetail).toHaveBeenCalledWith("run-1");

    await handlers.get(CHANNELS.systemReadiness)?.({});
    expect(client.systemReadiness).toHaveBeenCalled();

    await handlers.get(CHANNELS.llmServers)?.({});
    expect(client.llmServers).toHaveBeenCalled();

    await handlers.get(CHANNELS.llmModels)?.({});
    expect(client.llmModels).toHaveBeenCalled();

    await handlers.get(CHANNELS.llmServeStatus)?.({});
    expect(client.llmServeStatus).toHaveBeenCalled();

    await handlers.get(CHANNELS.registryValidate)?.({}, "/tmp/demo.yaml", "workflows");
    expect(client.registryValidate).toHaveBeenCalledWith("/tmp/demo.yaml", "workflows");

    await handlers.get(CHANNELS.registryPublish)?.({}, "/tmp/demo.yaml", "workflows");
    expect(client.registryPublish).toHaveBeenCalledWith("/tmp/demo.yaml", "workflows");

    await handlers.get(CHANNELS.registryReindex)?.({});
    expect(client.registryReindex).toHaveBeenCalled();

    await handlers.get(CHANNELS.registryRetire)?.({}, "workflows", "demo", "1.0.0");
    expect(client.registryRetire).toHaveBeenCalledWith("workflows", "demo", "1.0.0");

    await handlers.get(CHANNELS.registryTrust)?.({}, "workflows", "demo", "1.0.0", "trusted");
    expect(client.registryTrust).toHaveBeenCalledWith("workflows", "demo", "1.0.0", "trusted");

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

    await handlers.get(CHANNELS.improvementList)?.({});
    expect(client.improvementList).toHaveBeenCalled();

    await handlers.get(CHANNELS.improvementGet)?.({}, "imp-1");
    expect(client.improvementGet).toHaveBeenCalledWith("imp-1");

    await handlers.get(CHANNELS.improvementRequestMerge)?.({}, "imp-1");
    expect(client.improvementRequestMerge).toHaveBeenCalledWith("imp-1");

    await handlers.get(CHANNELS.improvementMerge)?.({}, "imp-1", "ap-1");
    expect(client.improvementMerge).toHaveBeenCalledWith("imp-1", "ap-1");

    await handlers.get(CHANNELS.improvementReject)?.({}, "imp-1", "not ready");
    expect(client.improvementReject).toHaveBeenCalledWith("imp-1", "not ready");

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
