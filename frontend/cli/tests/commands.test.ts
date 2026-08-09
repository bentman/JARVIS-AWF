import { describe, expect, it, vi } from "vitest";
import { CommandError, dispatchCommand, type CommandClient } from "../src/commands.js";
import { DEFAULT_SETTINGS } from "../src/settings.js";

function makeFakeClient(overrides: Partial<CommandClient> = {}): CommandClient {
  return {
    runStart: vi.fn().mockResolvedValue({ run_id: "run-1", status: "SUCCEEDED" }),
    runStatus: vi.fn().mockResolvedValue({ run_id: "run-1", status: "SUCCEEDED", steps: [] }),
    runList: vi.fn().mockResolvedValue([]),
    runResume: vi.fn().mockResolvedValue([]),
    approvalList: vi.fn().mockResolvedValue([]),
    approvalApprove: vi.fn().mockResolvedValue({ approval_id: "ap-1", status: "approved" }),
    approvalReject: vi.fn().mockResolvedValue({ approval_id: "ap-1", status: "rejected" }),
    artifactList: vi.fn().mockResolvedValue([]),
    secretListNames: vi.fn().mockResolvedValue([]),
    registryList: vi.fn().mockResolvedValue([]),
    workflowAuthorDraft: vi.fn().mockResolvedValue({ proposal_id: "p1", status: "draft" }),
    proposalGet: vi.fn().mockResolvedValue({ proposal_id: "p1", status: "draft" }),
    proposalUpdate: vi.fn().mockResolvedValue({ proposal_id: "p1", status: "draft" }),
    proposalPublish: vi.fn().mockResolvedValue({ proposal: { proposal_id: "p1", status: "published" } }),
    proposalReject: vi.fn().mockResolvedValue({ proposal_id: "p1", status: "rejected" }),
    ...overrides,
  } as CommandClient;
}

describe("dispatchCommand", () => {
  it("/help returns the built-in command list as text", async () => {
    const client = makeFakeClient();
    const result = await dispatchCommand(client, "/help", DEFAULT_SETTINGS);
    expect(result.kind).toBe("text");
    if (result.kind === "text") expect(result.text).toContain("/run <workflow>@<version>");
  });

  it("/run calls runStart with the workflow ref", async () => {
    const client = makeFakeClient();
    const result = await dispatchCommand(client, "/run demo@1.0.0", DEFAULT_SETTINGS);
    expect(client.runStart).toHaveBeenCalledWith("demo@1.0.0");
    expect(result).toEqual({ kind: "json", data: { run_id: "run-1", status: "SUCCEEDED" } });
  });

  it("/run without an argument raises CommandError", async () => {
    const client = makeFakeClient();
    await expect(dispatchCommand(client, "/run", DEFAULT_SETTINGS)).rejects.toBeInstanceOf(CommandError);
  });

  it("/status calls runStatus with the run id", async () => {
    const client = makeFakeClient();
    await dispatchCommand(client, "/status run-1", DEFAULT_SETTINGS);
    expect(client.runStatus).toHaveBeenCalledWith("run-1");
  });

  it("/runs calls runList", async () => {
    const client = makeFakeClient();
    await dispatchCommand(client, "/runs", DEFAULT_SETTINGS);
    expect(client.runList).toHaveBeenCalled();
  });

  it("/resume calls runResume", async () => {
    const client = makeFakeClient();
    await dispatchCommand(client, "/resume", DEFAULT_SETTINGS);
    expect(client.runResume).toHaveBeenCalled();
  });

  it("/approvals calls approvalList", async () => {
    const client = makeFakeClient();
    await dispatchCommand(client, "/approvals", DEFAULT_SETTINGS);
    expect(client.approvalList).toHaveBeenCalled();
  });

  it("/approve calls approvalApprove with the id", async () => {
    const client = makeFakeClient();
    await dispatchCommand(client, "/approve ap-1", DEFAULT_SETTINGS);
    expect(client.approvalApprove).toHaveBeenCalledWith("ap-1");
  });

  it("/reject joins remaining args as the reason", async () => {
    const client = makeFakeClient();
    await dispatchCommand(client, "/reject ap-1 not safe enough", DEFAULT_SETTINGS);
    expect(client.approvalReject).toHaveBeenCalledWith("ap-1", "not safe enough");
  });

  it("/reject without a reason raises CommandError", async () => {
    const client = makeFakeClient();
    await expect(dispatchCommand(client, "/reject ap-1", DEFAULT_SETTINGS)).rejects.toBeInstanceOf(CommandError);
  });

  it("/artifacts calls artifactList with the run id", async () => {
    const client = makeFakeClient();
    await dispatchCommand(client, "/artifacts run-1", DEFAULT_SETTINGS);
    expect(client.artifactList).toHaveBeenCalledWith("run-1");
  });

  it.each([
    ["/agents", "agents"],
    ["/skills", "skills"],
    ["/workflows", "workflows"],
    ["/capabilities", "capabilities"],
    ["/mcp", "mcp"],
    ["/model", "model-profiles"],
    ["/voices", "voice-profiles"],
  ])("%s calls registryList(%s)", async (command, kind) => {
    const client = makeFakeClient();
    await dispatchCommand(client, command, DEFAULT_SETTINGS);
    expect(client.registryList).toHaveBeenCalledWith(kind);
  });

  it("/secrets calls secretListNames (names only)", async () => {
    const client = makeFakeClient();
    await dispatchCommand(client, "/secrets", DEFAULT_SETTINGS);
    expect(client.secretListNames).toHaveBeenCalled();
  });

  it("/author-workflow calls workflowAuthorDraft with the objective text", async () => {
    const client = makeFakeClient();
    await dispatchCommand(client, "/author-workflow make a demo workflow", DEFAULT_SETTINGS);
    expect(client.workflowAuthorDraft).toHaveBeenCalledWith({ objective: "make a demo workflow" });
  });

  it("/proposal calls proposalGet", async () => {
    const client = makeFakeClient();
    await dispatchCommand(client, "/proposal p1", DEFAULT_SETTINGS);
    expect(client.proposalGet).toHaveBeenCalledWith("p1");
  });

  it("/proposal-publish calls proposalPublish", async () => {
    const client = makeFakeClient();
    await dispatchCommand(client, "/proposal-publish p1 abc", DEFAULT_SETTINGS);
    expect(client.proposalPublish).toHaveBeenCalledWith("p1", "abc");
  });

  it("/proposal-reject joins remaining args as reason", async () => {
    const client = makeFakeClient();
    await dispatchCommand(client, "/proposal-reject p1 not useful", DEFAULT_SETTINGS);
    expect(client.proposalReject).toHaveBeenCalledWith("p1", "not useful");
  });

  it("/settings, /theme, /keybindings never touch the protocol client", async () => {
    const client = makeFakeClient();
    const settings = { ...DEFAULT_SETTINGS, theme: "dark" as const };

    const settingsResult = await dispatchCommand(client, "/settings", settings);
    const themeResult = await dispatchCommand(client, "/theme", settings);
    const keybindingsResult = await dispatchCommand(client, "/keybindings", settings);

    expect(settingsResult).toEqual({ kind: "json", data: settings });
    expect(themeResult).toEqual({ kind: "json", data: { theme: "dark" } });
    expect(keybindingsResult).toEqual({ kind: "json", data: settings.keybindings });
    for (const fn of Object.values(client)) expect(fn).not.toHaveBeenCalled();
  });

  it("/clear returns a clear result", async () => {
    const client = makeFakeClient();
    const result = await dispatchCommand(client, "/clear", DEFAULT_SETTINGS);
    expect(result).toEqual({ kind: "clear" });
  });

  it("/quit returns a quit result", async () => {
    const client = makeFakeClient();
    const result = await dispatchCommand(client, "/quit", DEFAULT_SETTINGS);
    expect(result).toEqual({ kind: "quit" });
  });

  it("rejects an unknown command", async () => {
    const client = makeFakeClient();
    await expect(dispatchCommand(client, "/not-a-real-command", DEFAULT_SETTINGS)).rejects.toBeInstanceOf(
      CommandError,
    );
  });

  it("rejects input that is not a slash command", async () => {
    const client = makeFakeClient();
    await expect(dispatchCommand(client, "plain text", DEFAULT_SETTINGS)).rejects.toBeInstanceOf(CommandError);
  });
});
