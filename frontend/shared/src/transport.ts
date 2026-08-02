import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import { createInterface } from "node:readline";

export interface Transport {
  send(line: string): void;
  onLine(handler: (line: string) => void): void;
  onExit(handler: (code: number | null) => void): void;
  close(): void;
}

export interface SpawnCoreOptions {
  /** Path to the `awf` executable. Defaults to "awf" (resolved via PATH). */
  command?: string;
  /** Extra args before "serve --stdio" - normally none. */
  args?: string[];
  cwd?: string;
}

/** Spawns `awf serve --stdio` (Section 16.3) as a child process and speaks
 * newline-delimited JSON-RPC over its stdin/stdout. */
export class ChildProcessTransport implements Transport {
  private child: ChildProcessWithoutNullStreams;
  private lineHandlers: Array<(line: string) => void> = [];
  private exitHandlers: Array<(code: number | null) => void> = [];

  constructor(options: SpawnCoreOptions = {}) {
    const command = options.command ?? "awf";
    const args = [...(options.args ?? []), "serve", "--stdio"];
    this.child = spawn(command, args, {
      cwd: options.cwd,
      stdio: ["pipe", "pipe", "pipe"],
    });

    const rl = createInterface({ input: this.child.stdout });
    rl.on("line", (line) => {
      for (const handler of this.lineHandlers) handler(line);
    });
    this.child.on("exit", (code) => {
      for (const handler of this.exitHandlers) handler(code);
    });
  }

  send(line: string): void {
    this.child.stdin.write(line + "\n");
  }

  onLine(handler: (line: string) => void): void {
    this.lineHandlers.push(handler);
  }

  onExit(handler: (code: number | null) => void): void {
    this.exitHandlers.push(handler);
  }

  close(): void {
    this.child.stdin.end();
  }

  kill(signal: NodeJS.Signals = "SIGTERM"): void {
    this.child.kill(signal);
  }
}
