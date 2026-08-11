import { cleanup } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { afterEach, vi } from "vitest";

vi.stubGlobal(
  "Audio",
  vi.fn().mockImplementation(function AudioMock() {
    return {
    play: vi.fn().mockResolvedValue(undefined),
    };
  }),
);

afterEach(() => {
  cleanup();
});
