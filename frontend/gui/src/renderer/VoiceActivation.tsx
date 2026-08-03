import React, { useState } from "react";

export interface VoiceActivationProps {
  onRoundTrip: (wakeAudioPath: string, commandAudioPath: string) => Promise<void>;
}

/** Push-to-talk-by-file (Section 16.4): the operator supplies a recorded
 * wake-word clip and a recorded command clip. Every recognized utterance
 * and response goes through the same visible Transcript as any other
 * command (the text-first invariant) - voice is an alternate input path,
 * not a separate surface. */
export function VoiceActivation({ onRoundTrip }: VoiceActivationProps): React.JSX.Element {
  const [wakeAudioPath, setWakeAudioPath] = useState("");
  const [commandAudioPath, setCommandAudioPath] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleActivate = async () => {
    setBusy(true);
    setError(null);
    try {
      await onRoundTrip(wakeAudioPath, commandAudioPath);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div role="group" aria-label="Voice activation">
      <label>
        Wake-word audio file
        <input
          type="text"
          value={wakeAudioPath}
          onChange={(e) => setWakeAudioPath(e.target.value)}
          placeholder="/path/to/hey_jarvis.wav"
        />
      </label>
      <label>
        Command audio file
        <input
          type="text"
          value={commandAudioPath}
          onChange={(e) => setCommandAudioPath(e.target.value)}
          placeholder="/path/to/command.wav"
        />
      </label>
      <button onClick={handleActivate} disabled={busy || !wakeAudioPath || !commandAudioPath}>
        {busy ? "Listening..." : "Activate"}
      </button>
      {error && <p role="alert">{error}</p>}
    </div>
  );
}
