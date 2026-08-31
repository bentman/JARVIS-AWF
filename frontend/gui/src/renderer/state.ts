const OK = new Set(["SUCCEEDED", "ready", "running", "adopted", "approved", "trusted", "complete", "config"]);
const WARN = new Set(["WAITING_APPROVAL", "WAITING_INPUT", "pending", "draft", "ready_for_review", "review", "degraded", "quarantined", "data"]);
const DANGER = new Set(["FAILED", "CANCELED", "not ready", "denied", "blocked", "rejected", "R3"]);

/** Maps a status string to one of the four semantic state classes (ADR-0025
 * Part C). Every component calls this rather than embedding its own
 * conditional, so run status, readiness, approval risk class, and LLM state
 * all derive their colour the same way. */
export function stateClass(value: string): string {
  if (OK.has(value)) return "state-ok";
  if (WARN.has(value)) return "state-warn";
  if (DANGER.has(value)) return "state-danger";
  return "state-idle";
}
