/** WAV encoding for transcription input.
 *
 * `awf.speech.stt_onnx._read_wav_float32` opens transcription input with
 * Python's `wave` module and rejects anything that is not mono 16-bit PCM,
 * and Whisper expects 16 kHz. Chromium's `MediaRecorder` cannot produce
 * that - `MediaRecorder.isTypeSupported("audio/wav")` is false there, so a
 * recording is WebM/Opus regardless of the filename it is written to. The
 * renderer therefore decodes its own recording and re-encodes the exact
 * format the STT adapters already require, rather than pushing container
 * handling into the Python side.
 */

export const STT_SAMPLE_RATE = 16000;

/** Mono float samples (-1.0..1.0) to a 16-bit PCM WAV byte buffer. */
export function encodeWav16(samples: Float32Array, sampleRate: number): ArrayBuffer {
  const dataBytes = samples.length * 2;
  const buffer = new ArrayBuffer(44 + dataBytes);
  const view = new DataView(buffer);

  const writeAscii = (offset: number, text: string) => {
    for (let index = 0; index < text.length; index += 1) {
      view.setUint8(offset + index, text.charCodeAt(index));
    }
  };

  writeAscii(0, "RIFF");
  view.setUint32(4, 36 + dataBytes, true);
  writeAscii(8, "WAVE");
  writeAscii(12, "fmt ");
  view.setUint32(16, 16, true); // PCM fmt chunk size
  view.setUint16(20, 1, true); // PCM
  view.setUint16(22, 1, true); // mono
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true); // byte rate: rate * channels * bytes per sample
  view.setUint16(32, 2, true); // block align
  view.setUint16(34, 16, true); // bits per sample
  writeAscii(36, "data");
  view.setUint32(40, dataBytes, true);

  let offset = 44;
  for (let index = 0; index < samples.length; index += 1) {
    const clamped = Math.max(-1, Math.min(1, samples[index]));
    view.setInt16(offset, Math.round(clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff), true);
    offset += 2;
  }
  return buffer;
}

/** Decode a recorded blob and re-encode it as 16 kHz mono 16-bit PCM WAV.
 *
 * `decodeAudioData` resamples to the `AudioContext`'s own rate, so the
 * context is constructed at the STT rate rather than resampling by hand. */
export async function blobToWav16(blob: Blob, sampleRate: number = STT_SAMPLE_RATE): Promise<ArrayBuffer> {
  const encoded = await blob.arrayBuffer();
  const AudioContextCtor =
    window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  if (!AudioContextCtor) {
    throw new Error("AudioContext is unavailable; cannot encode recorded audio for transcription");
  }
  const context = new AudioContextCtor({ sampleRate });
  try {
    const decoded = await context.decodeAudioData(encoded);
    return encodeWav16(decoded.getChannelData(0), decoded.sampleRate);
  } finally {
    void context.close();
  }
}
