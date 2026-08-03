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
    <div role="log" aria-label="Transcript">
      {entries.map((entry) => (
        <p key={entry.id}>
          <strong>{entry.speaker}:</strong> {entry.text}
        </p>
      ))}
    </div>
  );
}
