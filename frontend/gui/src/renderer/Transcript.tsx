import React from "react";

export interface TranscriptEntry {
  id: number;
  speaker: string;
  text: string;
}

/** Text-first invariant (Section 16.4): every recognized utterance is
 * displayed as text before submission, and every spoken response has a
 * visible transcript. There are no voice-only capabilities. */
export function Transcript({ entries }: { entries: TranscriptEntry[] }): React.JSX.Element {
  return (
    <div role="log" aria-label="Transcript" className="card">
      {entries.map((entry) => (
        <p key={entry.id} className="transcript-row">
          <strong className="transcript-speaker">{entry.speaker}:</strong>{" "}
          <span className="transcript-body">{entry.text}</span>
        </p>
      ))}
    </div>
  );
}
