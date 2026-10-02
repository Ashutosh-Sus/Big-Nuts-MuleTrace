import { Fragment, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { ChevronDown, ChevronRight, Download, Users } from "lucide-react";
import { api } from "../api";
import { useApp, useLoad } from "../state";
import { Empty, ErrorBox, RoleBadge, SeverityBadge, Spinner, StatusBadge } from "../components/Badges";
import { moneyShort, PATTERN_LABEL } from "../format";
import { accountPath } from "../lib/paths";

const SEVS = ["HIGH", "MEDIUM", "LOW"];
const PATTERNS = ["RELAY", "HUB", "LAYERED_RECEIPT", "ROUND_TRIP", "IDENTITY"];
const STATUSES = ["OPEN", "CONFIRMED", "CLEARED"];

function toggle(list: string[], v: string) {
  return list.includes(v) ? list.filter((x) => x !== v) : [...list, v];
}

export default function Queue() {
  const { version } = useApp();
  const [sp, setSp] = useSearchParams();
  const nav = useNavigate();
  const [expanded, setExpanded] = useState<string | null>(null);
  const get = (k: string) => (sp.get(k) ? sp.get(k)!.split(",") : []);
  const sev = get("severity"), pat = get("pattern"), st = get("status");
  const q = sp.get("q") ?? "";
  const set = (k: string, vals: string[] | string) => {
    const next = new URLSearchParams(sp);
    const v = Array.isArray(vals) ? vals.join(",") : vals;
    if (v) next.set(k, v); else next.delete(k);
    setSp(next, { replace: true });
  };
  const params: Record<string, string> = {};
  if (sev.length) params.severity = sev.join(",");
  if (pat.length) params.pattern = pat.join(",");
  if (st.length) params.status = st.join(",");
  if (q) params.q = q;
  const { data, error, loading } = useLoad(() => api.queue(params), [version, sp.toString()]);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h1 className="text-lg font-semibold">Investigation queue</h1>
          <p className="text-sm text-muted">Ordered by severity, evidence score, then exposure. Click a row to investigate.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <input className="input w-60" placeholder="Filter by account ID" aria-label="Filter the queue by account ID" value={q} onChange={(e) => set("q", e.target.value)} />
          <a className="btn" href={"/api/export/queue.csv?" + new URLSearchParams(params)} download
            title="Download the queue as shown, with the current filters, as CSV">
            <Download size={15} /> Export CSV
          </a>
        </div>
      </div>
      <div className="card flex flex-wrap items-center gap-x-5 gap-y-2 px-4 py-2.5">
        <FilterGroup label="Severity" options={SEVS} selected={sev} onToggle={(v) => set("severity", toggle(sev, v))} />
        <FilterGroup label="Pattern" options={PATTERNS} selected={pat} onToggle={(v) => set("pattern", toggle(pat, v))}
          fmt={(p) => PATTERN_LABEL[p]} />
        <FilterGroup label="Status" options={STATUSES} selected={st} onToggle={(v) => set("status", toggle(st, v))}
          fmt={(s) => s[0] + s.slice(1).toLowerCase()} />
        {(sev.length || pat.length || st.length || q) ? (
          <button className="btn btn-ghost text-xs" onClick={() => setSp(new URLSearchParams(), { replace: true })}>Clear filters</button>
        ) : null}
      </div>
      {error && <ErrorBox message={error} />}
      <section className="card overflow-x-auto">
        {loading && !data ? <Spinner /> : !data?.items.length ? <Empty>No accounts match these filters.</Empty> : (
          <table className="tbl w-full min-w-[900px] text-sm">
            <thead>
              <tr><th className="w-36">Account</th><th className="w-36">Severity · score</th><th>Primary reason</th>
                <th className="w-56">Patterns</th><th className="w-28">Role</th><th className="w-24 text-right">Exposure</th><th className="w-24">Status</th></tr>
            </thead>
            <tbody>
              {data.items.map((i) => (
                <Fragment key={i.id}>
                  <tr className="cursor-pointer hover:bg-sunken/70"
                    onClick={() => i.type === "account" ? nav(accountPath(i.id)) : setExpanded(expanded === i.id ? null : i.id)}>
                    <td className="font-mono text-[13px] font-semibold [overflow-wrap:anywhere]">
                      {i.type === "group" ? (
                        <button type="button" className="flex items-center gap-1 py-1" aria-expanded={expanded === i.id}
                          onClick={(e) => { e.stopPropagation(); setExpanded(expanded === i.id ? null : i.id); }}>
                          {expanded === i.id ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                          <Users size={14} /> {i.size} accounts</button>
                      ) : <Link to={accountPath(i.id)} onClick={(e) => e.stopPropagation()} className="link">{i.id}</Link>}
                    </td>
                    <td><SeverityBadge severity={i.severity} score={i.score} /></td>
                    <td className="text-ink2"><span className="line-clamp-2">{i.primary_reason}</span></td>
                    <td><div className="flex flex-wrap gap-1">{i.patterns.map((p) => (
                      <span key={p} className="rounded bg-sunken px-1.5 py-0.5 text-2xs text-ink2">{PATTERN_LABEL[p]}</span>))}</div></td>
                    <td><RoleBadge role={i.role} /></td>
                    <td className="num text-right">{i.exposure ? moneyShort(i.exposure) : "—"}</td>
                    <td><StatusBadge status={i.status} /></td>
                  </tr>
                  {i.type === "group" && expanded === i.id && (
                    <tr><td colSpan={7} className="bg-sunken/40">
                      <div className="flex flex-wrap gap-1.5">{i.members?.map((m) => (
                        <Link key={m} to={accountPath(m)} className="rounded border border-line bg-raised px-2 py-1 font-mono text-xs link">{m}</Link>))}</div>
                    </td></tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        )}
      </section>
      {data && <div className="text-xs text-muted">{data.total} item{data.total === 1 ? "" : "s"}</div>}
    </div>
  );
}

function FilterGroup({ label, options, selected, onToggle, fmt }: {
  label: string; options: string[]; selected: string[]; onToggle: (v: string) => void; fmt?: (v: string) => string;
}) {
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <span className="label mr-1">{label}</span>
      {options.map((o) => (
        <button key={o} className={`chip ${selected.includes(o) ? "chip-on" : ""}`} onClick={() => onToggle(o)}
          aria-pressed={selected.includes(o)}>
          {fmt ? fmt(o) : o[0] + o.slice(1).toLowerCase()}
        </button>
      ))}
    </div>
  );
}
