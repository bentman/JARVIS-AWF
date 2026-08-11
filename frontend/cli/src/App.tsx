import type { ProtocolClient } from "@awf/protocol-client";
import { Box, Static, Text, useApp } from "ink";
import TextInput from "ink-text-input";
import React, { useRef, useState } from "react";
import { CommandError, dispatchAssistantInput, dispatchCommand } from "./commands.js";
import type { Settings } from "./settings.js";

interface LogEntry {
  id: number;
  text: string;
}

const COMMAND_NAMES = [
  "help",
  "run",
  "status",
  "runs",
  "resume",
  "approvals",
  "approve",
  "reject",
  "artifacts",
  "agents",
  "skills",
  "workflows",
  "capabilities",
  "mcp",
  "model",
  "voices",
  "secrets",
  "settings",
  "theme",
  "keybindings",
  "clear",
  "quit",
];

export interface AppProps {
  client: ProtocolClient;
  settings: Settings;
}

/** Renders inline in the main terminal buffer (Section 16.2): completed
 * output goes through Ink's <Static> so it's appended permanently to
 * scrollback; only the active input region re-renders. No alternate screen
 * is used - Ink does not enable one unless asked to. */
export function App({ client, settings }: AppProps): React.JSX.Element {
  const { exit } = useApp();
  const [log, setLog] = useState<LogEntry[]>([
    { id: 0, text: "AWF-CLI ready. Type a request, or /help for commands." },
  ]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const nextId = useRef(1);

  const append = (text: string) => {
    setLog((prev) => [...prev, { id: nextId.current++, text }]);
  };

  const firstToken = input.startsWith("/") ? input.slice(1).split(/\s+/)[0] ?? "" : "";
  const suggestions =
    input.startsWith("/") && input.length > 1
      ? COMMAND_NAMES.filter((name) => name.startsWith(firstToken)).slice(0, 6)
      : [];

  const handleSubmit = async (value: string) => {
    const trimmed = value.trim();
    setInput("");
    if (!trimmed) return;
    append(`> ${trimmed}`);

    setBusy(true);
    try {
      const result = trimmed.startsWith("/")
        ? await dispatchCommand(client, trimmed, settings)
        : await dispatchAssistantInput(client, trimmed, settings.defaultWorkflow);
      if (result.kind === "text") {
        append(result.text);
      } else if (result.kind === "json") {
        append(JSON.stringify(result.data, null, 2));
      } else if (result.kind === "clear") {
        setLog([]);
      } else if (result.kind === "quit") {
        client.close();
        exit();
      }
    } catch (err) {
      if (err instanceof CommandError) {
        append(`Error: ${err.message}`);
      } else {
        append(`Error: ${(err as Error).message}`);
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <Box flexDirection="column">
      <Static items={log}>{(entry) => <Text key={entry.id}>{entry.text}</Text>}</Static>
      <Box>
        <Text color="cyan">{"> "}</Text>
        <TextInput value={input} onChange={setInput} onSubmit={handleSubmit} />
      </Box>
      {suggestions.length > 0 && (
        <Box flexDirection="column">
          {suggestions.map((name) => (
            <Text key={name} dimColor>
              /{name}
            </Text>
          ))}
        </Box>
      )}
      {busy && <Text dimColor>working...</Text>}
    </Box>
  );
}
