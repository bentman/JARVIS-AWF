#!/usr/bin/env node
import { ChildProcessTransport, ProtocolClient } from "@awf/protocol-client";
import { render } from "ink";
import React from "react";
import { App } from "./App.js";
import { resolveBackendCommand } from "./backendCommand.js";
import { loadSettings } from "./settings.js";

function main(): void {
  const repoRoot = process.env.AWF_REPO_ROOT ?? process.cwd();
  const settings = loadSettings(repoRoot);
  const transport = new ChildProcessTransport({
    command: process.env.AWF_CORE_COMMAND ?? resolveBackendCommand(repoRoot, "awf"),
    cwd: repoRoot,
  });
  const client = new ProtocolClient(transport);

  render(React.createElement(App, { client, settings }));
}

main();
