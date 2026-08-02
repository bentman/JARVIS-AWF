import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { DEFAULT_SETTINGS, loadSettings, SettingsValidationError } from "../src/settings.js";

function makeDirs() {
  const repoRoot = mkdtempSync(join(tmpdir(), "awf-repo-"));
  const homeDir = mkdtempSync(join(tmpdir(), "awf-home-"));
  return { repoRoot, homeDir };
}

function writeSettings(dir: string, filename: string, content: object) {
  const awfDir = join(dir, ".awf");
  mkdirSync(awfDir, { recursive: true });
  writeFileSync(join(awfDir, filename), JSON.stringify(content));
}

describe("loadSettings", () => {
  it("returns defaults when no settings files exist", () => {
    const { repoRoot, homeDir } = makeDirs();
    expect(loadSettings(repoRoot, homeDir)).toEqual(DEFAULT_SETTINGS);
  });

  it("user settings override defaults", () => {
    const { repoRoot, homeDir } = makeDirs();
    writeSettings(homeDir, "settings.json", { theme: "dark" });

    expect(loadSettings(repoRoot, homeDir).theme).toBe("dark");
  });

  it("project settings override user settings", () => {
    const { repoRoot, homeDir } = makeDirs();
    writeSettings(homeDir, "settings.json", { theme: "dark" });
    writeSettings(repoRoot, "settings.json", { theme: "light" });

    expect(loadSettings(repoRoot, homeDir).theme).toBe("light");
  });

  it("local settings override project and user settings", () => {
    const { repoRoot, homeDir } = makeDirs();
    writeSettings(homeDir, "settings.json", { theme: "dark" });
    writeSettings(repoRoot, "settings.json", { theme: "light" });
    writeSettings(repoRoot, "settings.local.json", { theme: "system" });

    expect(loadSettings(repoRoot, homeDir).theme).toBe("system");
  });

  it("rejects a key outside the schema, naming the key", () => {
    const { repoRoot, homeDir } = makeDirs();
    writeSettings(repoRoot, "settings.json", { notARealKey: true });

    expect(() => loadSettings(repoRoot, homeDir)).toThrow(SettingsValidationError);
    expect(() => loadSettings(repoRoot, homeDir)).toThrow(/notARealKey/);
  });

  it("accepts GUI-only keys alongside CLI-relevant ones", () => {
    const { repoRoot, homeDir } = makeDirs();
    writeSettings(repoRoot, "settings.json", { wakeWordEnabled: true, inputDevice: "default" });

    const settings = loadSettings(repoRoot, homeDir);
    expect(settings.wakeWordEnabled).toBe(true);
    expect(settings.inputDevice).toBe("default");
  });
});
