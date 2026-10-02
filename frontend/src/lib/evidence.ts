// Evidence card selection on the account page. `null` is a real state: no evidence is highlighted and the
// graph is drawn without dimming.

/** Clicking the selected card clears the selection; clicking any other card selects it. */
export const toggleEvidence = (current: string | null, clicked: string): string | null =>
  current === clicked ? null : clicked;

/** The timeline shows the selected evidence, or the first evidence with transactions when none is selected. */
export function timelineKind<T extends { kind: string; timeline: unknown[] }>(selected: string | null, scored: T[]): string | null {
  if (selected && scored.some((s) => s.kind === selected)) return selected;
  return scored.find((s) => s.timeline.length)?.kind ?? null;
}
