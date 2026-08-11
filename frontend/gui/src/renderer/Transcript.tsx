import React, { useEffect, useRef, useState } from "react";

export interface TranscriptEntry {
  id: number;
  speaker: string;
  text: string;
}

export interface TranscriptProps {
  entries: TranscriptEntry[];
  /** Appends the operator's typed text to the conversation (local, text-first). */
  onSend?: (text: string) => void;
  /** Drives the existing push-to-talk flow (mic button in the composer). */
  onMic?: () => void;
}

function MicIcon(): React.JSX.Element {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
      <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
      <line x1="12" y1="19" x2="12" y2="23" />
      <line x1="8" y1="23" x2="16" y2="23" />
    </svg>
  );
}

function SendIcon(): React.JSX.Element {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <line x1="22" y1="2" x2="11" y2="13" />
      <polygon points="22 2 15 22 11 13 2 9 22 2" />
    </svg>
  );
}

/** Text-first invariant (Section 16.4): every recognized utterance is
 * displayed as text before submission, and every spoken response has a
 * visible transcript. There are no voice-only capabilities.
 *
 * Rendered as a chat-messenger window-panel (ADR-0025): a title bar, an
 * auto-scrolling bubble stream (operator right, agent left, letter avatars),
 * and a composer bar with a mic (voice) button and a Send button. */
export function Transcript({ entries, onSend, onMic }: TranscriptProps): React.JSX.Element {
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const [draft, setDraft] = useState("");

  // Follow the newest entry so the operator always sees the live tail.
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [entries]);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const text = draft.trim();
    if (!text) return;
    onSend?.(text);
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
          <MicIcon />
        </button>
        <input
          className="composer-input"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Message AWF..."
          aria-label="Message"
        />
        <button type="submit" className="btn-send" disabled={!draft.trim()} aria-label="Send">
          <span>Send</span>
          <SendIcon />
        </button>
      </form>
    </section>
  );
}
