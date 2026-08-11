import { existsSync } from "node:fs";
import path from "node:path";

export function resolveBackendCommand(repoRoot: string, name: string): string {
  const venvBin = path.join(repoRoot, "backend", ".venv", process.platform === "win32" ? "Scripts" : "bin");
  const candidate = path.join(venvBin, process.platform === "win32" ? `${name}.exe` : name);
  return existsSync(candidate) ? candidate : name;
}
