import { describe, expect, it } from "vitest";
import { decideVoiceAcknowledgement } from "../src/voiceApproval.js";

describe("decideVoiceAcknowledgement", () => {
  it.each(["R2", "R3"] as const)("%s is never decided by voice, even when confirmed", (riskClass) => {
    const decision = decideVoiceAcknowledgement(riskClass, true);
    expect(decision.decided).toBe(false);
    expect(decision.requiresOnScreenConfirmation).toBe(true);
  });

  it.each(["R0", "R1"] as const)("%s may be acknowledged by voice when confirmed", (riskClass) => {
    const decision = decideVoiceAcknowledgement(riskClass, true);
    expect(decision.decided).toBe(true);
    expect(decision.requiresOnScreenConfirmation).toBe(false);
  });

  it("R0/R1 are not decided without voice confirmation", () => {
    const decision = decideVoiceAcknowledgement("R0", false);
    expect(decision.decided).toBe(false);
  });
});
