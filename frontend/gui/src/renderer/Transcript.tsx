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
}: TranscriptProps): React.JSX.Element {
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const [draft, setDraft] = useState("");

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

  return (
    <section aria-label="Chat" className="chat-window">
      <h2 className="chat-title">
        <span className="chat-dot" aria-hidden="true" />
        Chat
      </h2>
      <div ref={scrollRef} role="log" aria-label="Chat log" className="chat-scroll">
        {entries.length === 0 ? (
          <p className="empty chat-empty">No conversation yet — type a message or use voice to start.</p>
        ) : (
          entries.map((entry) => {
            const isUser = /^operator/i.test(entry.speaker);
            return (
              <div key={entry.id} className={`bubble ${isUser ? "bubble-user" : "bubble-agent"}`}>
                <span className="avatar" aria-hidden="true">
                  {isUser ? "U" : "A"}
                </span>
                <span className="bubble-body">
                  <strong className="bubble-speaker">{entry.speaker}:</strong>
                  <span className="bubble-text">{entry.text}</span>
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
        <input
          className="composer-input"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Message AWF..."
          aria-label="Message"
        />
        <button type="submit" className="btn-send" disabled={!draft.trim() || submitting} aria-label="Send">
          <span>{submitting ? "Sending" : "Send"}</span>
          <SendIcon size={15} />
        </button>
      </form>
      {submitError && <div role="alert">{submitError}</div>}
    </section>
  );
}
