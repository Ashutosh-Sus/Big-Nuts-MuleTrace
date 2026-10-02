// Post-processing of the layered (left-to-right) graph layout.

export interface Pos { id: string; x: number; y: number }

/** A layered layout puts every account of one step into a single column, so a fan-out of 25 becomes one tall
 *  line that has to be shrunk to fit. Columns with more than `maxPerColumn` accounts are wrapped into a small
 *  grid (row by row, keeping their top-to-bottom order) and later columns move right to make room. Columns
 *  keep their left-to-right order, so the direction money moves in stays readable. */
export function wrapColumns(pos: Pos[], maxPerColumn: number, colGap: number, rowGap: number): Pos[] {
  if (!pos.length) return pos;
  const cols = new Map<number, Pos[]>();
  for (const p of pos) {
    const key = Math.round(p.x);
    const list = cols.get(key);
    if (list) list.push(p); else cols.set(key, [p]);
  }
  const xs = [...cols.keys()].sort((a, b) => a - b);
  const out = new Map<string, Pos>();
  let shift = 0;
  for (const x of xs) {
    const list = [...cols.get(x)!].sort((a, b) => a.y - b.y || a.id.localeCompare(b.id));
    if (list.length <= maxPerColumn) {
      for (const p of list) out.set(p.id, { ...p, x: p.x + shift });
      continue;
    }
    const k = Math.ceil(list.length / maxPerColumn);
    const rows = Math.ceil(list.length / k);
    const midY = (list[0].y + list[list.length - 1].y) / 2;
    list.forEach((p, i) => {
      const r = Math.floor(i / k), c = i % k;
      out.set(p.id, { id: p.id, x: x + shift + c * colGap, y: midY + (r - (rows - 1) / 2) * rowGap });
    });
    shift += (k - 1) * colGap;
  }
  return pos.map((p) => out.get(p.id)!);
}
