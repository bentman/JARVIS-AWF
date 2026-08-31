import { describe, expect, it, vi } from "vitest";
import {
  COMMAND_NAMES,
  DEFAULT_ASSISTANT_WORKFLOW_REF,
  HELP_TEXT,
  CommandError,
  dispatchAssistantInput,
  dispatchCommand,
  type CommandClient,
} from "../src/commands.js";
import { DEFAULT_SETTINGS } from "../src/settings.js";

function makeFakeClient(overrides: Partial<CommandClient> = {}): CommandClient {
  return {
    runStart: vi.fn().mockResolvedValue({
      run_id: "run-1",
      status: "SUCCEEDED",
      outputs: { response_text: "Default assistant response." },
    }),
    runStatus: vi.fn().mockResolvedValue({ run_id: "run-1", status: "SUCCEEDED", steps: [] }),
    runList: vi.fn().mockResolvedValue([]),
    runResume: vi.fn().mockResolvedValue([]),
    approvalList: vi.fn().mockResolvedValue([]),
    approvalDetail: vi.fn().mockImplementation(async (id: string) => {
      if (!id.startsWith("ap")) throw new Error(`no such approval: ${id}`);
      return { approval: { approval_id: id }, preview: null };
    }),
    approvalApprove: vi.fn().mockResolvedValue({ approval_id: "ap-1", status: "approved" }),
    approvalReject: vi.fn().mockResolvedValue({ approval_id: "ap-1", status: "rejected" }),
    artifactList: vi.fn().mockResolvedValue([]),
    improvementList: vi.fn().mockResolvedValue([]),
    improvementGet: vi.fn().mockImplementation(async (id: string) => {
      if (!id.startsWith("imp")) throw new Error(`no such improvement: ${id}`);
      return { improvement_id: id };
    }),
    improvementPrepare: vi.fn().mockResolvedValue({ improvement_id: "imp-1" }),
    improvementRequestMerge: vi.fn().mockResolvedValue({ approval: { approval_id: "ap-1" } }),
    improvementMerge: vi.fn().mockResolvedValue({ improvement_id: "imp-1", status: "merged" }),
    improvementReject: vi.fn().mockResolvedValue({ improvement_id: "imp-1", status: "rejected" }),
    secretListNames: vi.fn().mockResolvedValue([]),
    registryList: vi.fn().mockResolvedValue([]),
    workflowAuthorDraft: vi.fn().mockResolvedValue({ proposal_id: "p1", status: "draft" }),
    proposalGet: vi.fn().mockResolvedValue({ proposal_id: "p1", status: "draft" }),
    proposalUpdate: vi.fn().mockResolvedValue({ proposal_id: "p1", status: "draft" }),
    proposalPublish: vi.fn().mockResolvedValue({ proposal: { proposal_id: "p1", status: "published" } }),
    proposalReject: vi.fn().mockResolvedValue({ proposal_id: "p1", status: "rejected" }),
    memorySearch: vi.fn().mockResolvedValue({ semantic: [], episodic: [] }),
    memoryGet: vi.fn().mockResolvedValue({ ref: "pref@1.0.0" }),
    memoryPropose: vi.fn().mockResolvedValue({ proposal_id: "p1", status: "draft" }),
    memoryPublish: vi.fn().mockResolvedValue({ proposal: { proposal_id: "p1", status: "published" } }),
    memoryReject: vi.fn().mockResolvedValue({ proposal_id: "p1", status: "rejected" }),
    memoryBlock: vi.fn().mockResolvedValue({ ref: "pref@1.0.0", trust_status: "blocked" }),
    controlSummary: vi.fn().mockResolvedValue({ runs: [], approvals: [] }),
    controlRunDetail: vi.fn().mockResolvedValue({ run: { run_id: "run-1" } }),
    systemReadiness: vi.fn().mockResolvedValue({ profile_id: "linux-x64-cpu" }),
    systemDoctor: vi.fn().mockResolvedValue({
      status: "warn",
      checks: [{ name: "frontend", status: "warn", summary: "npm missing" }],
      first_run_command: 'awf run assistant-default@1.0.0 --objective "check the system"',
    }),
    llmServers: vi.fn().mockResolvedValue({ default_server: "llama-server" }),
    llmModels: vi.fn().mockResolvedValue({ local_models: [] }),
    llmServeStatus: vi.fn().mockResolvedValue({ state: "stopped" }),
    registryGet: vi.fn().mockResolvedValue({ kind: "skills", name: "demo", version: "1.0.0" }),
    skillInvoke: vi.fn().mockResolvedValue({ ref: "demo@1.0.0", response_text: "Skill response." }),
    sessionStart: vi.fn().mockResolvedValue({ session_id: "s1" }),
    sessionShow: vi.fn().mockResolvedValue({ session_id: "s1", entries: [] }),
    episodicSearch: vi.fn().mockResolvedValue([]),
    episodicTimeline: vi.fn().mockResolvedValue({ run: { run_id: "run-1" } }),
    ...overrides,
  } as CommandClient;
}

describe("dispatchCommand", () => {
  it("/help returns the built-in command list as text", async () => {
    const client = makeFakeClient();
    const result = await dispatchCommand(client, "/help", DEFAULT_SETTINGS);
    expect(result).toEqual({ kind: "text", text: HELP_TEXT });
  });

  it("derives autocomplete command names from help text", () => {
    const helpCommands = [
      ...new Set(
        HELP_TEXT.split("\n")
          .map((line) => line.match(/^\s*\/([a-z0-9-]+)/)?.[1])
          .filter(Boolean),
      ),
    ];

    expect(COMMAND_NAMES).toEqual(helpCommands);
    // Grouped commands autocomplete on the group name, not each subcommand.
    expect(COMMAND_NAMES).toContain("review");
    expect(COMMAND_NAMES).toContain("memory");
  });

  it("groups help text by task and alphabetizes within each group after Start here", () => {
    const sections: string[][] = [];
    for (const line of HELP_TEXT.split("\n")) {
      if (/^\S.*:$/.test(line)) sections.push([]);
      const name = line.match(/^\s+\/([a-z0-9-]+)/)?.[1];
      if (name && sections.length > 0) sections[sections.length - 1].push(name);
    }

    // "Start here" is deliberately ordered as the operator's path, not A-Z.
    expect(sections.length).toBeGreaterThan(1);
    for (const names of sections.slice(1)) {
      expect(names).toEqual([...names].sort((left, right) => left.localeCompare(right)));
    }
  });

  it("/run calls runStart with the workflow ref", async () => {
    const client = makeFakeClient();
    const result = await dispatchCommand(client, "/run demo@1.0.0", DEFAULT_SETTINGS);
    expect(client.runStart).toHaveBeenCalledWith("demo@1.0.0");
    expect(result.kind).toBe("text");
    if (result.kind === "text") expect(result.text).toContain("Result: Default assistant response.");
  });

  it("plain assistant input starts the default workflow with objective text", async () => {
    const client = makeFakeClient();
    const result = await dispatchAssistantInput(client, "summarize the active run", DEFAULT_ASSISTANT_WORKFLOW_REF);

    expect(client.runStart).toHaveBeenCalledWith(DEFAULT_ASSISTANT_WORKFLOW_REF, {
      objective: "summarize the active run",
    });
    expect(result.kind).toBe("text");
    if (result.kind === "text") {
      expect(result.text).toContain("Run: run-1");
      expect(result.text).toContain("Result: Default assistant response.");
    }
  });

  it("plain assistant input can use the configured default workflow", async () => {
    const client = makeFakeClient();
    await dispatchAssistantInput(client, "summarize the active run", "operator-default@2.0.0");

    expect(client.runStart).toHaveBeenCalledWith("operator-default@2.0.0", {
      objective: "summarize the active run",
    });
  });

  it("/run without an argument raises CommandError", async () => {
    const client = makeFakeClient();
    await expect(dispatchCommand(client, "/run", DEFAULT_SETTINGS)).rejects.toBeInstanceOf(CommandError);
  });

  it("/status calls runStatus with the run id", async () => {
    const client = makeFakeClient();
    const result = await dispatchCommand(client, "/status run-1", DEFAULT_SETTINGS);
    expect(client.controlRunDetail).toHaveBeenCalledWith("run-1");
    expect(result.kind).toBe("text");
  });

  it("/runs calls runList", async () => {
    const client = makeFakeClient();
    const result = await dispatchCommand(client, "/status", DEFAULT_SETTINGS);
    expect(client.runList).toHaveBeenCalled();
    expect(result).toEqual({ kind: "text", text: "No runs." });
  });

  it("/resume calls runResume", async () => {
    const client = makeFakeClient();
    const result = await dispatchCommand(client, "/system resume", DEFAULT_SETTINGS);
    expect(client.runResume).toHaveBeenCalled();
    expect(result).toEqual({ kind: "text", text: "No incomplete runs to resume." });
  });

  it("/review list calls approvalList and improvementList", async () => {
    const client = makeFakeClient();
    await dispatchCommand(client, "/review list", DEFAULT_SETTINGS);
    expect(client.approvalList).toHaveBeenCalled();
  });

  it("/review show calls approvalDetail for an approval id", async () => {
    const client = makeFakeClient();
    await dispatchCommand(client, "/review show ap-1", DEFAULT_SETTINGS);
    expect(client.approvalDetail).toHaveBeenCalledWith("ap-1");
  });

  it("/review approve calls approvalApprove with the id", async () => {
    const client = makeFakeClient();
    await dispatchCommand(client, "/review approve ap-1", DEFAULT_SETTINGS);
    expect(client.approvalApprove).toHaveBeenCalledWith("ap-1");
  });

  it("/review reject joins remaining args as the reason", async () => {
    const client = makeFakeClient();
    await dispatchCommand(client, "/review reject ap-1 not safe enough", DEFAULT_SETTINGS);
    expect(client.approvalReject).toHaveBeenCalledWith("ap-1", "not safe enough");
  });

  it("/review reject without a reason raises CommandError", async () => {
    const client = makeFakeClient();
    await expect(dispatchCommand(client, "/review reject ap-1", DEFAULT_SETTINGS)).rejects.toBeInstanceOf(CommandError);
  });

  it("/artifacts calls artifactList with the run id", async () => {
    const client = makeFakeClient();
    await dispatchCommand(client, "/artifacts run-1", DEFAULT_SETTINGS);
    expect(client.artifactList).toHaveBeenCalledWith("run-1");
  });

  it("dispatches improvement commands and renders human-readable review", async () => {
    const fakeProposal = {
      improvement_id: "imp-1",
      status: "ready_for_review",
      human_summary: "1 file changed (+5 / -1 lines) in main.py. Validation passed.",
      scope_classification: "localized",
      safety_assessment: "Localized change bounded to worktree sandbox.",
      verdict_artifact_id: "art-v-1",
      diff_stats: [
        {
          path: "main.py",
          additions: 5,
          deletions: 1,
          preview_lines: ["@@ -1,3 +1,4 @@", "+import foo"],
        },
      ],
      next_action: {
        action: "request_merge",
        label: "Request merge approval",
        command: "awf review request-merge imp-1",
      },
    };
    const client = makeFakeClient({
      improvementList: vi.fn().mockResolvedValue([fakeProposal]),
      improvementGet: vi.fn().mockResolvedValue(fakeProposal),
      approvalDetail: vi.fn().mockImplementation(async (id: string) => {
        if (!id.startsWith("ap")) throw new Error(`no such approval: ${id}`);
        return {
          approval: { approval_id: id, status: "pending", risk_class: "R2", action_digest: "sha256:123" },
          preview: {
            kind: "improvement_merge",
            human_summary: "1 file changed (+5 / -1 lines) in main.py. Validation passed.",
            safety_assessment: "Localized change bounded to worktree sandbox.",
            verdict_artifact_id: "art-v-1",
            diff_stats: fakeProposal.diff_stats,
          },
        };
      }),
    });

    const listRes = await dispatchCommand(client, "/review list", DEFAULT_SETTINGS);
    expect(client.improvementList).toHaveBeenCalled();
    expect(listRes.kind).toBe("text");
    if (listRes.kind === "text") {
      expect(listRes.text).toContain("imp-1 [READY_FOR_REVIEW]");
      expect(listRes.text).toContain("Next: awf review request-merge imp-1");
    }

    const showRes = await dispatchCommand(client, "/review show imp-1", DEFAULT_SETTINGS);
    expect(client.improvementGet).toHaveBeenCalledWith("imp-1");
    expect(showRes.kind).toBe("text");
    if (showRes.kind === "text") {
      expect(showRes.text).toContain("AWF IMPROVEMENT PROPOSAL REVIEW: imp-1");
      expect(showRes.text).toContain("1. WHAT CHANGED:\n  1 file changed (+5 / -1 lines) in main.py.");
      expect(showRes.text).toContain("2. WHERE IT CHANGED:\n  • main.py (+5 / -1 lines)");
      expect(showRes.text).toContain("3. VALIDATION STATUS:\n  PASSED");
      expect(showRes.text).toContain("4. WHY IT IS SAFE TO CONSIDER:\n  Localized change bounded to worktree sandbox.");
      expect(showRes.text).toContain("+import foo");
      expect(showRes.text).toContain("6. NEXT OPERATOR ACTION:\n  Request merge approval");
    }

    const apprRes = await dispatchCommand(client, "/review show ap-1", DEFAULT_SETTINGS);
    expect(client.approvalDetail).toHaveBeenCalledWith("ap-1");
    expect(apprRes.kind).toBe("text");
    if (apprRes.kind === "text") {
      expect(apprRes.text).toContain("AWF APPROVAL REVIEW: ap-1 [PENDING]");
      expect(apprRes.text).toContain("1. WHAT IS BEING APPROVED:\n  1 file changed (+5 / -1 lines) in main.py.");
      expect(apprRes.text).toContain("2. WHY IT IS SAFE TO APPROVE:\n  Localized change bounded to worktree sandbox.");
      expect(apprRes.text).toContain("+import foo");
      expect(apprRes.text).toContain("Approve: /review approve ap-1");
    }

    await dispatchCommand(client, "/review prepare run-1 focused fix", DEFAULT_SETTINGS);
    expect(client.improvementPrepare).toHaveBeenCalledWith("run-1", "focused fix");

    await dispatchCommand(client, "/review request-merge imp-1", DEFAULT_SETTINGS);
    expect(client.improvementRequestMerge).toHaveBeenCalledWith("imp-1");

    await dispatchCommand(client, "/review merge imp-1 ap-1", DEFAULT_SETTINGS);
    expect(client.improvementMerge).toHaveBeenCalledWith("imp-1", "ap-1");

    await dispatchCommand(client, "/review reject imp-1 not ready", DEFAULT_SETTINGS);
    expect(client.improvementReject).toHaveBeenCalledWith("imp-1", "not ready");
  });

  it.each([
    ["/agents", "agents"],
    ["/skills", "skills"],
    ["/workflows", "workflows"],
    ["/capabilities", "capabilities"],
    ["/mcp", "mcp"],
    ["/model", "model-profiles"],
    ["/voices", "voice-profiles"],
  ])("%s calls registryList(%s)", async (command, kind) => {
    const client = makeFakeClient();
    await dispatchCommand(client, command, DEFAULT_SETTINGS);
    expect(client.registryList).toHaveBeenCalledWith(kind);
  });

  it("/secrets calls secretListNames (names only)", async () => {
    const client = makeFakeClient();
    await dispatchCommand(client, "/system secrets", DEFAULT_SETTINGS);
    expect(client.secretListNames).toHaveBeenCalled();
  });

  it("/review draft calls workflowAuthorDraft with the objective text", async () => {
    const client = makeFakeClient();
    await dispatchCommand(client, "/review draft make a demo workflow", DEFAULT_SETTINGS);
    expect(client.workflowAuthorDraft).toHaveBeenCalledWith({ objective: "make a demo workflow" });
  });

  it("/review show calls proposalGet", async () => {
    const client = makeFakeClient();
    await dispatchCommand(client, "/review show p1", DEFAULT_SETTINGS);
    expect(client.proposalGet).toHaveBeenCalledWith("p1");
  });

  it("/review publish calls proposalPublish", async () => {
    const client = makeFakeClient();
    await dispatchCommand(client, "/review publish p1 abc", DEFAULT_SETTINGS);
    expect(client.proposalPublish).toHaveBeenCalledWith("p1", "abc");
  });

  it("/review routes subcommands to their handlers", async () => {
    const client = makeFakeClient();

    await dispatchCommand(client, "/review list", DEFAULT_SETTINGS);
    expect(client.improvementList).toHaveBeenCalled();

    await dispatchCommand(client, "/review merge imp-1 ap-1", DEFAULT_SETTINGS);
    expect(client.improvementMerge).toHaveBeenCalledWith("imp-1", "ap-1");

    await dispatchCommand(client, "/review draft ship the thing", DEFAULT_SETTINGS);
    expect(client.workflowAuthorDraft).toHaveBeenCalledWith({ objective: "ship the thing" });
  });

  it("/review show falls back across id kinds", async () => {
    // The fake resolves each id only in its own namespace, so the command has
    // to walk approval -> change -> draft the way the real surface does.
    const approvalClient = makeFakeClient();
    await dispatchCommand(approvalClient, "/review show ap-1", DEFAULT_SETTINGS);
    expect(approvalClient.approvalDetail).toHaveBeenCalledWith("ap-1");
    expect(approvalClient.improvementGet).not.toHaveBeenCalled();

    const changeClient = makeFakeClient();
    await dispatchCommand(changeClient, "/review show imp-1", DEFAULT_SETTINGS);
    expect(changeClient.improvementGet).toHaveBeenCalledWith("imp-1");
    expect(changeClient.proposalGet).not.toHaveBeenCalled();

    const draftClient = makeFakeClient();
    await dispatchCommand(draftClient, "/review show p1", DEFAULT_SETTINGS);
    expect(draftClient.proposalGet).toHaveBeenCalledWith("p1");
  });

  it("/memory keeps the legacy direct-ref spelling working alongside subcommands", async () => {
    const grouped = makeFakeClient();
    await dispatchCommand(grouped, "/memory get pref@1.0.0", DEFAULT_SETTINGS);
    expect(grouped.memoryGet).toHaveBeenCalledWith("pref@1.0.0");

    const legacy = makeFakeClient();
    await dispatchCommand(legacy, "/memory pref@1.0.0", DEFAULT_SETTINGS);
    expect(legacy.memoryGet).toHaveBeenCalledWith("pref@1.0.0");
  });

  it("/review names its subcommands when given none", async () => {
    const client = makeFakeClient();
    await expect(dispatchCommand(client, "/review", DEFAULT_SETTINGS)).rejects.toThrow(/usage: \/review </);
  });

  it("/review reject joins remaining args as reason", async () => {
    const client = makeFakeClient();
    await dispatchCommand(client, "/review reject p1 not useful", DEFAULT_SETTINGS);
    expect(client.proposalReject).toHaveBeenCalledWith("p1", "not useful");
  });

  it("dispatches memory, session, and episodic commands", async () => {
    const client = makeFakeClient();

    await dispatchCommand(client, "/memory search targeted tests", DEFAULT_SETTINGS);
    expect(client.memorySearch).toHaveBeenCalledWith("targeted tests");

    await dispatchCommand(client, "/memory pref@1.0.0", DEFAULT_SETTINGS);
    expect(client.memoryGet).toHaveBeenCalledWith("pref@1.0.0");

    await dispatchCommand(client, "/memory propose /tmp/memory.yaml", DEFAULT_SETTINGS);
    expect(client.memoryPropose).toHaveBeenCalledWith("/tmp/memory.yaml");

    await dispatchCommand(client, "/memory publish p1 abc", DEFAULT_SETTINGS);
    expect(client.memoryPublish).toHaveBeenCalledWith("p1", "abc");

    await dispatchCommand(client, "/memory reject p1 not useful", DEFAULT_SETTINGS);
    expect(client.memoryReject).toHaveBeenCalledWith("p1", "not useful");

    await dispatchCommand(client, "/memory block pref@1.0.0", DEFAULT_SETTINGS);
    expect(client.memoryBlock).toHaveBeenCalledWith("pref@1.0.0");

    await dispatchCommand(client, "/memory session-start demo session", DEFAULT_SETTINGS);
    expect(client.sessionStart).toHaveBeenCalledWith("demo session");

    await dispatchCommand(client, "/memory session-show s1", DEFAULT_SETTINGS);
    expect(client.sessionShow).toHaveBeenCalledWith("s1");

    await dispatchCommand(client, "/memory events targeted", DEFAULT_SETTINGS);
    expect(client.episodicSearch).toHaveBeenCalledWith("targeted");

    await dispatchCommand(client, "/memory timeline run-1", DEFAULT_SETTINGS);
    expect(client.episodicTimeline).toHaveBeenCalledWith("run-1");
  });

  it("dispatches control center status commands", async () => {
    const client = makeFakeClient();

    await dispatchCommand(client, "/control", DEFAULT_SETTINGS);
    expect(client.controlSummary).toHaveBeenCalled();

    await dispatchCommand(client, "/system readiness", DEFAULT_SETTINGS);
    expect(client.systemReadiness).toHaveBeenCalled();

    await dispatchCommand(client, "/doctor", DEFAULT_SETTINGS);
    expect(client.systemDoctor).toHaveBeenCalled();

    await dispatchCommand(client, "/system llm", DEFAULT_SETTINGS);
    expect(client.llmServers).toHaveBeenCalled();
    expect(client.llmModels).toHaveBeenCalled();
    expect(client.llmServeStatus).toHaveBeenCalled();
  });

  it("/skill inspects a registry Skill without invoking it", async () => {
    const client = makeFakeClient();

    await dispatchCommand(client, "/skill demo@1.0.0", DEFAULT_SETTINGS);

    expect(client.registryGet).toHaveBeenCalledWith("skills", "demo", "1.0.0");
  });

  it("/skill-run invokes a registry Skill with operator input", async () => {
    const client = makeFakeClient();

    await dispatchCommand(client, "/skill-run demo@1.0.0 apply the recipe", DEFAULT_SETTINGS);

    expect(client.skillInvoke).toHaveBeenCalledWith("demo@1.0.0", "apply the recipe");
  });

  it("/skill requires a name@version ref", async () => {
    const client = makeFakeClient();

    await expect(dispatchCommand(client, "/skill demo", DEFAULT_SETTINGS)).rejects.toBeInstanceOf(CommandError);
  });

  it("/settings, /theme, /keybindings never touch the protocol client", async () => {
    const client = makeFakeClient();
    const settings = { ...DEFAULT_SETTINGS, theme: "dark" as const };

    const settingsResult = await dispatchCommand(client, "/settings", settings);
    const themeResult = await dispatchCommand(client, "/theme", settings);
    const keybindingsResult = await dispatchCommand(client, "/keybindings", settings);

    expect(settingsResult).toEqual({ kind: "json", data: settings });
    expect(themeResult).toEqual({ kind: "json", data: { theme: "dark" } });
    expect(keybindingsResult).toEqual({ kind: "json", data: settings.keybindings });
    for (const fn of Object.values(client)) expect(fn).not.toHaveBeenCalled();
  });

  it("/clear returns a clear result", async () => {
    const client = makeFakeClient();
    const result = await dispatchCommand(client, "/clear", DEFAULT_SETTINGS);
    expect(result).toEqual({ kind: "clear" });
  });

  it("/quit returns a quit result", async () => {
    const client = makeFakeClient();
    const result = await dispatchCommand(client, "/quit", DEFAULT_SETTINGS);
    expect(result).toEqual({ kind: "quit" });
  });

  it("rejects an unknown command", async () => {
    const client = makeFakeClient();
    await expect(dispatchCommand(client, "/not-a-real-command", DEFAULT_SETTINGS)).rejects.toBeInstanceOf(
      CommandError,
    );
  });

  it("rejects input that is not a slash command", async () => {
    const client = makeFakeClient();
    await expect(dispatchCommand(client, "plain text", DEFAULT_SETTINGS)).rejects.toBeInstanceOf(CommandError);
  });
});
