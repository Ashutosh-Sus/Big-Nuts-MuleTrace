// In-app links for free-text identifiers. Account IDs can contain "/", "?", "#", "%" or spaces; every link
// encodes them so the router receives the ID exactly as it is.

export const accountPath = (id: string, view?: "back" | "fwd"): string =>
  `/account/${encodeURIComponent(id)}${view ? `?view=${view}` : ""}`;

export const casePath = (id: string): string => `/case/${encodeURIComponent(id)}`;

export const queuePath = (params: Record<string, string>): string => {
  const qs = new URLSearchParams(params).toString();
  return qs ? `/queue?${qs}` : "/queue";
};
