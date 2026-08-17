import { describe, expect, it } from "vitest";
import { encodeWav16, STT_SAMPLE_RATE } from "../src/renderer/wav.js";

function ascii(view: DataView, offset: number, length: number): string {
  let out = "";
  for (let index = 0; index < length; index += 1) {
    out += String.fromCharCode(view.getUint8(offset + index));
  }
  return out;
}

describe("encodeWav16", () => {
  it("writes the mono 16-bit PCM header awf.speech.stt_onnx requires", () => {
    const buffer = encodeWav16(new Float32Array(8), STT_SAMPLE_RATE);
    const view = new DataView(buffer);

    expect(ascii(view, 0, 4)).toBe("RIFF");
    expect(ascii(view, 8, 4)).toBe("WAVE");
    expect(ascii(view, 12, 4)).toBe("fmt ");
    expect(view.getUint32(16, true)).toBe(16);
    expect(view.getUint16(20, true)).toBe(1); // PCM
    expect(view.getUint16(22, true)).toBe(1); // mono
    expect(view.getUint32(24, true)).toBe(STT_SAMPLE_RATE);
    expect(view.getUint32(28, true)).toBe(STT_SAMPLE_RATE * 2);
    expect(view.getUint16(32, true)).toBe(2);
    expect(view.getUint16(34, true)).toBe(16); // sampwidth 2 bytes
    expect(ascii(view, 36, 4)).toBe("data");
  });

  it("sizes the RIFF and data chunks from the sample count", () => {
    const buffer = encodeWav16(new Float32Array(10), STT_SAMPLE_RATE);
    const view = new DataView(buffer);

    expect(buffer.byteLength).toBe(44 + 20);
    expect(view.getUint32(4, true)).toBe(36 + 20);
    expect(view.getUint32(40, true)).toBe(20);
  });

  it("converts floats to signed 16-bit samples and clamps out-of-range input", () => {
    const buffer = encodeWav16(new Float32Array([0, 1, -1, 2, -2, 0.5]), STT_SAMPLE_RATE);
    const view = new DataView(buffer);

    expect(view.getInt16(44, true)).toBe(0);
    expect(view.getInt16(46, true)).toBe(32767);
    expect(view.getInt16(48, true)).toBe(-32768);
    expect(view.getInt16(50, true)).toBe(32767);
    expect(view.getInt16(52, true)).toBe(-32768);
    expect(view.getInt16(54, true)).toBe(16384);
  });

  it("carries the sample rate it was given", () => {
    const view = new DataView(encodeWav16(new Float32Array(2), 48000));
    expect(view.getUint32(24, true)).toBe(48000);
    expect(view.getUint32(28, true)).toBe(96000);
  });
});
