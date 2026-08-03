/** Voice approval rule (Section 16.4): an approval decision for an R2+
 * action MUST NOT be granted from voice input alone - the GUI MUST display
 * the exact action digest and require a non-voice (click/keypress)
 * confirmation. Voice MAY acknowledge R0/R1 prompts.
 *
 * Mirrors `awf.gates.voice_approval.decide_voice_acknowledgement` on the
 * Python side (defense in depth: the core also never grants an R2+
 * approval from a voice-only signal), enforced here at the point the GUI
 * would otherwise be tempted to call `approvalApprove` directly from a
 * recognized voice utterance.
 */

export type RiskClass = "R0" | "R1" | "R2" | "R3";

const HIGH_RISK_CLASSES: RiskClass[] = ["R2", "R3"];

export interface VoiceAcknowledgementDecision {
  decided: boolean;
  requiresOnScreenConfirmation: boolean;
  channel: "voice";
}

export function decideVoiceAcknowledgement(
  riskClass: RiskClass,
  voiceConfirmed: boolean,
): VoiceAcknowledgementDecision {
  if (HIGH_RISK_CLASSES.includes(riskClass)) {
    return { decided: false, requiresOnScreenConfirmation: true, channel: "voice" };
  }
  return { decided: voiceConfirmed, requiresOnScreenConfirmation: false, channel: "voice" };
}
