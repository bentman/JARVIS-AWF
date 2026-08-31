"""Canonical JSON-RPC method manifest.

This is the source for generated protocol mirrors. Keep transport plumbing,
domain result types, and argparse implementation outside this file.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class MethodSpec:
    name: str
    handler: str
    python_args: str
    ts_method: str
    cli_path: tuple[str, ...] = ()
    run_timeout: bool = False


METHODS: tuple[MethodSpec, ...] = (
    MethodSpec(
        "awf/run.start",
        "awf.ops.run.op_run_start",
        'repo_root, conn, workflow_ref=params["workflow"], input_data=params.get("input", {})',
        "runStart(workflowRef: string, input: Record<string, unknown> = {}): Promise<RunStartResult> {\n"
        '    return this.call("awf/run.start", { workflow: workflowRef, input }, this.runCallTimeoutMs);\n'
        "  }",
        ("run",),
        True,
    ),
    MethodSpec(
        "awf/run.status",
        "awf.ops.run.op_run_status",
        'conn, run_id=params["runId"]',
        'runStatus(runId: string): Promise<RunStatus> {\n    return this.call("awf/run.status", { runId });\n  }',
        ("status",),
    ),
    MethodSpec(
        "awf/run.list",
        "awf.ops.run.op_run_list",
        "conn",
        'runList(): Promise<RunSummary[]> {\n    return this.call("awf/run.list", {});\n  }',
        ("status",),
    ),
    MethodSpec(
        "awf/run.resume",
        "awf.ops.run.op_run_resume",
        "repo_root, conn",
        'runResume(): Promise<RunStartResult[]> {\n    return this.call("awf/run.resume", {}, this.runCallTimeoutMs);\n  }',
        ("system", "resume"),
        True,
    ),
    MethodSpec(
        "awf/approval.list",
        "awf.ops.approval.op_approval_list",
        "conn",
        'approvalList(): Promise<Approval[]> {\n    return this.call("awf/approval.list", {});\n  }',
        ("review", "list"),
    ),
    MethodSpec(
        "awf/approval.detail",
        "awf.ops.approval.op_approval_detail",
        'conn, approval_id=params["approvalId"]',
        "approvalDetail(approvalId: string): Promise<ApprovalDetail> {\n"
        '    return this.call("awf/approval.detail", { approvalId });\n'
        "  }",
    ),
    MethodSpec(
        "awf/approval.approve",
        "awf.ops.approval.op_approval_approve",
        'conn, approval_id=params["approvalId"], channel=params.get("channel", "manual"), risk_class=params.get("riskClass")',
        "approvalApprove(approvalId: string, options: ApprovalApproveOptions = {}): Promise<Approval> {\n"
        '    return this.call("awf/approval.approve", { approvalId, channel: options.channel, riskClass: options.riskClass });\n'
        "  }",
        ("review", "approve"),
    ),
    MethodSpec(
        "awf/approval.reject",
        "awf.ops.approval.op_approval_reject",
        'conn, approval_id=params["approvalId"], reason=params.get("reason", "")',
        "approvalReject(approvalId: string, reason: string): Promise<Approval> {\n"
        '    return this.call("awf/approval.reject", { approvalId, reason });\n'
        "  }",
        ("review", "reject"),
    ),
    MethodSpec(
        "awf/machine.actionPreview",
        "awf.ops.approval.op_machine_action_preview",
        'conn, approval_id=params["approvalId"]',
        "machineActionPreview(approvalId: string): Promise<MachineActionPreview> {\n"
        '    return this.call("awf/machine.actionPreview", { approvalId });\n'
        "  }",
    ),
    MethodSpec(
        "awf/improvement.list",
        "awf.ops.improvement.op_improvement_list",
        'conn, status=params.get("status")',
        "improvementList(status?: string): Promise<ImprovementProposal[]> {\n"
        '    return this.call("awf/improvement.list", { status });\n'
        "  }",
        ("review", "list"),
    ),
    MethodSpec(
        "awf/improvement.get",
        "awf.ops.improvement.op_improvement_get",
        'conn, improvement_id=params["improvementId"]',
        "improvementGet(improvementId: string): Promise<ImprovementProposal> {\n"
        '    return this.call("awf/improvement.get", { improvementId });\n'
        "  }",
        ("review", "show"),
    ),
    MethodSpec(
        "awf/improvement.prepare",
        "awf.ops.improvement.op_improvement_prepare",
        'repo_root, conn, run_id=params["runId"], summary=params.get("summary")',
        "improvementPrepare(runId: string, summary?: string): Promise<ImprovementProposal> {\n"
        '    return this.call("awf/improvement.prepare", { runId, summary });\n'
        "  }",
        ("review", "prepare"),
    ),
    MethodSpec(
        "awf/improvement.markReady",
        "awf.ops.improvement.op_improvement_mark_ready",
        'repo_root, conn, improvement_id=params["improvementId"], verdict_artifact_id=params["verdictArtifactId"], validation_artifact_ids=params.get("validationArtifactIds", [])',
        "improvementMarkReady(\n"
        "    improvementId: string,\n"
        "    verdictArtifactId: string,\n"
        "    validationArtifactIds: string[] = [],\n"
        "  ): Promise<ImprovementProposal> {\n"
        '    return this.call("awf/improvement.markReady", { improvementId, verdictArtifactId, validationArtifactIds });\n'
        "  }",
        ("review", "mark-ready"),
    ),
    MethodSpec(
        "awf/improvement.requestMerge",
        "awf.ops.improvement.op_improvement_request_merge",
        'repo_root, conn, improvement_id=params["improvementId"]',
        "improvementRequestMerge(improvementId: string): Promise<Record<string, unknown>> {\n"
        '    return this.call("awf/improvement.requestMerge", { improvementId });\n'
        "  }",
        ("review", "request-merge"),
    ),
    MethodSpec(
        "awf/improvement.merge",
        "awf.ops.improvement.op_improvement_merge",
        'repo_root, conn, improvement_id=params["improvementId"], approval_id=params["approvalId"]',
        "improvementMerge(improvementId: string, approvalId: string): Promise<ImprovementProposal> {\n"
        '    return this.call("awf/improvement.merge", { improvementId, approvalId });\n'
        "  }",
        ("review", "merge"),
    ),
    MethodSpec(
        "awf/improvement.reject",
        "awf.ops.improvement.op_improvement_reject",
        'repo_root, conn, improvement_id=params["improvementId"], reason=params.get("reason")',
        "improvementReject(improvementId: string, reason?: string): Promise<ImprovementProposal> {\n"
        '    return this.call("awf/improvement.reject", { improvementId, reason });\n'
        "  }",
        ("review", "reject"),
    ),
    MethodSpec(
        "awf/artifact.list",
        "awf.ops.artifact.op_artifact_list",
        'conn, run_id=params["runId"]',
        'artifactList(runId: string): Promise<Artifact[]> {\n    return this.call("awf/artifact.list", { runId });\n  }',
        ("status",),
    ),
    MethodSpec(
        "awf/artifact.read",
        "awf.ops.artifact.op_artifact_read",
        'conn, artifact_id=params["artifactId"], artifacts_root=artifacts_dir(repo_root)',
        "artifactRead(artifactId: string): Promise<Artifact & { content: string }> {\n"
        '    return this.call("awf/artifact.read", { artifactId });\n'
        "  }",
    ),
    MethodSpec(
        "awf/registry.list",
        "awf.ops.registry.op_registry_list",
        'repo_root, kind=params["kind"], conn=conn',
        'registryList(kind: string): Promise<RegistryEntry[]> {\n    return this.call("awf/registry.list", { kind });\n  }',
    ),
    MethodSpec(
        "awf/registry.get",
        "awf.ops.registry.op_registry_get",
        'repo_root, conn, kind=params["kind"], name=params["name"], version=params["version"]',
        "registryGet(kind: string, name: string, version: string): Promise<Record<string, unknown>> {\n"
        '    return this.call("awf/registry.get", { kind, name, version });\n'
        "  }",
    ),
    MethodSpec(
        "awf/registry.validate",
        "awf.ops.registry.op_registry_validate",
        'Path(params["path"]), kind=params.get("kind")',
        "registryValidate(path: string, kind?: string): Promise<Record<string, unknown>> {\n"
        '    return this.call("awf/registry.validate", kind ? { path, kind } : { path });\n'
        "  }",
        ("registry", "validate"),
    ),
    MethodSpec(
        "awf/registry.publish",
        "awf.ops.registry.op_registry_publish",
        'repo_root, conn, path=Path(params["path"]), kind=params["kind"]',
        "registryPublish(path: string, kind: string): Promise<Record<string, unknown>> {\n"
        '    return this.call("awf/registry.publish", { path, kind });\n'
        "  }",
        ("registry", "publish"),
    ),
    MethodSpec(
        "awf/registry.reindex",
        "awf.ops.registry.op_registry_reindex",
        "repo_root, conn",
        'registryReindex(): Promise<Record<string, unknown>> {\n    return this.call("awf/registry.reindex", {});\n  }',
        ("registry", "reindex"),
    ),
    MethodSpec(
        "awf/registry.retire",
        "awf.ops.registry.op_registry_retire",
        'conn, kind=params["kind"], name=params["name"], version=params["version"]',
        "registryRetire(kind: string, name: string, version: string): Promise<Record<string, unknown>> {\n"
        '    return this.call("awf/registry.retire", { kind, name, version });\n'
        "  }",
        ("registry", "retire"),
    ),
    MethodSpec(
        "awf/registry.trust",
        "awf.ops.registry.op_registry_trust",
        'conn, kind=params["kind"], name=params["name"], version=params["version"], status=params["status"]',
        "registryTrust(kind: string, name: string, version: string, status: string): Promise<Record<string, unknown>> {\n"
        '    return this.call("awf/registry.trust", { kind, name, version, status });\n'
        "  }",
        ("registry", "trust"),
    ),
    MethodSpec(
        "awf/skill.invoke",
        "awf.ops.registry.op_skill_invoke",
        'repo_root, conn, ref=params["ref"], input_text=params["input"], profile_ref=params.get("profile", DEFAULT_AUTHOR_PROFILE)',
        "skillInvoke(ref: string, input: string, profile?: string): Promise<Record<string, unknown>> {\n"
        '    return this.call("awf/skill.invoke", { ref, input, profile });\n'
        "  }",
    ),
    MethodSpec(
        "awf/workflow.authorDraft",
        "awf.ops.authoring.op_workflow_author_draft",
        'repo_root, conn, objective=params["objective"], name=params.get("name"), version=params.get("version"), profile_ref=params.get("profile", DEFAULT_AUTHOR_PROFILE)',
        "workflowAuthorDraft(options: {\n"
        "    objective: string;\n"
        "    name?: string;\n"
        "    version?: string;\n"
        "    profile?: string;\n"
        "  }): Promise<Proposal> {\n"
        '    return this.call("awf/workflow.authorDraft", options);\n'
        "  }",
        ("review", "draft"),
    ),
    MethodSpec(
        "awf/proposal.get",
        "awf.ops.authoring.op_proposal_get",
        'repo_root, conn, proposal_id=params["proposalId"]',
        'proposalGet(proposalId: string): Promise<Proposal> {\n    return this.call("awf/proposal.get", { proposalId });\n  }',
        ("review", "show"),
    ),
    MethodSpec(
        "awf/proposal.update",
        "awf.ops.authoring.op_proposal_update",
        'repo_root, conn, proposal_id=params["proposalId"], content=params["content"], summary=params.get("summary")',
        "proposalUpdate(proposalId: string, content: string, summary?: string): Promise<Proposal> {\n"
        '    return this.call("awf/proposal.update", { proposalId, content, summary });\n'
        "  }",
        ("review", "update"),
    ),
    MethodSpec(
        "awf/proposal.publish",
        "awf.ops.authoring.op_proposal_publish",
        'repo_root, conn, proposal_id=params["proposalId"], digest=params["digest"]',
        "proposalPublish(proposalId: string, digest: string): Promise<Record<string, unknown>> {\n"
        '    return this.call("awf/proposal.publish", { proposalId, digest });\n'
        "  }",
        ("review", "publish"),
    ),
    MethodSpec(
        "awf/proposal.reject",
        "awf.ops.authoring.op_proposal_reject",
        'repo_root, conn, proposal_id=params["proposalId"], reason=params.get("reason")',
        "proposalReject(proposalId: string, reason?: string): Promise<Proposal> {\n"
        '    return this.call("awf/proposal.reject", { proposalId, reason });\n'
        "  }",
        ("review", "reject"),
    ),
    MethodSpec(
        "awf/memory.search",
        "awf.ops.memory.op_memory_search",
        'repo_root, conn, query=params["query"], profile_ref=params.get("profile", "default@1.0.0")',
        'memorySearch(query: string, profile = "default@1.0.0"): Promise<MemorySearchResult> {\n'
        '    return this.call("awf/memory.search", { query, profile });\n'
        "  }",
        ("memory", "search"),
    ),
    MethodSpec(
        "awf/memory.get",
        "awf.ops.memory.op_memory_get",
        'repo_root, conn, ref=params["ref"]',
        'memoryGet(ref: string): Promise<Record<string, unknown>> {\n    return this.call("awf/memory.get", { ref });\n  }',
        ("memory", "get"),
    ),
    MethodSpec(
        "awf/memory.propose",
        "awf.ops.memory.op_memory_propose",
        'repo_root, conn, path=Path(params["path"]), summary=params.get("summary")',
        "memoryPropose(path: string, summary?: string): Promise<Proposal> {\n"
        '    return this.call("awf/memory.propose", { path, summary });\n'
        "  }",
        ("memory", "propose"),
    ),
    MethodSpec(
        "awf/memory.publish",
        "awf.ops.memory.op_memory_publish",
        'repo_root, conn, proposal_id=params["proposalId"], digest=params["digest"]',
        "memoryPublish(proposalId: string, digest: string): Promise<Record<string, unknown>> {\n"
        '    return this.call("awf/memory.publish", { proposalId, digest });\n'
        "  }",
        ("memory", "publish"),
    ),
    MethodSpec(
        "awf/memory.reject",
        "awf.ops.memory.op_memory_reject",
        'repo_root, conn, proposal_id=params["proposalId"], reason=params.get("reason")',
        "memoryReject(proposalId: string, reason?: string): Promise<Proposal> {\n"
        '    return this.call("awf/memory.reject", { proposalId, reason });\n'
        "  }",
        ("memory", "reject"),
    ),
    MethodSpec(
        "awf/memory.block",
        "awf.ops.memory.op_memory_block",
        'conn, ref=params["ref"]',
        'memoryBlock(ref: string): Promise<Record<string, unknown>> {\n    return this.call("awf/memory.block", { ref });\n  }',
        ("memory", "block"),
    ),
    MethodSpec(
        "awf/session.start",
        "awf.ops.memory.op_session_start",
        'conn, title=params.get("title"), expires_at=params.get("expiresAt")',
        "sessionStart(title?: string, expiresAt?: string): Promise<Record<string, unknown>> {\n"
        '    return this.call("awf/session.start", { title, expiresAt });\n'
        "  }",
        ("memory", "session-start"),
    ),
    MethodSpec(
        "awf/session.append",
        "awf.ops.memory.op_session_append",
        'conn, session_id=params["sessionId"], role=params["role"], content=params["content"], summary=params.get("summary")',
        "sessionAppend(\n"
        "    sessionId: string,\n"
        "    role: string,\n"
        "    content: Record<string, unknown>,\n"
        "    summary?: string,\n"
        "  ): Promise<Record<string, unknown>> {\n"
        '    return this.call("awf/session.append", { sessionId, role, content, summary });\n'
        "  }",
        ("memory", "session-append"),
    ),
    MethodSpec(
        "awf/session.show",
        "awf.ops.memory.op_session_show",
        'conn, session_id=params["sessionId"]',
        "sessionShow(sessionId: string): Promise<Record<string, unknown>> {\n"
        '    return this.call("awf/session.show", { sessionId });\n'
        "  }",
        ("memory", "session-show"),
    ),
    MethodSpec(
        "awf/session.summarize",
        "awf.ops.memory.op_session_summarize",
        'conn, session_id=params["sessionId"], summary=params.get("summary")',
        "sessionSummarize(sessionId: string, summary?: string): Promise<Record<string, unknown>> {\n"
        '    return this.call("awf/session.summarize", { sessionId, summary });\n'
        "  }",
        ("memory", "session-summarize"),
    ),
    MethodSpec(
        "awf/voice.sessionStart",
        "awf.ops.voice.op_voice_session_start",
        'conn, title=params.get("title"), wake_enabled=bool(params.get("wakeEnabled", False))',
        "voiceSessionStart(title?: string, wakeEnabled = false): Promise<VoiceSessionResult> {\n"
        '    return this.call("awf/voice.sessionStart", { title, wakeEnabled });\n'
        "  }",
    ),
    MethodSpec(
        "awf/voice.event",
        "awf.ops.voice.op_voice_session_event",
        'conn, voice_session_id=params["voiceSessionId"], frame_type=params["frameType"], payload=params.get("payload", {}), turn_id=params.get("turnId")',
        "voiceEvent(\n"
        "    voiceSessionId: string,\n"
        "    frameType: VoiceFrameType,\n"
        "    payload: Record<string, unknown> = {},\n"
        "    turnId?: string,\n"
        "  ): Promise<VoiceSessionResult> {\n"
        '    return this.call("awf/voice.event", { voiceSessionId, frameType, payload, turnId });\n'
        "  }",
    ),
    MethodSpec(
        "awf/voice.sessionClose",
        "awf.ops.voice.op_voice_session_close",
        'conn, voice_session_id=params["voiceSessionId"], reason=params.get("reason")',
        "voiceSessionClose(voiceSessionId: string, reason?: string): Promise<VoiceSessionResult> {\n"
        '    return this.call("awf/voice.sessionClose", { voiceSessionId, reason });\n'
        "  }",
    ),
    MethodSpec(
        "awf/voice.submitText",
        "awf.ops.voice.op_voice_submit_text",
        'repo_root, conn, voice_session_id=params["voiceSessionId"], text=params["text"], workflow_ref=params.get("workflowRef"), voice_profile_ref=params.get("voiceProfileRef"), turn_id=params.get("turnId")',
        "voiceSubmitText(options: {\n"
        "    voiceSessionId: string;\n"
        "    text: string;\n"
        "    workflowRef?: string;\n"
        "    voiceProfileRef?: string;\n"
        "    turnId?: string;\n"
        "  }): Promise<VoiceSubmitTextResult> {\n"
        '    return this.call("awf/voice.submitText", options);\n'
        "  }",
    ),
    MethodSpec(
        "awf/episodic.search",
        "awf.ops.memory.op_episodic_search",
        'conn, query=params["query"], run_id=params.get("runId")',
        "episodicSearch(query: string, runId?: string): Promise<Record<string, unknown>[]> {\n"
        '    return this.call("awf/episodic.search", { query, runId });\n'
        "  }",
        ("memory", "events"),
    ),
    MethodSpec(
        "awf/episodic.timeline",
        "awf.ops.memory.op_episodic_timeline",
        'conn, run_id=params["runId"]',
        "episodicTimeline(runId: string): Promise<Record<string, unknown>> {\n"
        '    return this.call("awf/episodic.timeline", { runId });\n'
        "  }",
        ("memory", "timeline"),
    ),
    MethodSpec(
        "awf/secret.set",
        "awf.ops.system.op_secret_set",
        'repo_root, conn, name=params["name"], value=params["value"]',
        "secretSet(name: string, value: string): Promise<Record<string, unknown>> {\n"
        '    return this.call("awf/secret.set", { name, value });\n'
        "  }",
        ("system", "secret"),
    ),
    MethodSpec(
        "awf/secret.listNames",
        "awf.ops.system.op_secret_list_names",
        "conn",
        'secretListNames(): Promise<string[]> {\n    return this.call("awf/secret.listNames", {});\n  }',
        ("system", "secret"),
    ),
    MethodSpec(
        "awf/control.summary",
        "awf.ops.control.op_control_center_summary",
        "repo_root, conn",
        'controlSummary(): Promise<ControlSummary> {\n    return this.call("awf/control.summary", {});\n  }',
    ),
    MethodSpec(
        "awf/control.runDetail",
        "awf.ops.control.op_control_center_run_detail",
        'repo_root, conn, run_id=params["runId"]',
        "controlRunDetail(runId: string): Promise<ControlRunDetail> {\n"
        '    return this.call("awf/control.runDetail", { runId });\n'
        "  }",
    ),
    MethodSpec(
        "awf/system.readiness",
        "awf.ops.system.op_system_readiness",
        "repo_root",
        'systemReadiness(): Promise<SystemReadiness> {\n    return this.call("awf/system.readiness", {});\n  }',
        ("system", "readiness"),
    ),
    MethodSpec(
        "awf/system.doctor",
        "awf.ops.system.op_system_doctor",
        "repo_root",
        'systemDoctor(): Promise<SystemDoctor> {\n    return this.call("awf/system.doctor", {});\n  }',
        ("doctor",),
    ),
    MethodSpec(
        "awf/llm.servers",
        "awf.ops.llm.op_llm_servers",
        "repo_root",
        'llmServers(): Promise<LlmServersReport> {\n    return this.call("awf/llm.servers", {});\n  }',
        ("system", "llm", "servers"),
    ),
    MethodSpec(
        "awf/llm.models",
        "awf.ops.llm.op_llm_models",
        "repo_root",
        'llmModels(): Promise<LlmModelsReport> {\n    return this.call("awf/llm.models", {});\n  }',
        ("system", "llm", "models"),
    ),
    MethodSpec(
        "awf/llm.serveStatus",
        "awf.ops.llm.op_llm_serve",
        'repo_root, conn, action="status"',
        'llmServeStatus(): Promise<LlmServeStatus> {\n    return this.call("awf/llm.serveStatus", {});\n  }',
        ("system", "llm", "serve"),
    ),
    MethodSpec(
        "awf/events.subscribe",
        "awf.ops.control.op_events_snapshot",
        'conn, run_id=params.get("runId"), limit=int(params.get("limit", 100))',
        "eventsSubscribe(options: { runId?: string; limit?: number } = {}): Promise<EventsSnapshot> {\n"
        '    return this.call("awf/events.subscribe", options);\n'
        "  }",
    ),
)


METHOD_NAMES = tuple(method.name for method in METHODS)
