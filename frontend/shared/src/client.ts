import type { Transport } from "./transport.js";
import { ProtocolGeneratedClient, type MethodName } from "./protocol.generated.js";
import {
  ProtocolError,
  type JsonRpcResponse,
} from "./types.js";

/** The single TypeScript protocol client (Section 16.3) - both frontends
 * (AWF-CLI, AWF-GUI) consume this; neither may implement its own protocol
 * layer. Every method maps 1:1 onto an `awf system serve --stdio` JSON-RPC method;
 * the protocol adds no authority beyond what the core operation itself
 * grants. */
export class ProtocolClient extends ProtocolGeneratedClient {
  private transport: Transport;
  private nextId = 1;
  private pending = new Map<
    number,
    { method: MethodName; resolve: (value: unknown) => void; reject: (reason: unknown) => void; timer: NodeJS.Timeout }
  >();
  protected callTimeoutMs: number;
  protected runCallTimeoutMs: number;

  constructor(transport: Transport, options: { callTimeoutMs?: number; runCallTimeoutMs?: number } = {}) {
    super();
    this.transport = transport;
    this.callTimeoutMs = options.callTimeoutMs ?? 30000;
    this.runCallTimeoutMs = options.runCallTimeoutMs ?? 600000;
    this.transport.onLine((line) => this.handleLine(line));
    this.transport.onExit((code) => this.handleExit(code));
    this.transport.onError((error) => this.handleTransportError(error));
  }

  private handleLine(line: string): void {
    const trimmed = line.trim();
    if (!trimmed) return;
    let response: JsonRpcResponse;
    try {
      response = JSON.parse(trimmed) as JsonRpcResponse;
    } catch {
      return;
    }
    if (response.id === null || response.id === undefined) return;
    const pending = this.pending.get(response.id);
    if (!pending) return;
    this.pending.delete(response.id);
    clearTimeout(pending.timer);
    if (response.error) {
      pending.reject(new ProtocolError(response.error.code, response.error.message));
    } else {
      pending.resolve(response.result);
    }
  }

  private handleExit(code: number | null): void {
    const error = new Error(`awf core process exited (code=${code}) before responding`);
    for (const { reject, timer } of this.pending.values()) {
      clearTimeout(timer);
      reject(error);
    }
    this.pending.clear();
  }

  private handleTransportError(error: Error): void {
    for (const { reject, timer } of this.pending.values()) {
      clearTimeout(timer);
      reject(error);
    }
    this.pending.clear();
  }

  protected call<T>(method: MethodName, params?: Record<string, unknown>, timeoutMs = this.callTimeoutMs): Promise<T> {
    const id = this.nextId++;
    const request = { jsonrpc: "2.0" as const, id, method, params };
    const promise = new Promise<T>((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error(`awf ${method} timed out after ${timeoutMs}ms`));
      }, timeoutMs);
      timer.unref?.();
      this.pending.set(id, { method, resolve: resolve as (value: unknown) => void, reject, timer });
    });
    this.transport.send(JSON.stringify(request));
    return promise;
  }

  close(): void {
    this.transport.close();
  }
}
