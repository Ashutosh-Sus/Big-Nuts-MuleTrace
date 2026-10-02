// Graph data handling on the account page.
import type { GraphData } from "../api";

export type GraphMode = "network" | "back" | "fwd";

/** Double-click meaning per view. In the network it adds the account's neighbourhood to the drawing. A traced
 *  flow's amounts belong to one start account, so a trace is never merged with another: double-click opens
 *  the clicked account's own trace instead. */
export const expandAction = (mode: GraphMode): "merge" | "open-trace" => (mode === "network" ? "merge" : "open-trace");

/** Adds a 1-hop neighbourhood to a network drawing. Only network graphs merge; anything else is returned
 *  unchanged (traced amounts and their exact accounting must not be mixed). */
export function mergeNetwork(a: GraphData, b: GraphData): GraphData {
  if (a.mode !== "network" || b.mode !== "network") return a;
  const nodes = new Map(a.nodes.map((n) => [n.id, n]));
  for (const n of b.nodes) if (!nodes.has(n.id)) nodes.set(n.id, { ...n, focus: false });
  const edges = new Map(a.edges.map((e) => [e.id, e]));
  for (const e of b.edges) if (!edges.has(e.id)) edges.set(e.id, e);
  const ids = new Map((a.identity_edges ?? []).map((e) => [`${e.source}|${e.target}|${e.attr}`, e]));
  for (const e of b.identity_edges ?? []) ids.set(`${e.source}|${e.target}|${e.attr}`, e);
  return { ...a, nodes: [...nodes.values()], edges: [...edges.values()], identity_edges: [...ids.values()] };
}

/** A decision changes one account's status; the drawing (including expanded neighbourhoods) stays as it is. */
export function withStatus(g: GraphData, account: string, status: string): GraphData {
  if (!g.nodes.some((n) => n.id === account)) return g;
  return { ...g, nodes: g.nodes.map((n) => (n.id === account ? { ...n, status } : n)) };
}
