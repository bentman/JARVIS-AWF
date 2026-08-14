import type { Transport } from "../src/transport.js";

/** In-memory Transport for unit tests - no real process spawned. */
export class FakeTransport implements Transport {
  sent: string[] = [];
  private lineHandlers: Array<(line: string) => void> = [];
  private exitHandlers: Array<(code: number | null) => void> = [];
  private errorHandlers: Array<(error: Error) => void> = [];

  send(line: string): void {
    this.sent.push(line);
  }

  onLine(handler: (line: string) => void): void {
    this.lineHandlers.push(handler);
  }

  onExit(handler: (code: number | null) => void): void {
    this.exitHandlers.push(handler);
  }

  onError(handler: (error: Error) => void): void {
    this.errorHandlers.push(handler);
  }

  close(): void {}

  /** Test helper: simulate the core process writing a response line. */
  emit(payload: unknown): void {
    const line = JSON.stringify(payload);
    for (const handler of this.lineHandlers) handler(line);
  }

  emitExit(code: number | null): void {
    for (const handler of this.exitHandlers) handler(code);
  }

  emitError(error: Error): void {
    for (const handler of this.errorHandlers) handler(error);
  }

  lastRequest(): { jsonrpc: string; id: number; method: string; params?: Record<string, unknown> } {
    return JSON.parse(this.sent[this.sent.length - 1]);
  }
}
