export type Severity = "HIGH" | "MEDIUM" | "LOW";
export type Status = "OPEN" | "CONFIRMED" | "CLEARED" | "MIXED";

export interface IngestError { row: number; reason: string; excerpt: string }
export interface IngestReport {
  rows_total: number; rows_accepted: number; rows_rejected: number; duplicates_dropped: number;
  errors: IngestError[]; column_mapping: Record<string, string>; ignored_columns: string[];
  time_mode: string; time_mode_label: string; currency: string; currency_symbol: string;
  coverage: Record<string, boolean>; txn_id_derived: boolean; time_start: number | null; time_end: number | null;
}
export interface DatasetView {
  dataset: { id: number; name: string; sha256: string; config_hash: string; engine: string } | null;
  report: IngestReport | null; currency: string | null; symbol: string | null;
  history_limited: boolean | null; establishment_evidence: boolean | null;
}
export interface QueueItem {
  type: "account" | "group"; id: string; score: number; severity: Severity; status: Status;
  patterns: string[]; families: string[]; role: string | null; primary_reason: string; exposure: number;
  cases: string[]; size?: number; members?: string[];
}
export interface Observation { kind: string; text: string; account?: string; episode?: string }
export interface ObservationRow extends Observation {
  account: string; flagged: boolean; severity: Severity | null; score: number; role: string | null; status: Status;
}
export interface ObservationList { items: ObservationRow[]; total: number; counts: Record<string, number> }
export interface Summary extends DatasetView {
  kpis: { accounts: number; transactions: number; flagged: number; cases: number; value_total: number;
    exposure: number; flow_links: number; time_start: number; time_end: number };
  severity: Record<Severity, number>; patterns: Record<string, number>; pattern_labels: Record<string, string>;
  status: Record<string, number>; top: QueueItem[]; reviewed_not_flagged: (Observation & { account: string })[];
  reviewed_total: number; review_kinds: string[];
  decided_not_flagged: { id: string; status: Status; analyst: string | null; at: number | null }[];
}
export interface TxnRow {
  txn_id: string; ts: number; sender: string; receiver: string; amount: number; channel: string | null;
  dwell_seconds?: number; direction?: "in" | "out"; suspicious?: boolean;
}
export interface Component { family: string; rule: string; points: number; tier: string | null; detail: string; ref: string | null }
export interface SignalView {
  kind: string; label: string; family: string; raw_tier: string | null; final_tier: string | null;
  qualifies: boolean; reason: string; metrics: Record<string, any>; notes: string[]; finding: string | null;
  timeline: TxnRow[]; timeline_total: number; path: string[];
}
export interface PathInfo { accounts: string[]; txn_ids: string[]; span: number }
export interface AuditRow { id: number; account_id: string; action: string; from_status: string | null;
  to_status: string | null; note: string | null; analyst: string | null; at: number }
export interface AccountDetail {
  id: string;
  profile: { first_seen: number; last_seen: number; in_count: number; out_count: number; in_total: number;
    out_total: number; counterparties: number; created: number | null; age_days: number | null;
    establishment: string; establishment_basis: string; pooled: boolean; attributes: Record<string, string[]> };
  flagged: boolean; score: number; severity: Severity | null; families: string[]; exposure: number;
  primary_reason: string; components: Component[]; signals: SignalView[]; role: string | null; cases: string[];
  indicator: { status: string; text: string | null; reasons: string[] };
  chain: PathInfo | null; corroborated: PathInfo | null; observations: Observation[];
  disposition: { status: Status; note?: string; analyst?: string; updated_at?: number }; audit: AuditRow[];
}
export interface GraphNode {
  id: string; score?: number; severity?: Severity | null; flagged?: boolean; role?: string | null;
  status?: string; pooled?: boolean; focus?: boolean; hop?: number; indicator?: string | null;
  traced?: number; retained?: number; stopped?: boolean; dwell_seconds?: number | null;
  aggregate?: boolean; count?: number; label?: string;
}
export interface GraphEdge {
  id: string; source: string; target: string; count?: number; total?: number; amount?: number;
  first_ts: number | null; last_ts: number | null; txn_ids: string[]; suspicious?: boolean;
}
export interface GraphData {
  mode: "network" | "flow" | "transactions"; focus: string; case?: string; nodes: GraphNode[]; edges: GraphEdge[];
  identity_edges?: { source: string; target: string; attr: string; value: string }[];
  hidden_count?: number; total_count?: number; truncated?: boolean; label?: string; direction?: string;
  accounting?: { start: number; retained: number; stopped_at_pooled: number; beyond_hop_limit: number; exact: boolean };
  aggregated_accounts?: number;
}
export interface CaseDetail {
  id: string; members: { id: string; role: string | null; score: number; severity: Severity | null; flagged: boolean; status: string }[];
  metrics: { accounts: number; active: number; transactions: number; start: number | null; end: number | null;
    median_dwell_seconds: number | null; value_from_origins: number | null; value_moved: number };
  families: string[]; origins: string[]; timeline: TxnRow[]; timeline_total: number; timeline_member: string | null;
  confirmed: number; confirmed_flagged: number; decided_not_flagged: number; flagged: number;
}
export interface CaseListItem {
  id: string; severity: Severity; severity_counts: Record<Severity, number>; accounts: number; flagged: number;
  origins: number; metrics: CaseDetail["metrics"]; families: string[]; confirmed: number; confirmed_flagged: number;
  decided_not_flagged: number; fully_confirmed: boolean;
}

export class ApiError extends Error {
  constructor(public status: number, message: string, public body?: any) { super(message); }
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init);
  const text = await res.text();
  let body: any = null;
  try { body = text ? JSON.parse(text) : null; } catch { body = text; }
  if (!res.ok) {
    const msg = (body && (body.detail || body.message)) || `Request failed (${res.status})`;
    throw new ApiError(res.status, typeof msg === "string" ? msg : JSON.stringify(msg), body);
  }
  return body as T;
}

const json = (body: unknown): RequestInit => ({
  method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
});

export const api = {
  current: () => req<DatasetView>("/api/datasets/current"),
  upload: (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return req<DatasetView>("/api/datasets", { method: "POST", body: fd });
  },
  loadDemo: () => req<DatasetView>("/api/datasets/demo", { method: "POST" }),
  reset: (analyst: string) => req<DatasetView>("/api/reset", json({ analyst })),
  summary: () => req<Summary>("/api/summary"),
  queue: (params: Record<string, string>) =>
    req<{ items: QueueItem[]; total: number }>("/api/queue?" + new URLSearchParams(params)),
  search: (q: string) => req<{ items: { id: string; flagged: boolean; score: number; severity: Severity | null; role: string | null }[] }>(
    "/api/search?q=" + encodeURIComponent(q)),
  account: (id: string) => req<AccountDetail>(`/api/accounts/${encodeURIComponent(id)}`),
  transactions: (id: string) => req<{ items: TxnRow[]; total: number }>(`/api/accounts/${encodeURIComponent(id)}/transactions`),
  network: (id: string, hops: number, suspiciousOnly: boolean, minAmount = 0) =>
    req<GraphData>(`/api/accounts/${encodeURIComponent(id)}/network?` +
      new URLSearchParams({ hops: String(hops), suspicious_only: String(suspiciousOnly), min_amount: String(minAmount) })),
  trace: (id: string, dir: "fwd" | "back") => req<GraphData>(`/api/accounts/${encodeURIComponent(id)}/trace?dir=${dir}`),
  cases: () => req<{ items: CaseListItem[]; total: number; unflagged_cases: number }>("/api/cases"),
  caseDetail: (id: string, member?: string | null) => req<CaseDetail>(`/api/cases/${encodeURIComponent(id)}` +
    (member ? `?member=${encodeURIComponent(member)}` : "")),
  caseNetwork: (id: string) => req<GraphData>(`/api/cases/${encodeURIComponent(id)}/network`),
  observations: (params: Record<string, string>) => req<ObservationList>(
    "/api/observations?" + new URLSearchParams(params)),
  dispose: (id: string, status: string, note: string, analyst: string) =>
    req<{ disposition: any; audit: AuditRow[] }>(`/api/accounts/${encodeURIComponent(id)}/disposition`, json({ status, note, analyst })),
  config: () => req<{ config: Record<string, any>; hash: string; engine: string }>("/api/config"),
};
