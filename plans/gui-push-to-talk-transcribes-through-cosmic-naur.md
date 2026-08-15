# Plan: GUI Push-to-Talk Transcribes Through Local STT Adapter

## Context

VoiceActivation.tsx acquires a getUserMedia stream but routes transcription through `window.SpeechRecognition` — a browser web API that the AWF stack does not own or configure. The local STT pipeline (`awf.speech.stt_onnx.transcribe`) is already reachable via a one-shot CLI call, as demonstrated by how `speech/cli.py` handles `round-trip` and `models`. The fix replaces the browser API with a MediaRecorder → temp file → `awf-speech transcribe` chain, so push-to-talk text originates from the same hardware-aware model selection that the rest of the voice stack uses.

## What Changes

### 1. `backend/src/awf/speech/cli.py` — add `transcribe` subcommand

Add a `transcribe` subparser and `_run_transcribe` handler mirroring the readiness resolution already in `_run_models`.

**Subparser registration** (alongside `round-trip`, `synthesize`, `models`):
```python
p_transcribe = subparsers.add_parser("transcribe")
p_transcribe.add_argument("audio_path", type=Path)
p_transcribe.set_defaults(func=_run_transcribe)
```

**Handler** — import the same hardware readiness chain used by `_run_models` (locally inside the function to avoid import-time cost), resolve the STT runtime, call `transcribe`, emit JSON:
```python
def _run_transcribe(args: argparse.Namespace, repo_root: Path) -> int:
    from awf.hardware.preflight import collect_preflight_tokens
    from awf.hardware.profiler import collect_inventory
    from awf.hardware.readiness import derive_stt_readiness
    from awf.speech import stt_onnx

    inventory = collect_inventory()
    tokens = collect_preflight_tokens(inventory)
    readiness = derive_stt_readiness(inventory, tokens)
    result = stt_onnx.transcribe(
        args.audio_path,
        repo_root=repo_root,
        runtime=readiness.runtime,  # or .device — see Note below
    )
    print(json.dumps({"text": result["text"], "language": result["language"]}))
    return 0
```

> **Note on runtime resolution:** `derive_stt_readiness` returns a readiness object. Inspect whether it exposes `.runtime` (an `SttRuntime`) or only `.device` (a string). If only `.device`, use the same `stt_runtime(repo_root, device)` factory that `stt_onnx.py` calls internally for the cpu fallback path. Check `awf/hardware/readiness.py` and `awf/speech/stt_onnx.py` imports at implementation time.

### 2. `frontend/gui/src/main/voicePipeline.ts` — add `runVoiceTranscribe` and IPC handler

**New channel constant** — extend `VOICE_SESSION_CHANNELS`:
```typescript
transcribe: "awf:voiceTranscribe",
```

**New types:**
```typescript
interface RunVoiceTranscribeOptions {
  command?: string;
  cwd: string;
  audioData: Uint8Array;   // raw audio bytes from renderer
}
interface VoiceTranscribeResult {
  text: string;
  language: string;
}
```

**`runVoiceTranscribe` function** — write audio to a temp file, spawn `awf-speech transcribe`, parse result:
```typescript
export async function runVoiceTranscribe(
  options: RunVoiceTranscribeOptions,
): Promise<VoiceTranscribeResult> {
  const tmpPath = join(tmpdir(), `awf-transcribe-${Date.now()}.wav`);
  await writeFile(tmpPath, options.audioData);
  try {
    // spawn awf-speech transcribe <tmpPath>
    // parse last JSON line → {text, language}
    // follow same spawn/stdout/stderr/close pattern as runVoiceSpeakText
  } finally {
    await unlink(tmpPath).catch(() => {});
  }
}
```

**IPC handler** — register alongside existing handlers:
```typescript
export function registerVoiceTranscribeIpcHandler(ipcMain: IpcMain, options: ...) {
  ipcMain.handle(VOICE_SESSION_CHANNELS.transcribe, async (_, audioData: ArrayBuffer) => {
    return runVoiceTranscribe({ ...options, audioData: new Uint8Array(audioData) });
  });
}
```

Call `registerVoiceTranscribeIpcHandler` from wherever `registerVoiceSpeakIpcHandler` is currently registered (search for its call site in `main/index.ts` or equivalent).

### 3. `frontend/gui/src/renderer/VoiceActivation.tsx` — replace SpeechRecognition with MediaRecorder

**State changes:**
- Remove `recognitionRef` (`useRef<SpeechRecognition | null>(null)`)
- Add `mediaRecorderRef` (`useRef<MediaRecorder | null>(null)`)
- Add `audioChunksRef` (`useRef<Blob[]>([])`)
- `partialText` state stays (it is rendered in the UI); it simply will never be set on this path

**`startPushToTalk` changes** (replace lines ~146–165):
```typescript
// Remove: SpeechRecognition init and recognition.start()
// Add:
audioChunksRef.current = [];
const recorder = new MediaRecorder(streamRef.current, {
  mimeType: MediaRecorder.isTypeSupported("audio/wav") ? "audio/wav" : "audio/webm",
});
recorder.ondataavailable = (e) => { if (e.data.size > 0) audioChunksRef.current.push(e.data); };
mediaRecorderRef.current = recorder;
recorder.start();
```

**`stopPushToTalk` changes** (replace lines ~176–185):
```typescript
// Remove: recognitionRef.current?.stop(); recognition cleanup
// Add: stop recorder, collect blob, send to main, set recognizedText
const recorder = mediaRecorderRef.current;
if (!recorder) return;

await new Promise<void>((resolve) => {
  recorder.onstop = async () => {
    const blob = new Blob(audioChunksRef.current, { type: recorder.mimeType });
    const arrayBuffer = await blob.arrayBuffer();
    const result = await window.electronAPI.transcribeAudio(arrayBuffer);
    setRecognizedText(result.text);
    resolve();
  };
  recorder.stop();
});
mediaRecorderRef.current = null;
streamRef.current?.getTracks().forEach((track) => track.stop());
streamRef.current = null;
updateFrom(await onPushToTalkStop(voiceSessionId, turnId));
```

**`interrupt` changes:** mirror the cleanup — stop the MediaRecorder (no await needed), clear refs, stop tracks.

**Remove entirely:** all `window.SpeechRecognition ?? window.webkitSpeechRecognition` references and the `Recognition` guard block.

**Preload/contextBridge:** add `transcribeAudio` to whichever preload script exposes `electronAPI`. It should invoke `ipcRenderer.invoke(VOICE_SESSION_CHANNELS.transcribe, audioData)`.

## Files Modified

| File | Change |
|------|--------|
| `backend/src/awf/speech/cli.py` | Add `transcribe` subparser + `_run_transcribe` handler |
| `frontend/gui/src/main/voicePipeline.ts` | Add channel constant, types, `runVoiceTranscribe`, IPC handler |
| `frontend/gui/src/renderer/VoiceActivation.tsx` | Replace SpeechRecognition with MediaRecorder; wire transcribe IPC |
| `frontend/gui/src/main/preload.ts` (or equivalent) | Expose `transcribeAudio` on `electronAPI` |
| `frontend/gui/tests/voicePipeline.test.ts` | Add tests for `runVoiceTranscribe` |
| `backend/tests/` (speech CLI tests) | Add test for `awf-speech transcribe` handler |

## Verification

1. **Backend unit test:** call `_run_transcribe` with a fixture WAV, assert JSON output contains non-empty `text` and `language`. Mark `@pytest.mark.live` if it loads the actual model.
2. **Frontend unit test:** mock `spawn` (same pattern as existing tests), assert `runVoiceTranscribe` spawns `awf-speech transcribe <tmppath>` and returns parsed `{text, language}`.
3. **End-to-end:** launch the Electron app, press push-to-talk, speak a short phrase, release — the transcript field should populate from the local STT model. Confirm no `SpeechRecognition` reference remains (`grep -r SpeechRecognition frontend/gui/src`).
