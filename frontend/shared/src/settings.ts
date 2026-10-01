import { existsSync, readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

export interface Settings {
  theme: "dark" | "light" | "system";
  keybindings: Record<string, string>;
  verbosity: "quiet" | "normal" | "verbose";
  defaultWorkflow?: string;
  wakeWordEnabled: boolean;
  inputDevice?: string;
  outputDevice?: string;
}

export const DEFAULT_SETTINGS: Settings = {
  theme: "system",
  keybindings: {},
  verbosity: "normal",
  wakeWordEnabled: false,
};

const ALLOWED_KEYS = new Set<string>([
  "theme",
  "keybindings",
  "verbosity",
  "defaultWorkflow",
  "wakeWordEnabled",
  "inputDevice",
  "outputDevice",
]);

export class SettingsValidationError extends Error {
  constructor(key: string) {
    super(`unknown settings key: ${key}`);
    this.name = "SettingsValidationError";
  }
}

function validateKeys(raw: Record<string, unknown>): void {
  for (const key of Object.keys(raw)) {
    if (!ALLOWED_KEYS.has(key)) {
      throw new SettingsValidationError(key);
    }
  }
}

function readJsonIfExists(path: string): Record<string, unknown> | null {
  if (!existsSync(path)) return null;
  const raw = JSON.parse(readFileSync(path, "utf-8")) as Record<string, unknown>;
  validateKeys(raw);
  return raw;
}

/** Precedence: local > project > user (Section 16.2 "Configuration"). */
export function loadSettings(repoRoot: string, homeDir: string = homedir()): Settings {
  const userPath = join(homeDir, ".awf", "settings.json");
  const projectPath = join(repoRoot, ".awf", "settings.json");
  const localPath = join(repoRoot, ".awf", "settings.local.json");

  const user = readJsonIfExists(userPath) ?? {};
  const project = readJsonIfExists(projectPath) ?? {};
  const local = readJsonIfExists(localPath) ?? {};

  return { ...DEFAULT_SETTINGS, ...user, ...project, ...local } as Settings;
}
