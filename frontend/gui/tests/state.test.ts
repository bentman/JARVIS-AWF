import { describe, expect, it } from "vitest";
import { stateClass } from "../src/renderer/state.js";

describe("stateClass", () => {
  it("maps healthy/succeeded states to state-ok", () => {
    for (const value of ["SUCCEEDED", "ready", "running", "adopted", "approved", "trusted"]) {
      expect(stateClass(value)).toBe("state-ok");
    }
  });

  it("maps waiting/degraded states to state-warn", () => {
    for (const value of ["WAITING_APPROVAL", "WAITING_INPUT", "pending", "draft", "degraded", "quarantined"]) {
      expect(stateClass(value)).toBe("state-warn");
    }
  });

  it("maps failed/denied states to state-danger", () => {
    for (const value of ["FAILED", "CANCELED", "not ready", "denied", "blocked", "rejected", "R3"]) {
      expect(stateClass(value)).toBe("state-danger");
    }
  });

  it("falls back to state-idle for idle or unrecognized values", () => {
    for (const value of ["idle", "stopped", "closed", "banana"]) {
      expect(stateClass(value)).toBe("state-idle");
    }
  });
});
