import React, { useEffect, useRef, useState } from "react";
import { MicIcon, SendIcon } from "./icons.js";

export interface TranscriptEntry {
  id: number;
  speaker: string;
  text: string;
}

export interface TranscriptProps {
  entries: TranscriptEntry[];
  workflowRef?: string;
  workflowOptions?: string[];
  onWorkflowRefChange?: (workflowRef: string) => void;
  submitError?: string | null;
  submitting?: boolean;
  /** Submits typed text to the same governed backend work path as voice. */
  onSend?: (text: string) => boolean | void | Promise<boolean | void>;
  /** Drives the existing push-to-talk flow (mic button in the composer). */
  onMic?: () => void;
  /** Navigates to Operate and inspects the specified run. */
  onRunSelect?: (runId: string) => void;
}

/** Text-first invariant (Section 16.4): every recognized utterance is
 * displayed as text before submission, and every spoken response has a
 * visible transcript. There are no voice-only capabilities.
 *
 * Rendered as a chat-messenger window-panel (ADR-0025): a title bar, an
 * auto-scrolling bubble stream (operator right, agent left, letter avatars),
 * and a composer bar with a mic (voice) button and a Send button. */
export function Transcript({
  entries,
  workflowRef = "",
  workflowOptions = [],
  onWorkflowRefChange,
  submitError,
  submitting = false,
  onSend,
  onMic,
  onRunSelect,
}: TranscriptProps): React.JSX.Element {
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const [draft, setDraft] = useState("");
  const [copiedId, setCopiedId] = useState<number | null>(null);

  // Follow the newest entry so the operator always sees the live tail.
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [entries]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const text = draft.trim();
    if (!text || submitting) return;
    const sent = await onSend?.(text);
    if (sent === false) return;
    setDraft("");
  };

  const copyTimerRef = React.useRef<number | null>(null);

  const copyText = (id: number, text: string) => {
    if (typeof navigator !== "undefined" && navigator.clipboard) {
      void navigator.clipboard.writeText(text);
      setCopiedId(id);
      if (copyTimerRef.current !== null) {
        window.clearTimeout(copyTimerRef.current);
      }
      copyTimerRef.current = window.setTimeout(() => {
        setCopiedId((curr) => (curr === id ? null : curr));
      }, 1500);
    }
  };

  return (
    <section aria-label="Chat" className="chat-window">
      <h2 className="chat-title">
        <span className="chat-dot" aria-hidden="true" />
        Chat
      </h2>
      <div ref={scrollRef} role="log" aria-label="Chat log" className="chat-scroll">
        {entries.length === 0 ? (
          <div>
            <p className="empty chat-empty">No conversation yet — type a message or use voice to start.</p>
            <div className="starter-prompts" aria-label="Suggested starter prompts">
              <span className="starter-prompts-title">Suggested prompts</span>
              <button
                type="button"
                className="starter-chip"
                onClick={() => setDraft("Check system readiness and report profile status.")}
              >
                Check system readiness
              </button>
              <button
                type="button"
                className="starter-chip"
                onClick={() => setDraft("List active workflows in the registry.")}
              >
                List active workflows
              </button>
              <button
                type="button"
                className="starter-chip"
                onClick={() => setDraft("Summarize recent workflow runs and verdicts.")}
              >
                Summarize recent runs
              </button>
            </div>
          </div>
        ) : (
          entries.map((entry) => {
            const isUser = /^operator/i.test(entry.speaker);
            const runMatch = onRunSelect ? entry.text.match(/\b(run-[a-zA-Z0-9_\-]+)\b/) : null;
            const runId = runMatch ? runMatch[1] : null;
            return (
              <div key={entry.id} className={`bubble ${isUser ? "bubble-user" : "bubble-agent"}`}>
                <span className="avatar" aria-hidden="true">
                  {isUser ? "U" : "A"}
                </span>
                <span className="bubble-body">
                  <strong className="bubble-speaker">{entry.speaker}:</strong>
                  <span className="bubble-text">{entry.text}</span>
                  <div className="bubble-actions">
                    {runId && (
                      <button
                        type="button"
                        className="run-link-chip"
                        onClick={() => onRunSelect?.(runId)}
                        title={`Jump to run ${runId} in Operate`}
                        aria-label={`Inspect run ${runId}`}
                      >
                        Inspect run {runId}
                      </button>
                    )}
                    <button
                      type="button"
                      className="btn-copy-bubble"
                      onClick={() => copyText(entry.id, entry.text)}
                      title="Copy message text to clipboard"
                      aria-label={`Copy message from ${entry.speaker}`}
                    >
                      {copiedId === entry.id ? "Copied" : "Copy"}
                    </button>
                  </div>
                </span>
              </div>
            );
          })
        )}
      </div>
      <form className="composer" onSubmit={submit}>
        <button
          type="button"
          className="btn-mic"
          onClick={() => onMic?.()}
          disabled={!onMic}
          aria-label="Push to talk"
        >
          <MicIcon size={15} />
        </button>
        <input
          className="workflow-input mono"
          value={workflowRef}
          onChange={(e) => onWorkflowRefChange?.(e.target.value)}
          placeholder="workflow@1.0.0"
          aria-label="Workflow"
          list={workflowOptions.length > 0 ? "chat-workflow-options" : undefined}
        />
        {workflowOptions.length > 0 && (
          <datalist id="chat-workflow-options">
            {workflowOptions.map((option) => (
              <option key={option} value={option} />
            ))}
          </datalist>
        )}
        <textarea
          className="composer-input"
          value={draft}
          rows={1}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void submit(e);
            }
          }}
          placeholder="Message AWF (e.g. 'check readiness', 'run workflow')..."
          aria-label="Message"
        />
        <button type="submit" className="btn-send" disabled={!draft.trim() || submitting} aria-label="Send">
          <span>{submitting ? "Sending" : "Send"}</span>
          <SendIcon size={15} />
        </button>
      </form>
      <div className="composer-hints">
        <span><span className="kbd-hint">Enter</span> send &bull; <span className="kbd-hint">Shift+Enter</span> newline &bull; <span className="kbd-hint">Ctrl+K</span> focus</span>
        <span>Voice dispatches via intent routing</span>
      </div>
      {submitError && (
        <div role="alert" className="chip state-danger" style={{ margin: "var(--space-2) var(--space-3)" }}>
          {submitError}
        </div>
      )}
    </section>
  );
}
