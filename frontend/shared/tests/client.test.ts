import { describe, expect, it } from "vitest";
import { ProtocolClient } from "../src/client.js";
import { ProtocolError } from "../src/types.js";
import { FakeTransport } from "./fake_transport.js";

function setup() {
  const transport = new FakeTransport();
  const client = new ProtocolClient(transport);
  return { transport, client };
}

describe("ProtocolClient", () => {
  it("sends a well-formed JSON-RPC request for runStart", () => {
    const { transport, client } = setup();
    void client.runStart("demo@1.0.0", { objective: "x" });

    const request = transport.lastRequest();
    expect(request.jsonrpc).toBe("2.0");
    expect(request.method).toBe("awf/run.start");
    expect(request.params).toEqual({ workflow: "demo@1.0.0", input: { objective: "x" } });
  });

  it("resolves the matching promise by request id", async () => {
    const { transport, client } = setup();
    const promise = client.runStatus("run-1");
    const request = transport.lastRequest();

    transport.emit({ jsonrpc: "2.0", id: request.id, result: { run_id: "run-1", status: "SUCCEEDED" } });

    const result = await promise;
    expect(result.run_id).toBe("run-1");
  });

  it("rejects with ProtocolError when the response carries an error", async () => {
    const { transport, client } = setup();
    const promise = client.runStatus("does-not-exist");
    const request = transport.lastRequest();

    transport.emit({ jsonrpc: "2.0", id: request.id, error: { code: -32000, message: "no such run" } });

    await expect(promise).rejects.toBeInstanceOf(ProtocolError);
    await expect(promise).rejects.toThrow("no such run");
  });

  it("ignores responses whose id does not match any pending request", async () => {
    const { transport, client } = setup();
    const promise = client.runStatus("run-1");
    const request = transport.lastRequest();

    transport.emit({ jsonrpc: "2.0", id: 9999, result: { unrelated: true } });
    transport.emit({ jsonrpc: "2.0", id: request.id, result: { run_id: "run-1", status: "SUCCEEDED" } });

    const result = await promise;
    expect(result.run_id).toBe("run-1");
  });

  it("rejects all pending requests when the core process exits", async () => {
    const { transport, client } = setup();
    const promise = client.runStatus("run-1");

    transport.emitExit(1);

    await expect(promise).rejects.toThrow(/exited/);
  });

  it("increments request ids across calls", () => {
    const { transport, client } = setup();
    void client.runList();
    const first = transport.lastRequest().id;
    void client.runList();
    const second = transport.lastRequest().id;

    expect(second).toBe(first + 1);
  });

  it("builds correct params for approval and artifact methods", () => {
    const { transport, client } = setup();

    void client.approvalApprove("ap-1", { channel: "voice", riskClass: "R2" });
    expect(transport.lastRequest().params).toEqual({ approvalId: "ap-1", channel: "voice", riskClass: "R2" });

    void client.approvalReject("ap-1", "not safe");
    expect(transport.lastRequest().params).toEqual({ approvalId: "ap-1", reason: "not safe" });

    void client.approvalDetail("ap-1");
    expect(transport.lastRequest().method).toBe("awf/approval.detail");
    expect(transport.lastRequest().params).toEqual({ approvalId: "ap-1" });

    void client.machineActionPreview("ap-1");
    expect(transport.lastRequest().method).toBe("awf/machine.actionPreview");
    expect(transport.lastRequest().params).toEqual({ approvalId: "ap-1" });

    void client.artifactRead("art-1");
    expect(transport.lastRequest().params).toEqual({ artifactId: "art-1" });

    void client.registryGet("capabilities", "read_file", "1.0.0");
    expect(transport.lastRequest().params).toEqual({
      kind: "capabilities",
      name: "read_file",
      version: "1.0.0",
    });

    void client.registryPublish("/tmp/demo.yaml", "workflows");
    expect(transport.lastRequest().params).toEqual({ path: "/tmp/demo.yaml", kind: "workflows" });
  });

  it("builds correct params for proposal methods", () => {
    const { transport, client } = setup();

    void client.workflowAuthorDraft({ objective: "make demo", name: "demo" });
    expect(transport.lastRequest().method).toBe("awf/workflow.authorDraft");
    expect(transport.lastRequest().params).toEqual({ objective: "make demo", name: "demo" });

    void client.proposalGet("p1");
    expect(transport.lastRequest().params).toEqual({ proposalId: "p1" });

    void client.proposalUpdate("p1", "yaml", "edited");
    expect(transport.lastRequest().params).toEqual({ proposalId: "p1", content: "yaml", summary: "edited" });

    void client.proposalPublish("p1", "abc");
    expect(transport.lastRequest().params).toEqual({ proposalId: "p1", digest: "abc" });

    void client.proposalReject("p1", "not useful");
    expect(transport.lastRequest().params).toEqual({ proposalId: "p1", reason: "not useful" });
  });

  it("builds correct params for improvement methods", () => {
    const { transport, client } = setup();

    void client.improvementList("ready_for_review");
    expect(transport.lastRequest().method).toBe("awf/improvement.list");
    expect(transport.lastRequest().params).toEqual({ status: "ready_for_review" });

    void client.improvementGet("imp-1");
    expect(transport.lastRequest().params).toEqual({ improvementId: "imp-1" });

    void client.improvementPrepare("run-1", "summary");
    expect(transport.lastRequest().params).toEqual({ runId: "run-1", summary: "summary" });

    void client.improvementMarkReady("imp-1", "verdict-1", ["test-1"]);
    expect(transport.lastRequest().params).toEqual({
      improvementId: "imp-1",
      verdictArtifactId: "verdict-1",
      validationArtifactIds: ["test-1"],
    });

    void client.improvementRequestMerge("imp-1");
    expect(transport.lastRequest().params).toEqual({ improvementId: "imp-1" });

    void client.improvementMerge("imp-1", "ap-1");
    expect(transport.lastRequest().params).toEqual({ improvementId: "imp-1", approvalId: "ap-1" });

    void client.improvementReject("imp-1", "not ready");
    expect(transport.lastRequest().params).toEqual({ improvementId: "imp-1", reason: "not ready" });
  });

  it("builds correct params for memory, session, and episodic methods", () => {
    const { transport, client } = setup();

    void client.memorySearch("targeted tests");
    expect(transport.lastRequest().method).toBe("awf/memory.search");
    expect(transport.lastRequest().params).toEqual({ query: "targeted tests", profile: "default@1.0.0" });

    void client.memoryGet("pref@1.0.0");
    expect(transport.lastRequest().params).toEqual({ ref: "pref@1.0.0" });

    void client.memoryPublish("p1", "abc");
    expect(transport.lastRequest().params).toEqual({ proposalId: "p1", digest: "abc" });

    void client.sessionStart("demo");
    expect(transport.lastRequest().params).toEqual({ title: "demo", expiresAt: undefined });

    void client.episodicTimeline("run-1");
    expect(transport.lastRequest().params).toEqual({ runId: "run-1" });
  });

  it("builds correct params for voice session methods", () => {
    const { transport, client } = setup();

    void client.voiceSessionStart("voice", true);
    expect(transport.lastRequest().method).toBe("awf/voice.sessionStart");
    expect(transport.lastRequest().params).toEqual({ title: "voice", wakeEnabled: true });

    void client.voiceEvent("vs-1", "stt.final", { text: "hello" }, "turn-1");
    expect(transport.lastRequest().method).toBe("awf/voice.event");
    expect(transport.lastRequest().params).toEqual({
      voiceSessionId: "vs-1",
      frameType: "stt.final",
      payload: { text: "hello" },
      turnId: "turn-1",
    });

    void client.voiceSubmitText({
      voiceSessionId: "vs-1",
      text: "hello",
      workflowRef: "demo@1.0.0",
      voiceProfileRef: "narrator@1.0.0",
      turnId: "turn-1",
    });
    expect(transport.lastRequest().method).toBe("awf/voice.submitText");
    expect(transport.lastRequest().params).toEqual({
      voiceSessionId: "vs-1",
      text: "hello",
      workflowRef: "demo@1.0.0",
      voiceProfileRef: "narrator@1.0.0",
      turnId: "turn-1",
    });

    void client.voiceSessionClose("vs-1", "done");
    expect(transport.lastRequest().method).toBe("awf/voice.sessionClose");
    expect(transport.lastRequest().params).toEqual({ voiceSessionId: "vs-1", reason: "done" });
  });

  it("builds correct params for control center and readiness methods", () => {
    const { transport, client } = setup();

    void client.controlSummary();
    expect(transport.lastRequest().method).toBe("awf/control.summary");
    expect(transport.lastRequest().params).toEqual({});

    void client.controlRunDetail("run-1");
    expect(transport.lastRequest().method).toBe("awf/control.runDetail");
    expect(transport.lastRequest().params).toEqual({ runId: "run-1" });

    void client.systemReadiness();
    expect(transport.lastRequest().method).toBe("awf/system.readiness");
    expect(transport.lastRequest().params).toEqual({});

    void client.llmServers();
    expect(transport.lastRequest().method).toBe("awf/llm.servers");
    expect(transport.lastRequest().params).toEqual({});

    void client.llmModels();
    expect(transport.lastRequest().method).toBe("awf/llm.models");
    expect(transport.lastRequest().params).toEqual({});

    void client.llmServeStatus();
    expect(transport.lastRequest().method).toBe("awf/llm.serveStatus");
    expect(transport.lastRequest().params).toEqual({});
  });
});
