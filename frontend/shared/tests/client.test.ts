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

    void client.approvalReject("ap-1", "not safe");
    expect(transport.lastRequest().params).toEqual({ approvalId: "ap-1", reason: "not safe" });

    void client.artifactRead("art-1");
    expect(transport.lastRequest().params).toEqual({ artifactId: "art-1" });

    void client.registryGet("capabilities", "read_file", "1.0.0");
    expect(transport.lastRequest().params).toEqual({
      kind: "capabilities",
      name: "read_file",
      version: "1.0.0",
    });
  });
});
