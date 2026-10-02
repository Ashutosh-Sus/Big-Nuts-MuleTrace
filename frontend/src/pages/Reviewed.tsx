import { Fragment, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ChevronDown, ChevronRight, ShieldOff, Users } from "lucide-react";
import { api, type ObservationRow } from "../api";
import { useApp, useLoad } from "../state";
import { Empty, ErrorBox, RoleBadge, SeverityBadge, Spinner } from "../components/Badges";
import { OBS_LABEL } from "../format";

// Reasons an account was considered and set aside. NO_PATTERN ("nothing notable") is available but off by default.
const REASONS = ["MITIGATED", "ORIGIN_ZEROED", "ORIGIN", "INFRA_ATTRIBUTE", "ISOLATED_RELAY", "POOLED",
  "UNCORROBORATED", "NEAR_MISS", "RECIPROCAL", "HISTORY_UNAVAILABLE", "NO_PATTERN"];
const DEFAULT_REASONS = REASONS.filter((k) => k !== "NO_PATTERN");
const LIMIT = 2000;

interface Row { key: string; kind: string; text: string; accounts: ObservationRow[] }

// Identical statements (one shared office IP seen by 23 accounts) collapse into one row.
function group(items: ObservationRow[]): Row[] {
  const rows = new Map<string, Row>();
  for (const o of items) {
    const key = `${o.kind}\u0000${o.text}`;
    const row = rows.get(key);
    if (row) row.accounts.push(o);
    else rows.set(key, { key, kind: o.kind, text: o.text, accounts: [o] });
  }
  return [...rows.values()];
}

export default function Reviewed() {
  const { version } = useApp();
  const [sp, setSp] = useSearchParams();
  const [expanded, setExpanded] = useState<string | null>(null);
  const kinds = sp.get("kind") ? sp.get("kind")!.split(",").filter((k) => REASONS.includes(k)) : DEFAULT_REASONS;
  const scope = sp.get("scope") === "all" ? "all" : "unflagged";
  const q = sp.get("q") ?? "";
  const set = (k: string, v: string | null) => {
    const next = new URLSearchParams(sp);
    if (v) next.set(k, v); else next.delete(k);
    setSp(next, { replace: true });
  };
  const toggleKind = (k: string) => {
    const next = kinds.includes(k) ? kinds.filter((x) => x !== k) : [...kinds, k];
    const same = next.length === DEFAULT_REASONS.length && DEFAULT_REASONS.every((x) => next.includes(x));
    set("kind", same ? null : next.join(",") || "NONE");
  };
  const params: Record<string, string> = { kind: kinds.join(",") || "NONE", limit: String(LIMIT) };
  if (scope === "unflagged") params.flagged = "false";
  if (q) params.q = q;
  const { data, error, loading } = useLoad(() => api.observations(params), [version, sp.toString()]);
  const rows = data ? group(data.items) : [];
  const accounts = data ? new Set(data.items.map((o) => o.account)).size : 0;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h1 className="flex items-center gap-2 text-lg font-semibold"><ShieldOff size={18} className="text-good" /> Reviewed and not flagged</h1>
          <p className="text-sm text-muted">Activity that was considered and set aside, with the stated reason. Open any account for the full “Why not flagged?”.</p>
        </div>
        <input className="input w-60" placeholder="Filter by account ID" value={q} aria-label="Filter by account ID"
          onChange={(e) => set("q", e.target.value)} />
      </div>

      <div className="card flex flex-wrap items-center gap-x-5 gap-y-2 px-4 py-2.5">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="label mr-1">Accounts</span>
          {(["unflagged", "all"] as const).map((s) => (
            <button key={s} className={`chip ${scope === s ? "chip-on" : ""}`} aria-pressed={scope === s}
              onClick={() => set("scope", s === "all" ? "all" : null)}>
              {s === "all" ? "All, incl. flagged" : "Not flagged"}
            </button>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="label mr-1">Reason</span>
          {REASONS.filter((k) => data?.counts[k]).map((k) => (
            <button key={k} className={`chip ${kinds.includes(k) ? "chip-on" : ""}`} aria-pressed={kinds.includes(k)}
              onClick={() => toggleKind(k)}>
              {OBS_LABEL[k] ?? k}<span className="num ml-1">{data?.counts[k] ?? 0}</span>
            </button>
          ))}
        </div>
        {(sp.get("kind") || sp.get("scope") || q) ? (
          <button className="btn btn-ghost text-xs" onClick={() => setSp(new URLSearchParams(), { replace: true })}>Reset filters</button>
        ) : null}
      </div>

      {error && <ErrorBox message={error} />}
      <section className="card overflow-x-auto">
        {loading && !data ? <Spinner /> : !rows.length ? <Empty>No reviewed activity matches these filters.</Empty> : (
          <table className="tbl w-full min-w-[760px] text-sm">
            <thead>
              <tr><th className="w-40">Account</th><th className="w-44">Reason</th><th>Why it was set aside</th>
                <th className="w-36">Outcome</th></tr>
            </thead>
            <tbody>
              {rows.map((r) => {
                const many = r.accounts.length > 1;
                const one = r.accounts[0];
                const open = expanded === r.key;
                return (
                  <Fragment key={r.key}>
                    <tr className={many ? "cursor-pointer hover:bg-sunken/70" : ""}
                      onClick={many ? () => setExpanded(open ? null : r.key) : undefined}>
                      <td className="font-mono text-[13px] font-semibold">
                        {many ? (
                          <button className="flex items-center gap-1" aria-expanded={open}>
                            {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}<Users size={14} /> {r.accounts.length} accounts
                          </button>
                        ) : <Link to={`/account/${encodeURIComponent(one.account)}`} className="link">{one.account}</Link>}
                      </td>
                      <td><span className="rounded bg-good-soft px-1.5 py-0.5 text-2xs font-semibold text-good-ink">{OBS_LABEL[r.kind] ?? r.kind}</span></td>
                      <td className="text-ink2"><span className="text-xs leading-relaxed">{r.text}</span></td>
                      <td>
                        {many ? <Outcome rows={r.accounts} /> : (
                          <span className="flex flex-wrap items-center gap-1"><SeverityBadge severity={one.severity} score={one.flagged ? one.score : undefined} />
                            <RoleBadge role={one.role} /></span>
                        )}
                      </td>
                    </tr>
                    {many && open && (
                      <tr><td colSpan={4} className="bg-sunken/40">
                        <div className="flex flex-wrap gap-1.5">{r.accounts.map((o) => (
                          <Link key={o.account} to={`/account/${encodeURIComponent(o.account)}`}
                            className="rounded border border-line bg-raised px-2 py-0.5 font-mono text-xs link">
                            {o.account}{o.flagged && <span className="ml-1 text-high-ink">· flagged</span>}
                          </Link>))}</div>
                      </td></tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        )}
      </section>
      {data && (
        <div className="text-xs text-muted">
          {data.total} observation{data.total === 1 ? "" : "s"} on {accounts} account{accounts === 1 ? "" : "s"}
          {data.total > data.items.length && ` · showing the first ${data.items.length}; narrow the filters to see the rest`}
        </div>
      )}
    </div>
  );
}

function Outcome({ rows }: { rows: ObservationRow[] }) {
  const flagged = rows.filter((o) => o.flagged).length;
  if (!flagged) return <SeverityBadge severity={null} />;
  return <span className="text-2xs font-semibold text-ink2">{flagged} of {rows.length} flagged on other evidence</span>;
}
