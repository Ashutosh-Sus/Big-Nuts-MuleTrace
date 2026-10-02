// Wording for a row of the cases list. Counts come from the API as they are; nothing is recomputed here.

type Severity = "HIGH" | "MEDIUM" | "LOW";

/** "5 high · 4 low" — the severities of a case's flagged members, zero counts left out. */
export function severityMix(counts: Record<Severity, number>): string {
  return (["HIGH", "MEDIUM", "LOW"] as const).filter((s) => counts[s] > 0)
    .map((s) => `${counts[s]} ${s.toLowerCase()}`).join(" · ");
}

/** Decision progress in the case card's words; decisions on not-flagged members are named separately. */
export function progressText(c: { flagged: number; confirmed_flagged: number; decided_not_flagged: number }): string {
  const base = `${c.confirmed_flagged} of ${c.flagged} flagged confirmed`;
  if (c.decided_not_flagged === 0) return base;
  return `${base} · ${c.decided_not_flagged} decision${c.decided_not_flagged > 1 ? "s" : ""} on not-flagged members`;
}
