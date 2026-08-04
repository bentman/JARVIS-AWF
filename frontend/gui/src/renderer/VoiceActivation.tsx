import React, { useState } from "react";

export interface VoiceActivationProps {
  onRoundTrip: (wakeAudioPath: string, commandAudioPath: string, voiceId: string) => Promise<void>;
}

// The four Voice Profiles shipped at config/app_registry/voice-profiles/
// (Section 16.5) - the real, registered voice_ids for the Trifecta roles
// and the narrator default. Not fetched from the registry at runtime (that
// would need a new IPC surface); these are the same fixed defaults every
// workflow gets unless an operator publishes an override.
export const VOICE_OPTIONS = [
  { voiceProfile: "narrator", voiceId: "bf_isabella" },
  { voiceProfile: "builder", voiceId: "am_michael" },
  { voiceProfile: "verifier", voiceId: "bf_emma" },
  { voiceProfile: "adversary", voiceId: "bm_george" },
] as const;

/** Push-to-talk-by-file (Section 16.4): the operator supplies a recorded
 * wake-word clip and a recorded command clip. Every recognized utterance
 * and response goes through the same visible Transcript as any other
 * command (the text-first invariant) - voice is an alternate input path,
 * not a separate surface.
 *
 * The voice selector lets the operator actually hear the "two roles, two
 * voices" claim (Section 16.4's acceptance bar) instead of every response
 * always coming back in a single hardcoded voice. */
export function VoiceActivation({ onRoundTrip }: VoiceActivationProps): React.JSX.Element {
  const [wakeAudioPath, setWakeAudioPath] = useState("");
  const [commandAudioPath, setCommandAudioPath] = useState("");
  const [voiceId, setVoiceId] = useState<string>(VOICE_OPTIONS[0].voiceId);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleActivate = async () => {
    setBusy(true);
    setError(null);
    try {
      await onRoundTrip(wakeAudioPath, commandAudioPath, voiceId);
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
      <label>
        Response voice
        <select value={voiceId} onChange={(e) => setVoiceId(e.target.value)}>
          {VOICE_OPTIONS.map((option) => (
            <option key={option.voiceId} value={option.voiceId}>
              {option.voiceProfile} ({option.voiceId})
            </option>
          ))}
        </select>
      </label>
      <button onClick={handleActivate} disabled={busy || !wakeAudioPath || !commandAudioPath}>
        {busy ? "Listening..." : "Activate"}
      </button>
      {error && <p role="alert">{error}</p>}
    </div>
  );
}
