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
  | "approvalDetail"
  | "approvalApprove"
  | "approvalReject"
  | "artifactList"
  | "improvementList"
  | "improvementGet"
  | "improvementPrepare"
  | "improvementRequestMerge"
  | "improvementMerge"
  | "improvementReject"
  | "secretListNames"
  | "controlSummary"
  | "controlRunDetail"
  | "systemReadiness"
  | "llmServers"
  | "llmModels"
  | "llmServeStatus"
  | "registryList"
  | "registryGet"
  | "workflowAuthorDraft"
  | "proposalGet"
  | "proposalUpdate"
  | "proposalPublish"
  | "proposalReject"
  | "memorySearch"
  | "memoryGet"
  | "memoryPropose"
  | "memoryPublish"
  | "memoryReject"
  | "memoryBlock"
  | "sessionStart"
  | "sessionShow"
  | "episodicSearch"
  | "episodicTimeline"
>;

export type CommandResult =
  | { kind: "text"; text: string }
  | { kind: "json"; data: unknown }
  | { kind: "clear" }
  | { kind: "quit" };

export class CommandError extends Error {}

export const DEFAULT_ASSISTANT_WORKFLOW_REF = "assistant-default@1.0.0";

export const HELP_TEXT = `
Plain text                            Ask the default assistant workflow
/help                                 List commands and keybindings
/run <workflow>@<version>             Start a Run
/status <run-id>                      Run state, step progress, budgets
/runs                                 List Runs
/resume                               Trigger the startup recovery scan
/approvals                            Approval queue
/approval <id>                        Approval detail and machine-action preview
/approve <id>                         Approve a pending approval
/reject <id> <reason>                 Reject a pending approval
/artifacts <run-id>                   List artifacts for a Run
/improvements                         List Improvement Proposals
/improvement <id>                     Show an Improvement Proposal
/improvement-prepare <run-id>         Create/update an Improvement Proposal
/improvement-request-merge <id>       Request merge approval
/improvement-merge <id> <approval-id> Merge after approval
/improvement-reject <id> <reason>     Reject an Improvement Proposal
/author-workflow <objective>          Draft a Workflow proposal
/proposal <id>                        Show a Workflow proposal
/proposal-publish <id> <digest>       Publish a draft proposal
/proposal-reject <id> <reason>        Reject a draft proposal
/memory-search <query>                Search semantic and episodic memory
/memory <name>@<version>              Show a Semantic Memory
/memory-propose <path>                Draft a Semantic Memory proposal
/memory-publish <id> <digest>         Publish a Semantic Memory proposal
/memory-reject <id> <reason>          Reject a Semantic Memory proposal
/memory-block <name>@<version>        Block a Semantic Memory
/session-start [title]                Start an active session
/session-show <session-id>            Show an active session
/episodic-search <query>              Search event history
/episodic <run-id>                    Show a Run timeline
/control                              Control-center overview
/readiness                            Hardware and runtime readiness
/llm                                  LLM server/model status
/agents                               Registered Agent Manifests
/skills                               Registry Skills
/skill <name>@<version>               Show a registry Skill
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

function assistantResponseText(workflowRef: string, result: Record<string, unknown>): string {
  const outputs = result.outputs as Record<string, unknown> | undefined;
  if (typeof outputs?.response_text === "string") return outputs.response_text;
  if (typeof result.reason === "string") return result.reason;
  if (typeof result.error === "string") return result.error;
  return `Workflow ${workflowRef} finished with status ${String(result.status ?? "UNKNOWN")}.`;
}

export async function dispatchAssistantInput(
  client: CommandClient,
  text: string,
  workflowRef = DEFAULT_ASSISTANT_WORKFLOW_REF,
): Promise<CommandResult> {
  const trimmed = text.trim();
  if (!trimmed) throw new CommandError("assistant input is empty");
  const result = (await client.runStart(workflowRef, { objective: trimmed })) as Record<string, unknown>;
  const runId = typeof result.run_id === "string" ? ` (${result.run_id})` : "";
  return { kind: "text", text: `${assistantResponseText(workflowRef, result)}${runId}` };
}

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
  if (name === "approval") {
    if (!args[0]) throw new CommandError("usage: /approval <approval-id>");
    return { kind: "json", data: await client.approvalDetail(args[0]) };
  }
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
  if (name === "improvements") return { kind: "json", data: await client.improvementList() };
  if (name === "improvement") {
    if (!args[0]) throw new CommandError("usage: /improvement <id>");
    return { kind: "json", data: await client.improvementGet(args[0]) };
  }
  if (name === "improvement-prepare") {
    if (!args[0]) throw new CommandError("usage: /improvement-prepare <run-id>");
    const [runId, ...summaryParts] = args;
    return { kind: "json", data: await client.improvementPrepare(runId, summaryParts.join(" ") || undefined) };
  }
  if (name === "improvement-request-merge") {
    if (!args[0]) throw new CommandError("usage: /improvement-request-merge <id>");
    return { kind: "json", data: await client.improvementRequestMerge(args[0]) };
  }
  if (name === "improvement-merge") {
    if (!args[0] || !args[1]) throw new CommandError("usage: /improvement-merge <id> <approval-id>");
    return { kind: "json", data: await client.improvementMerge(args[0], args[1]) };
  }
  if (name === "improvement-reject") {
    if (!args[0] || args.length < 2) throw new CommandError("usage: /improvement-reject <id> <reason>");
    const [id, ...reasonParts] = args;
    return { kind: "json", data: await client.improvementReject(id, reasonParts.join(" ")) };
  }
  if (name === "author-workflow") {
    if (args.length < 1) throw new CommandError("usage: /author-workflow <objective>");
    return { kind: "json", data: await client.workflowAuthorDraft({ objective: args.join(" ") }) };
  }
  if (name === "proposal") {
    if (!args[0]) throw new CommandError("usage: /proposal <proposal-id>");
    return { kind: "json", data: await client.proposalGet(args[0]) };
  }
  if (name === "proposal-publish") {
    if (!args[0] || !args[1]) throw new CommandError("usage: /proposal-publish <proposal-id> <digest>");
    return { kind: "json", data: await client.proposalPublish(args[0], args[1]) };
  }
  if (name === "proposal-reject") {
    if (!args[0] || args.length < 2) throw new CommandError("usage: /proposal-reject <proposal-id> <reason>");
    const [id, ...reasonParts] = args;
    return { kind: "json", data: await client.proposalReject(id, reasonParts.join(" ")) };
  }
  if (name === "memory-search") {
    if (args.length < 1) throw new CommandError("usage: /memory-search <query>");
    return { kind: "json", data: await client.memorySearch(args.join(" ")) };
  }
  if (name === "memory") {
    if (!args[0]) throw new CommandError("usage: /memory <name>@<version>");
    return { kind: "json", data: await client.memoryGet(args[0]) };
  }
  if (name === "memory-propose") {
    if (!args[0]) throw new CommandError("usage: /memory-propose <path>");
    return { kind: "json", data: await client.memoryPropose(args[0]) };
  }
  if (name === "memory-publish") {
    if (!args[0] || !args[1]) throw new CommandError("usage: /memory-publish <proposal-id> <digest>");
    return { kind: "json", data: await client.memoryPublish(args[0], args[1]) };
  }
  if (name === "memory-reject") {
    if (!args[0] || args.length < 2) throw new CommandError("usage: /memory-reject <proposal-id> <reason>");
    const [id, ...reasonParts] = args;
    return { kind: "json", data: await client.memoryReject(id, reasonParts.join(" ")) };
  }
  if (name === "memory-block") {
    if (!args[0]) throw new CommandError("usage: /memory-block <name>@<version>");
    return { kind: "json", data: await client.memoryBlock(args[0]) };
  }
  if (name === "session-start") {
    return { kind: "json", data: await client.sessionStart(args.join(" ") || undefined) };
  }
  if (name === "session-show") {
    if (!args[0]) throw new CommandError("usage: /session-show <session-id>");
    return { kind: "json", data: await client.sessionShow(args[0]) };
  }
  if (name === "episodic-search") {
    if (args.length < 1) throw new CommandError("usage: /episodic-search <query>");
    return { kind: "json", data: await client.episodicSearch(args.join(" ")) };
  }
  if (name === "episodic") {
    if (!args[0]) throw new CommandError("usage: /episodic <run-id>");
    return { kind: "json", data: await client.episodicTimeline(args[0]) };
  }
  if (name === "control") return { kind: "json", data: await client.controlSummary() };
  if (name === "readiness") return { kind: "json", data: await client.systemReadiness() };
  if (name === "llm") {
    const [servers, models, status] = await Promise.all([
      client.llmServers(),
      client.llmModels(),
      client.llmServeStatus(),
    ]);
    return { kind: "json", data: { servers, models, status } };
  }
  if (name === "skill") {
    if (!args[0]) throw new CommandError("usage: /skill <name>@<version>");
    const [skillName, version] = splitRegistryRef(args[0], "skill");
    return { kind: "json", data: await client.registryGet("skills", skillName, version) };
  }
  if (name === "secrets") return { kind: "json", data: await client.secretListNames() };

  const registryKind = REGISTRY_KIND_BY_COMMAND[name ?? ""];
  if (registryKind) return { kind: "json", data: await client.registryList(registryKind) };

  throw new CommandError(`unknown command: /${name}`);
}

function splitRegistryRef(ref: string, label: string): [string, string] {
  const [name, version, extra] = ref.split("@");
  if (!name || !version || extra !== undefined) {
    throw new CommandError(`usage: /${label} <name>@<version>`);
  }
  return [name, version];
}
