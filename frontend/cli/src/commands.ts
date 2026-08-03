import type { ProtocolClient } from "@awf/protocol-client";
import type { Settings } from "./settings.js";

/** Only the subset of ProtocolClient that slash commands actually call -
 * keeps command-dispatch logic testable with a plain fake, no real
 * ProtocolClient/transport required. */
export type CommandClient = Pick<
  ProtocolClient,
  | "runStart"
  | "runStatus"
  | "runList"
  | "runResume"
  | "approvalList"
  | "approvalApprove"
  | "approvalReject"
  | "artifactList"
  | "secretListNames"
  | "registryList"
>;

export type CommandResult =
  | { kind: "text"; text: string }
  | { kind: "json"; data: unknown }
  | { kind: "clear" }
  | { kind: "quit" };

export class CommandError extends Error {}

export const HELP_TEXT = `
/help                                 List commands and keybindings
/run <workflow>@<version>             Start a Run
/status <run-id>                      Run state, step progress, budgets
/runs                                 List Runs
/resume                               Trigger the startup recovery scan
/approvals                            Approval queue
/approve <id>                         Approve a pending approval
/reject <id> <reason>                 Reject a pending approval
/artifacts <run-id>                   List artifacts for a Run
/agents                               Registered Agent Manifests
/skills                               Registry Skills
/workflows                            Registry Workflow definitions
/capabilities                         Capability Records with risk classes
/mcp                                  Registered MCP servers and trust status
/model                                Model Profiles
/voices                               Voice Profiles
/secrets                              Secret names only - never values
/settings                             Current TUI settings
/theme                                Current theme
/keybindings                          Current keybindings
/clear                                Clear the scrollback
/quit                                 Exit
`.trim();

const REGISTRY_KIND_BY_COMMAND: Record<string, string> = {
  agents: "agents",
  skills: "skills",
  workflows: "workflows",
  capabilities: "capabilities",
  mcp: "mcp",
  model: "model-profiles",
  voices: "voice-profiles",
};

export async function dispatchCommand(
  client: CommandClient,
  line: string,
  settings: Settings,
): Promise<CommandResult> {
  const trimmed = line.trim();
  if (!trimmed.startsWith("/")) {
    throw new CommandError(`not a slash command: ${line}`);
  }

  const [name, ...args] = trimmed.slice(1).split(/\s+/).filter(Boolean);

  if (name === "help") return { kind: "text", text: HELP_TEXT };
  if (name === "clear") return { kind: "clear" };
  if (name === "quit") return { kind: "quit" };
  if (name === "settings") return { kind: "json", data: settings };
  if (name === "theme") return { kind: "json", data: { theme: settings.theme } };
  if (name === "keybindings") return { kind: "json", data: settings.keybindings };

  if (name === "run") {
    if (!args[0]) throw new CommandError("usage: /run <workflow>@<version>");
    return { kind: "json", data: await client.runStart(args[0]) };
  }
  if (name === "status") {
    if (!args[0]) throw new CommandError("usage: /status <run-id>");
    return { kind: "json", data: await client.runStatus(args[0]) };
  }
  if (name === "runs") return { kind: "json", data: await client.runList() };
  if (name === "resume") return { kind: "json", data: await client.runResume() };
  if (name === "approvals") return { kind: "json", data: await client.approvalList() };
  if (name === "approve") {
    if (!args[0]) throw new CommandError("usage: /approve <approval-id>");
    return { kind: "json", data: await client.approvalApprove(args[0]) };
  }
  if (name === "reject") {
    if (!args[0] || args.length < 2) throw new CommandError("usage: /reject <approval-id> <reason>");
    const [id, ...reasonParts] = args;
    return { kind: "json", data: await client.approvalReject(id, reasonParts.join(" ")) };
  }
  if (name === "artifacts") {
    if (!args[0]) throw new CommandError("usage: /artifacts <run-id>");
    return { kind: "json", data: await client.artifactList(args[0]) };
  }
  if (name === "secrets") return { kind: "json", data: await client.secretListNames() };

  const registryKind = REGISTRY_KIND_BY_COMMAND[name ?? ""];
  if (registryKind) return { kind: "json", data: await client.registryList(registryKind) };

  throw new CommandError(`unknown command: /${name}`);
}
