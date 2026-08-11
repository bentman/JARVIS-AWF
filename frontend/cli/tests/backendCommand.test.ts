import { mkdtempSync, mkdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { resolveBackendCommand } from "../src/backendCommand.js";

describe("resolveBackendCommand", () => {
  it("uses the repo venv command when it exists", () => {
    const repoRoot = mkdtempSync(path.join(tmpdir(), "awf-cli-"));
    const binDir = path.join(repoRoot, "backend", ".venv", process.platform === "win32" ? "Scripts" : "bin");
    mkdirSync(binDir, { recursive: true });
    const commandPath = path.join(binDir, process.platform === "win32" ? "awf.exe" : "awf");
    writeFileSync(commandPath, "");

    expect(resolveBackendCommand(repoRoot, "awf")).toBe(commandPath);
  });

  it("falls back to PATH lookup when the repo venv command is missing", () => {
    const repoRoot = mkdtempSync(path.join(tmpdir(), "awf-cli-"));

    expect(resolveBackendCommand(repoRoot, "awf")).toBe("awf");
  });
});
