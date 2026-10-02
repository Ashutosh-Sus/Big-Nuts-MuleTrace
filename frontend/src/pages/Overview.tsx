import { Link } from "react-router-dom";
import { ArrowRight, ShieldOff } from "lucide-react";
import { api, type Severity } from "../api";
import { useApp, useLoad } from "../state";
import { ErrorBox, RoleBadge, SeverityBadge, Spinner, StatusBadge } from "../components/Badges";
import { date, moneyShort, OBS_LABEL, PATTERN_LABEL } from "../format";
import { accountPath, queuePath } from "../lib/paths";

const SEV_ORDER: Severity[] = ["HIGH", "MEDIUM", "LOW"];
const SEV_FILL: Record<Severity, string> = { HIGH: "bg-high", MEDIUM: "bg-medium", LOW: "bg-low" };

function Tile({ label, value, sub, title }: { label: string; value: string; sub?: string; title?: string }) {
  return (
    <div className="card px-4 py-3" title={title}>
      <div className="label">{label}</div>
      <div className="mt-1 text-2xl font-semibold tracking-tight">{value}</div>
      {sub && <div className="mt-0.5 text-xs text-muted">{sub}</div>}
    </div>
  );
}

export default function Overview() {
  const { version } = useApp();
  const { data: s, error } = useLoad(api.summary, [version]);
  if (error) return <ErrorBox message={error} />;
  if (!s) return <Spinner />;
  const k = s.kpis;
  const flaggedTotal = SEV_ORDER.reduce((a, x) => a + s.severity[x], 0);
  const maxPattern = Math.max(1, ...Object.values(s.patterns));
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h1 className="text-lg font-semibold">Overview</h1>
          <p className="text-sm text-muted">{s.dataset?.name} · {date(k.time_start)} – {date(k.time_end)}</p>
        </div>
        <Link to="/queue" className="btn btn-primary">Open investigation queue <ArrowRight size={15} /></Link>
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <Tile label="Accounts" value={k.accounts.toLocaleString()} />
        <Tile label="Transactions analysed" value={k.transactions.toLocaleString()} sub={`${k.flow_links.toLocaleString()} computed flow links`} />
        <Tile label="Flagged accounts" value={String(k.flagged)} sub={`${((k.flagged / Math.max(1, k.accounts)) * 100).toFixed(1)}% of accounts`} />
        <Tile label="High severity" value={String(s.severity.HIGH)} />
        <Tile label="Suspicious cases" value={String(k.cases)} sub="connected flows with a flagged member" />
        <Tile label="Exposure" value={moneyShort(k.exposure)} sub={`largest suspicious amount per flagged account, summed · ${moneyShort(k.value_total)} moved in all`}
          title="For each flagged account, the largest amount in its scored evidence; added up over the queue. Shown, never scored." />
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <section className="card">
          <div className="card-h"><h2 className="card-t">Risk distribution</h2><span className="text-xs text-muted">{flaggedTotal} flagged</span></div>
          <div className="space-y-4 p-4">
            {flaggedTotal > 0 ? (
              <div className="flex h-3 w-full gap-[2px] overflow-hidden rounded" role="img"
                aria-label={SEV_ORDER.map((x) => `${x} ${s.severity[x]}`).join(", ")}>
                {SEV_ORDER.filter((x) => s.severity[x] > 0).map((x) => (
                  <div key={x} className={`${SEV_FILL[x]} h-full`} style={{ flex: s.severity[x] }} title={`${x}: ${s.severity[x]}`} />
                ))}
              </div>
            ) : <div className="rounded bg-sunken px-3 py-2 text-sm text-ink2">No account in this dataset is flagged.</div>}
            <ul className="space-y-1.5">
              {SEV_ORDER.map((x) => (
                <li key={x} className="flex items-center justify-between text-sm">
                  <Link to={queuePath({ severity: x })} className="py-0.5 hover:underline"><SeverityBadge severity={x} /></Link>
                  <span className="num font-semibold">{s.severity[x]}</span>
                </li>
              ))}
            </ul>
            <div className="border-t border-line pt-3">
              <div className="label mb-2">Analyst decisions · flagged accounts</div>
              <div className="flex flex-wrap gap-3 text-sm">
                {(["OPEN", "CONFIRMED", "CLEARED"] as const).map((x) => (
                  <Link key={x} to={queuePath({ status: x })} className="flex items-center gap-1.5 py-0.5 hover:underline">
                    <StatusBadge status={x} /><span className="num font-semibold">{s.status[x]}</span></Link>
                ))}
              </div>
              {s.decided_not_flagged.length > 0 && (
                <div className="mt-2 text-xs text-ink2">
                  <div className="mb-1">Decisions on accounts that are not flagged (not in the queue):</div>
                  <div className="flex flex-wrap gap-1.5">
                    {s.decided_not_flagged.map((x) => (
                      <Link key={x.id} to={accountPath(x.id)} className="flex items-center gap-1 rounded border border-line bg-raised px-1.5 py-0.5 hover:border-line-strong">
                        <span className="font-mono">{x.id}</span><StatusBadge status={x.status} /></Link>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        </section>

        <section className="card">
          <div className="card-h"><h2 className="card-t">Patterns detected</h2><span className="text-xs text-muted">accounts per pattern</span></div>
          <ul className="space-y-2.5 p-4">
            {Object.entries(s.patterns).map(([p, n]) => (
              <li key={p}>
                <Link to={`/queue?pattern=${p}`} className="group block">
                  <div className="mb-1 flex justify-between text-sm"><span className="group-hover:underline">{PATTERN_LABEL[p] ?? p}</span>
                    <span className="num font-semibold">{n}</span></div>
                  <div className="h-2 rounded-sm bg-sunken">
                    <div className="h-2 rounded-sm bg-accent" style={{ width: `${(n / maxPattern) * 100}%` }} />
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        </section>

        <section className="card">
          <div className="card-h"><h2 className="card-t">Highest priority</h2><Link to="/queue" className="link text-xs">All</Link></div>
          {s.top.length === 0 && <div className="px-4 py-6 text-sm text-muted">Nothing to prioritise — no account is flagged.</div>}
          <ul className="divide-y divide-line">
            {s.top.map((i) => (
              <li key={i.id}>
                <Link to={i.type === "account" ? accountPath(i.id) : queuePath({ q: i.members?.[0] ?? "" })}
                  className="block px-4 py-2.5 hover:bg-sunken">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-mono text-[13px] font-semibold">{i.id}</span>
                    <span className="flex items-center gap-1.5"><RoleBadge role={i.role} /><SeverityBadge severity={i.severity} score={i.score} /></span>
                  </div>
                  <div className="mt-0.5 line-clamp-2 text-xs text-ink2" title={i.primary_reason}>{i.primary_reason}</div>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      </div>

      <section className="card">
        <div className="card-h">
          <h2 className="card-t flex items-center gap-2"><ShieldOff size={15} className="text-good" /> Reviewed and not flagged</h2>
          <span className="flex flex-wrap items-center gap-3 text-xs text-muted">
            {s.reviewed_total} not-flagged account{s.reviewed_total === 1 ? " was" : "s were"} considered and set aside, each for a stated reason
            {s.reviewed_not_flagged.length > 0 && s.reviewed_not_flagged.length < s.reviewed_total && <> · {s.reviewed_not_flagged.length} examples below</>}
            <Link to="/reviewed" className="link whitespace-nowrap py-1">View all {s.reviewed_total}</Link>
          </span>
        </div>
        {s.reviewed_not_flagged.length === 0 && <div className="px-4 py-6 text-sm text-muted">No activity needed setting aside in this dataset.</div>}
        <ul className="grid gap-px bg-line md:grid-cols-2">
          {s.reviewed_not_flagged.map((r) => (
            <li key={r.account + r.kind} className="bg-surface px-4 py-3">
              <div className="flex items-center justify-between gap-2">
                <Link to={accountPath(r.account)} className="min-w-0 font-mono text-[13px] font-semibold link [overflow-wrap:anywhere]">{r.account}</Link>
                <span className="rounded bg-good-soft px-1.5 py-0.5 text-2xs font-semibold text-good-ink">{OBS_LABEL[r.kind] ?? r.kind}</span>
              </div>
              <p className="mt-1 text-xs leading-relaxed text-ink2">{r.text}</p>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
