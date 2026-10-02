// Display formatting. Amounts arrive in minor units (paise / cents) as integers.
let currency = "INR";
let symbol = "₹";
const OFFSET_MIN = 330; // display timezone: IST (matches the analysis configuration)

export function setCurrency(code: string | null, sym: string | null) {
  if (code) currency = code;
  if (sym) symbol = sym;
}

function groupIndian(n: number): string {
  const s = String(Math.abs(Math.trunc(n)));
  if (s.length <= 3) return s;
  const tail = s.slice(-3);
  let head = s.slice(0, -3);
  const parts: string[] = [];
  while (head.length > 2) { parts.unshift(head.slice(-2)); head = head.slice(0, -2); }
  if (head) parts.unshift(head);
  return parts.join(",") + "," + tail;
}

export function money(minor: number | null | undefined): string {
  if (minor == null) return "—";
  const major = Math.round(minor / 100);
  const sign = major < 0 ? "-" : "";
  if (currency === "INR") return `${sign}${symbol}${groupIndian(major)}`;
  return `${sign}${symbol}${Math.abs(major).toLocaleString("en-US")}`;
}

export function moneyShort(minor: number | null | undefined): string {
  if (minor == null) return "—";
  const v = minor / 100;
  if (currency === "INR") {
    if (v >= 1e7) return `${symbol}${(v / 1e7).toFixed(2).replace(/\.?0+$/, "")}Cr`;
    if (v >= 1e5) return `${symbol}${(v / 1e5).toFixed(2).replace(/\.?0+$/, "")}L`;
    if (v >= 1e3) return `${symbol}${(v / 1e3).toFixed(1).replace(/\.0$/, "")}k`;
    return `${symbol}${Math.round(v)}`;
  }
  if (v >= 1e6) return `${symbol}${(v / 1e6).toFixed(2).replace(/\.?0+$/, "")}M`;
  if (v >= 1e3) return `${symbol}${(v / 1e3).toFixed(1).replace(/\.0$/, "")}k`;
  return `${symbol}${Math.round(v)}`;
}

function local(ts: number): Date {
  return new Date((ts + OFFSET_MIN * 60) * 1000);
}
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const pad = (n: number) => String(n).padStart(2, "0");

export function clock(ts: number | null | undefined): string {
  if (ts == null) return "—";
  const d = local(ts);
  return `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}`;
}
export function dateTime(ts: number | null | undefined): string {
  if (ts == null) return "—";
  const d = local(ts);
  return `${pad(d.getUTCDate())} ${MONTHS[d.getUTCMonth()]} ${clock(ts)}`;
}
export function date(ts: number | null | undefined): string {
  if (ts == null) return "—";
  const d = local(ts);
  return `${pad(d.getUTCDate())} ${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
}
/** When an analyst recorded something: same IST style as every other time in the console, with the year. */
export function auditTime(epochSeconds: number): string {
  return `${date(epochSeconds)} ${clock(epochSeconds)} IST`;
}

/** A time window: "25 Mar 10:01–13:34" within a day, "09 Mar 00:28 – 31 Mar 01:03" across days. */
export function timeRange(start: number | null | undefined, end: number | null | undefined): string {
  if (start == null || end == null) return "—";
  const a = local(start), b = local(end);
  const sameDay = a.getUTCFullYear() === b.getUTCFullYear() && a.getUTCMonth() === b.getUTCMonth() && a.getUTCDate() === b.getUTCDate();
  return sameDay ? `${dateTime(start)}–${clock(end)}` : `${dateTime(start)} – ${dateTime(end)}`;
}

export function duration(seconds: number | null | undefined): string {
  if (seconds == null) return "—";
  const s = Math.round(seconds);
  if (s < 60) return `${s} s`;
  if (s < 3600) return `${Math.floor(s / 60)} min`;
  if (s < 86400) {
    const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
    return m ? `${h} h ${m} min` : `${h} h`;
  }
  const d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600);
  return h ? `${d} d ${h} h` : `${d} d`;
}

export const pct = (x: number) => `${(x * 100).toFixed(1).replace(/\.0$/, "")}%`;

export const ROLE_LABEL: Record<string, string> = {
  ORIGIN: "Likely origin", RELAY: "Relay", HUB: "Hub", COLLECTOR: "Collector", DISTRIBUTOR: "Distributor",
  SINK: "Sink", POOLED: "Pooled", CLUSTER_MEMBER: "Cluster member", COUNTERPARTY: "Counterparty",
};
export const PATTERN_LABEL: Record<string, string> = {
  RELAY: "Pass-through", HUB: "Fan-in → fan-out", LAYERED_RECEIPT: "Layered receipt",
  ROUND_TRIP: "Circular flow", IDENTITY: "Shared attributes",
};
export const RULE_LABEL: Record<string, string> = {
  RELAY: "Pass-through", HUB: "Fan-in → fan-out hub", LAYERED_RECEIPT: "Received layered funds",
  ROUND_TRIP: "Circular money flow", SHARED_ATTRIBUTE: "Shared device / KYC / IP",
  ADDITIONAL_LINK_TYPE: "Additional shared attribute", REPEATED: "Repeated pass-through",
  CHAIN: "Part of a relay chain", CORROBORATED_LAYERING: "Corroborated rapid layering",
  CONSOLIDATION: "Consolidates several chains", FAMILY_CAP: "Family cap",
};
export const OBS_LABEL: Record<string, string> = {
  POOLED: "Pooled account", ORIGIN_ZEROED: "Likely origin of funds", ORIGIN: "Origin (contra-indicated)",
  ISOLATED_RELAY: "Isolated pass-through", UNCORROBORATED: "Uncorroborated", MITIGATED: "Downgraded by history",
  INFRA_ATTRIBUTE: "Shared infrastructure", RECIPROCAL: "Two-party exchange", NEAR_MISS: "Near miss",
  HISTORY_UNAVAILABLE: "History unavailable", NO_PATTERN: "No pattern",
};
