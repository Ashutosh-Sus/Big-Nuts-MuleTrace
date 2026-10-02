// Analyst decision panel logic: which reason shortcuts fit which action, and a submit that never loses input.

export type DecisionStatus = "OPEN" | "CONFIRMED" | "CLEARED";

export const CONFIRM_REASONS = ["Rapid layering confirmed", "Linked to confirmed case", "Customer unable to explain flows"];
export const CLEAR_REASONS = ["Known business activity", "Customer verified", "Possible victim — referred to support"];

/** Reason shortcuts per available action: an account can be confirmed unless it already is, cleared unless it
 *  already is. Each list belongs to its own button, so a "clear" reason is never offered for a confirmation. */
export function reasonsFor(status: DecisionStatus): { confirm: string[]; clear: string[] } {
  return {
    confirm: status === "CONFIRMED" ? [] : CONFIRM_REASONS,
    clear: status === "CLEARED" ? [] : CLEAR_REASONS,
  };
}

export type SubmitResult = { ok: true } | { ok: false; error: string };

/** Runs the request and reports the outcome instead of throwing, so the caller keeps the note on failure. */
export async function submitDecision(send: () => Promise<unknown>): Promise<SubmitResult> {
  try {
    await send();
    return { ok: true };
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    return { ok: false, error: msg || "The server did not accept the decision." };
  }
}
