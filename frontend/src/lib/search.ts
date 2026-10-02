// Header account search. Results are tagged with the query they answer, so a result list that belongs to
// an earlier query can never decide where Enter goes.

export interface SearchHit { id: string }
export interface SearchResults<T extends SearchHit = SearchHit> { query: string; items: T[] }

export const normalise = (q: string): string => q.trim();

/** The account Enter should open for `items` answering `query`: an exact ID match (any case), else the first. */
export function bestMatch<T extends SearchHit>(query: string, items: T[]): T | null {
  const q = normalise(query).toLowerCase();
  if (!q || !items.length) return null;
  return items.find((i) => i.id.toLowerCase() === q) ?? items[0];
}

/** Only results that answer the current query count; anything else is stale. */
export function currentItems<T extends SearchHit>(query: string, results: SearchResults<T> | null): T[] | null {
  if (!results || results.query !== normalise(query)) return null;
  return results.items;
}

export type EnterAction = { kind: "open"; id: string } | { kind: "search" } | { kind: "none" };

/** What pressing Enter does: open the best match of the current results, or search now when the shown
 *  results are stale or not there yet (the caller searches and then applies `bestMatch`). */
export function enterAction(query: string, results: SearchResults | null): EnterAction {
  if (!normalise(query)) return { kind: "none" };
  const items = currentItems(query, results);
  if (items == null) return { kind: "search" };
  const hit = bestMatch(query, items);
  return hit ? { kind: "open", id: hit.id } : { kind: "none" };
}
