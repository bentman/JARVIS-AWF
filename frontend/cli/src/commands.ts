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
  | "systemDoctor"
  | "llmServers"
  | "llmModels"
  | "llmServeStatus"
  | "registryList"
  | "registryGet"
  | "skillInvoke"
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
/agents                               Registered Agent Manifests
/approval <id>                        Approval detail and machine-action preview
/approvals                            Approval queue
/approve <id>                         Approve a pending approval
/artifacts <run-id>                   List artifacts for a Run
/author-workflow <objective>          Draft a Workflow proposal
/capabilities                         Capability Records with risk classes
/clear                                Clear the scrollback
/control                              Control-center overview
/doctor                               Install and operator readiness checks
/episodic <run-id>                    Show a Run timeline
/episodic-search <query>              Search event history
/help                                 List commands and keybindings
/improvement <id>                     Show an Improvement Proposal
/improvement-merge <id> <approval-id> Merge after approval
/improvement-prepare <run-id>         Create/update an Improvement Proposal
/improvement-reject <id> <reason>     Reject an Improvement Proposal
/improvement-request-merge <id>       Request merge approval
/improvements                         List Improvement Proposals
/keybindings                          Current keybindings
/llm                                  LLM server/model status
/mcp                                  Registered MCP servers and trust status
/memory <name>@<version>              Show a Semantic Memory
/memory-block <name>@<version>        Block a Semantic Memory
/memory-propose <path>                Draft a Semantic Memory proposal
/memory-publish <id> <digest>         Publish a Semantic Memory proposal
/memory-reject <id> <reason>          Reject a Semantic Memory proposal
/memory-search <query>                Search semantic and episodic memory
/model                                Model Profiles
/proposal <id>                        Show a Workflow proposal
/proposal-publish <id> <digest>       Publish a draft proposal
/proposal-reject <id> <reason>        Reject a draft proposal
/quit                                 Exit
/readiness                            Hardware and runtime readiness
/reject <id> <reason>                 Reject a pending approval
/resume                               Trigger the startup recovery scan
/run <workflow>@<version>             Start a Run
/runs                                 List Runs
/secrets                              Secret names only - never values
/session-show <session-id>            Show an active session
/session-start [title]                Start an active session
/settings                             Current TUI settings
/skill <name>@<version>               Show a registry Skill
/skill-run <name>@<version> <input>   Invoke a registry Skill through the resident mind
/skills                               Registry Skills
/status <run-id>                      Run state, step progress, budgets
/theme                                Current theme
/voices                               Voice Profiles
/workflows                            Registry Workflow definitions
`.trim();

export const COMMAND_NAMES = HELP_TEXT.split("\n")
  .map((line) => line.match(/^\/([a-z0-9-]+)/)?.[1])
  .filter((name): name is string => Boolean(name));

function assistantResponseText(workflowRef: string, result: Record<string, unknown>): string {
  const outputs = result.outputs as Record<string, unknown> | undefined;
  if (typeof outputs?.response_text === "string") return outputs.response_text;
  if (typeof result.reason === "string") return result.reason;
  if (typeof result.error === "string") return result.error;
  return `Workflow ${workflowRef} finished with status ${String(result.status ?? "UNKNOWN")}.`;
}

function runOutcome(result: Record<string, unknown>): Record<string, unknown> {
  const outcome = result.outcome as Record<string, unknown> | undefined;
  if (outcome) return outcome;
  return {
    run_id: result.run_id,
    workflow_ref: result.workflow_ref,
    status: result.status,
    response_text: assistantResponseText(String(result.workflow_ref ?? "workflow"), result),
    evidence: [],
    failures: [],
    pending_approvals: [],
    next_action: undefined,
  };
}

function formatOutcome(result: Record<string, unknown>): string {
  const outcome = runOutcome(result);
  const lines = [
    `Run: ${String(outcome.run_id ?? result.run_id ?? "unknown")}`,
    `Workflow: ${String(outcome.workflow_ref ?? result.workflow_ref ?? "unknown")}`,
    `Status: ${String(outcome.status ?? result.status ?? "UNKNOWN")}`,
    `Result: ${String(outcome.response_text ?? assistantResponseText(String(outcome.workflow_ref ?? "workflow"), result))}`,
  ];
  const proposal = outcome.proposal as Record<string, unknown> | undefined;
  if (proposal) {
    lines.push(
      "\n============================================================",
      "AWF IMPROVEMENT PROPOSAL REVIEW",
      `Proposal: ${String(proposal.improvement_id)}  •  Status: ${String(proposal.status ?? "").toUpperCase()} [${String(proposal.scope_classification ?? "localized").toUpperCase()}]`,
      "============================================================",
      `\n1. WHAT CHANGED:\n  ${String(proposal.human_summary ?? proposal.summary ?? "")}`,
    );
    if (proposal.verdict_artifact_id) {
      lines.push(`\n2. VALIDATION STATUS:\n  PASSED — All gate checks and tests passed (verdict: ${String(proposal.verdict_artifact_id)})`);
    }
    if (proposal.safety_assessment) {
      lines.push(`\n3. WHY IT IS SAFE TO CONSIDER:\n  ${String(proposal.safety_assessment)}`);
    }
    const diffStats = Array.isArray(proposal.diff_stats) ? (proposal.diff_stats as Record<string, unknown>[]) : [];
    if (diffStats.length > 0) {
      lines.push("\n4. CHANGED FILES & DIFF PREVIEW:");
      for (const f of diffStats) {
        lines.push(`  • ${String(f.path)} (+${String(f.additions ?? 0)} / -${String(f.deletions ?? 0)} lines)`);
        const previewLines = Array.isArray(f.preview_lines) ? (f.preview_lines as string[]) : [];
        for (const pl of previewLines.slice(0, 6)) {
          lines.push(`      ${pl}`);
        }
      }
    }
    const nextAction = proposal.next_action as Record<string, unknown> | undefined;
    if (nextAction && nextAction.command) {
      lines.push(
        "\n------------------------------------------------------------",
        `5. NEXT OPERATOR ACTION:\n  ${String(nextAction.label)}\n  Command: ${String(nextAction.command)}`,
        "------------------------------------------------------------",
      );
    }
    lines.push("============================================================");
  }
  const evidence = Array.isArray(outcome.evidence) ? (outcome.evidence as Record<string, unknown>[]) : [];
  if (evidence.length > 0 && !proposal) {
    lines.push("Evidence:");
    for (const item of evidence) lines.push(`  - ${String(item.type)}: ${String(item.path)} (${String(item.artifact_id)})`);
  }
  const failures = Array.isArray(outcome.failures) ? (outcome.failures as Record<string, unknown>[]) : [];
  if (failures.length > 0) {
    lines.push("Failures:");
    for (const item of failures) lines.push(`  - ${String(item.node_id)} (${String(item.step_id)}): ${String(item.failure_class ?? "failed")}`);
  }
  const pending = Array.isArray(outcome.pending_approvals)
    ? (outcome.pending_approvals as Record<string, unknown>[])
    : [];
  if (pending.length > 0) {
    lines.push("Pending approvals:");
    for (const item of pending) lines.push(`  - ${String(item.approval_id)} ${String(item.risk_class ?? "")}`.trimEnd());
  }
  if (outcome.next_action) lines.push(`\nNext: ${String(outcome.next_action)}`);
  return lines.join("\n");
}

function formatRunList(runs: Record<string, unknown>[]): string {
  if (runs.length === 0) return "No runs.";
  return [
    "Runs:",
    ...runs.map((run) => {
      const outcome = run.outcome as Record<string, unknown> | undefined;
      return `  - ${String(run.run_id)} ${String(run.status)} ${String(run.workflow_ref)} :: ${String(outcome?.response_text ?? "")}`;
    }),
  ].join("\n");
}

function formatReadiness(readiness: Record<string, unknown>): string {
  const lines = [`Profile: ${String(readiness.profile_id ?? "unknown")}`];
  if (readiness.error) lines.push(`Error: ${String(readiness.error)}`);
  const results = readiness.readiness as Record<string, Record<string, unknown>> | undefined;
  for (const [name, result] of Object.entries(results ?? {})) {
    lines.push(
      `${name}: ${result.ready ? "ready" : "not ready"} on ${String(result.device)} - ${String(result.reason ?? "")}`,
    );
  }
  const tokens = Array.isArray(readiness.tokens) ? readiness.tokens : [];
  if (tokens.length > 0) lines.push(`Tokens: ${tokens.join(", ")}`);
  return lines.join("\n");
}

function formatDoctor(report: Record<string, unknown>): string {
  const lines = [`AWF doctor: ${String(report.status ?? "unknown")}`];
  const checks = Array.isArray(report.checks) ? (report.checks as Record<string, unknown>[]) : [];
  for (const check of checks) {
    lines.push(`- ${String(check.name)}: ${String(check.status)} - ${String(check.summary)}`);
    if (check.next_action) lines.push(`  next: ${String(check.next_action)}`);
  }
  if (report.first_run_command) lines.push(`First run: ${String(report.first_run_command)}`);
  return lines.join("\n");
}

function formatApprovals(items: Record<string, unknown>[]): string {
  if (items.length === 0) return "No pending approvals.";
  const lines = ["Pending Approvals:"];
  for (const item of items) {
    const preview = item.preview as Record<string, unknown> | null | undefined;
    const human = preview?.human_summary as string | undefined;
    const risk = String(item.risk_class ?? "R2");
    const apprId = String(item.approval_id);
    if (human) {
      lines.push(`  - ${apprId} [${risk}] ${human}`);
    } else {
      lines.push(`  - ${apprId} [${risk}] run=${String(item.run_id)} digest=${String(item.action_digest)}`);
    }
    lines.push(`    Next: /approval ${apprId}  (or: /approve ${apprId})`);
  }
  return lines.join("\n");
}

function formatApprovalDetail(detail: Record<string, unknown>): string {
  const approval = detail.approval as Record<string, unknown>;
  const preview = detail.preview as Record<string, unknown> | null | undefined;
  const lines = [
    "============================================================",
    `AWF APPROVAL REVIEW: ${String(approval.approval_id)} [${String(approval.status).toUpperCase()}]`,
    `Risk Class: ${String(approval.risk_class ?? "unknown")}  •  Requested: ${String(approval.requested_at)}`,
    "============================================================",
  ];

  const proposal = (preview?.proposal as Record<string, unknown> | undefined) ?? (preview?.kind === "improvement_merge" ? preview : undefined);
  if (proposal) {
    const summary = String(proposal.human_summary ?? proposal.summary ?? "");
    lines.push(`\n1. WHAT IS BEING APPROVED:\n  ${summary}`);
    if (proposal.safety_assessment) {
      lines.push(`\n2. WHY IT IS SAFE TO APPROVE:\n  ${String(proposal.safety_assessment)}`);
    }
    if (proposal.verdict_artifact_id) {
      lines.push(`\n3. VALIDATION STATUS:\n  PASSED — All gate checks verified (verdict artifact: ${String(proposal.verdict_artifact_id)})`);
    }
    const diffStats = Array.isArray(proposal.diff_stats) ? (proposal.diff_stats as Record<string, unknown>[]) : [];
    if (diffStats.length > 0) {
      lines.push("\n4. CHANGED FILES & DIFF PREVIEW:");
      for (const f of diffStats) {
        lines.push(`  • ${String(f.path)} (+${String(f.additions ?? 0)} / -${String(f.deletions ?? 0)} lines)`);
        const previewLines = Array.isArray(f.preview_lines) ? (f.preview_lines as string[]) : [];
        for (const pl of previewLines.slice(0, 8)) {
          lines.push(`      ${pl}`);
        }
      }
    }
  } else if (preview?.machine_action) {
    const action = preview.machine_action as Record<string, unknown>;
    lines.push(`\nAction: ${String(action.kind)} ${String(action.capability_ref ?? "")}`.trimEnd());
    lines.push(`Target: ${JSON.stringify(action.target ?? {})}`);
  }

  lines.push("\n------------------------------------------------------------");
  lines.push("DECISION ACTIONS:");
  lines.push(`  Approve: /approve ${String(approval.approval_id)}`);
  lines.push(`  Reject:  /reject ${String(approval.approval_id)} <reason>`);
  lines.push("------------------------------------------------------------");
  lines.push(`\n[Digest: ${String(approval.action_digest)}]`);
  return lines.join("\n");
}

function formatMemorySearch(result: Record<string, unknown>): string {
  const semantic = Array.isArray(result.semantic) ? (result.semantic as Record<string, unknown>[]) : [];
  const episodic = Array.isArray(result.episodic) ? (result.episodic as Record<string, unknown>[]) : [];
  const lines = [`Memory: ${semantic.length} semantic, ${episodic.length} episodic`];
  for (const item of semantic.slice(0, 5)) {
    lines.push(`  - ${String(item.ref ?? item.name ?? "semantic")}: ${String(item.summary ?? item.text ?? "")}`);
  }
  for (const item of episodic.slice(0, 5)) {
    lines.push(`  - ${String(item.run_id ?? item.reason_code ?? "event")}: ${String(item.summary ?? item.reason_code ?? "")}`);
  }
  return lines.join("\n");
}

function formatControlSummary(summary: Record<string, unknown>): string {
  const runs = Array.isArray(summary.runs) ? summary.runs.length : 0;
  const approvals = Array.isArray(summary.approvals) ? summary.approvals.length : 0;
  return [`Control: ${runs} runs, ${approvals} pending approvals`].join("\n");
}

function formatLlmStatus(report: Record<string, unknown>): string {
  return [
    `LLM server: ${String((report.status as Record<string, unknown> | undefined)?.state ?? "unknown")}`,
    `Default: ${String((report.servers as Record<string, unknown> | undefined)?.default_server ?? "unknown")}`,
    `Models: ${Array.isArray((report.models as Record<string, unknown> | undefined)?.local_models) ? ((report.models as Record<string, unknown>).local_models as unknown[]).length : 0}`,
  ].join("\n");
}

function formatImprovementProposal(proposal: Record<string, unknown>): string {
  const impId = String(proposal.improvement_id ?? "unknown");
  const status = String(proposal.status ?? "draft");
  const summary = String(proposal.human_summary ?? proposal.summary ?? "No summary");
  const scope = String(proposal.scope_classification ?? "localized");

  const lines = [
    "============================================================",
    `AWF IMPROVEMENT PROPOSAL REVIEW: ${impId}`,
    `Status: ${status.toUpperCase()} [${scope.toUpperCase()}]`,
    "============================================================",
    `\n1. WHAT CHANGED:\n  ${summary}`,
  ];

  const diffStats = Array.isArray(proposal.diff_stats) ? (proposal.diff_stats as Record<string, unknown>[]) : [];
  if (diffStats.length > 0) {
    lines.push("\n2. WHERE IT CHANGED:");
    for (const f of diffStats) {
      lines.push(`  • ${String(f.path)} (+${String(f.additions ?? 0)} / -${String(f.deletions ?? 0)} lines)`);
    }
  }

  if (proposal.verdict_artifact_id) {
    lines.push(
      `\n3. VALIDATION STATUS:\n  PASSED — All deterministic verification checks and automated tests passed (verdict: ${String(proposal.verdict_artifact_id)}).`,
    );
  } else {
    lines.push("\n3. VALIDATION STATUS:\n  PENDING — Awaiting verification verdict.");
  }

  if (proposal.safety_assessment) {
    lines.push(`\n4. WHY IT IS SAFE TO CONSIDER:\n  ${String(proposal.safety_assessment)}`);
  }

  const approval = proposal.approval as Record<string, unknown> | undefined;
  if (approval) {
    lines.push(`\nApproval Gate: ${String(approval.approval_id)} [${String(approval.status ?? "")}]`);
  }

  if (diffStats.length > 0) {
    lines.push("\n5. DIFF PREVIEW:");
    for (const f of diffStats) {
      lines.push(`  --- ${String(f.path)} ---`);
      const previewLines = Array.isArray(f.preview_lines) ? (f.preview_lines as string[]) : [];
      if (previewLines.length > 0) {
        for (const pl of previewLines.slice(0, 8)) {
          lines.push(`    ${pl}`);
        }
        if (f.truncated) {
          lines.push("    ... [diff truncated; inspect full patch if needed]");
        }
      }
    }
  }

  const nextAction = proposal.next_action as Record<string, unknown> | undefined;
  if (nextAction) {
    const label = String(nextAction.label ?? "Next Action");
    const cmd = String(nextAction.command ?? "");
    lines.push("\n------------------------------------------------------------");
    lines.push(`6. NEXT OPERATOR ACTION:\n  ${label}`);
    if (cmd) lines.push(`  Command:   ${cmd}`);
    if (nextAction.description) lines.push(`  Rationale: ${String(nextAction.description)}`);
    lines.push("------------------------------------------------------------");
  }

  const target = String(proposal.target_branch ?? "main");
  const base = String(proposal.base_commit ?? "").slice(0, 10);
  const cand = String(proposal.candidate_commit ?? "").slice(0, 10);
  const digest = String(proposal.diff_digest ?? "");
  lines.push(`\n[Provenance: target=${target} (${base}..${cand}) digest=${digest}]`);

  return lines.join("\n");
}

function formatImprovementList(proposals: Record<string, unknown>[]): string {
  if (proposals.length === 0) return "No improvement proposals.";
  const lines = ["Improvement Proposals:"];
  for (const p of proposals) {
    const summary = String(p.human_summary ?? p.summary ?? "No summary");
    const status = String(p.status ?? "draft").toUpperCase();
    const nextAction = p.next_action as Record<string, unknown> | undefined;
    const nextCmd = String(nextAction?.command ?? "");
    lines.push(`  - ${String(p.improvement_id)} [${status}] ${summary}`);
    if (nextCmd) lines.push(`    Next: ${nextCmd}`);
  }
  return lines.join("\n");
}

export async function dispatchAssistantInput(
  client: CommandClient,
  text: string,
  workflowRef = DEFAULT_ASSISTANT_WORKFLOW_REF,
): Promise<CommandResult> {
  const trimmed = text.trim();
  if (!trimmed) throw new CommandError("assistant input is empty");
  const result = (await client.runStart(workflowRef, { objective: trimmed })) as Record<string, unknown>;
  return { kind: "text", text: formatOutcome(result) };
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
    return { kind: "text", text: formatOutcome((await client.runStart(args[0])) as Record<string, unknown>) };
  }
  if (name === "status") {
    if (!args[0]) throw new CommandError("usage: /status <run-id>");
    return { kind: "text", text: formatOutcome((await client.runStatus(args[0])) as Record<string, unknown>) };
  }
  if (name === "runs") {
    return { kind: "text", text: formatRunList((await client.runList()) as unknown as Record<string, unknown>[]) };
  }
  if (name === "resume") {
    const results = (await client.runResume()) as Record<string, unknown>[];
    return {
      kind: "text",
      text: results.length === 0 ? "No incomplete runs to resume." : results.map(formatOutcome).join("\n\n"),
    };
  }
  if (name === "approvals") {
    return { kind: "text", text: formatApprovals((await client.approvalList()) as unknown as Record<string, unknown>[]) };
  }
  if (name === "approval") {
    if (!args[0]) throw new CommandError("usage: /approval <approval-id>");
    return { kind: "text", text: formatApprovalDetail((await client.approvalDetail(args[0])) as unknown as Record<string, unknown>) };
  }
  if (name === "approve") {
    if (!args[0]) throw new CommandError("usage: /approve <approval-id>");
    const detail = (await client.approvalDetail(args[0])) as unknown as Record<string, unknown>;
    const approved = (await client.approvalApprove(args[0])) as unknown as Record<string, unknown>;
    return { kind: "text", text: `${formatApprovalDetail(detail)}\nDecision: ${String(approved.status ?? "approved")}` };
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
  if (name === "improvements") {
    const list = (await client.improvementList()) as unknown as Record<string, unknown>[];
    return { kind: "text", text: formatImprovementList(list) };
  }
  if (name === "improvement") {
    if (!args[0]) throw new CommandError("usage: /improvement <id>");
    const prop = (await client.improvementGet(args[0])) as unknown as Record<string, unknown>;
    return { kind: "text", text: formatImprovementProposal(prop) };
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
    return { kind: "text", text: formatMemorySearch((await client.memorySearch(args.join(" "))) as unknown as Record<string, unknown>) };
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
  if (name === "control") return { kind: "text", text: formatControlSummary((await client.controlSummary()) as unknown as Record<string, unknown>) };
  if (name === "readiness") {
    return { kind: "text", text: formatReadiness((await client.systemReadiness()) as unknown as Record<string, unknown>) };
  }
  if (name === "doctor") {
    return { kind: "text", text: formatDoctor((await client.systemDoctor()) as unknown as Record<string, unknown>) };
  }
  if (name === "llm") {
    const [servers, models, status] = await Promise.all([
      client.llmServers(),
      client.llmModels(),
      client.llmServeStatus(),
    ]);
    return { kind: "text", text: formatLlmStatus({ servers, models, status }) };
  }
  if (name === "skill") {
    if (!args[0]) throw new CommandError("usage: /skill <name>@<version>");
    const [skillName, version] = splitRegistryRef(args[0], "skill");
    return { kind: "json", data: await client.registryGet("skills", skillName, version) };
  }
  if (name === "skill-run") {
    if (!args[0] || args.length < 2) throw new CommandError("usage: /skill-run <name>@<version> <input>");
    const [skillRef, ...inputParts] = args;
    return { kind: "json", data: await client.skillInvoke(skillRef, inputParts.join(" ")) };
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
