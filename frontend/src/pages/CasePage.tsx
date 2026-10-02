import { Fragment, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ExternalLink } from "lucide-react";
import { api } from "../api";
import { useApp, useLoad } from "../state";
import { ErrorBox, SeverityBadge, Spinner, StatusBadge } from "../components/Badges";
import { GraphFrame, type Highlight } from "../components/GraphView";
import { Timeline } from "../components/Investigation";
import { MethodButton } from "../components/MethodPanel";
import { duration, moneyShort, ROLE_LABEL, timeRange } from "../format";
import { flaggedFirst } from "../lib/members";
import { accountPath } from "../lib/paths";

export default function CasePage() {
  const { id = "" } = useParams();
  const nav = useNavigate();
  const { version, theme } = useApp();
  const { data: c, error } = useLoad(() => api.caseDetail(id), [id, version]);
  const { data: g, error: graphErr } = useLoad(() => api.caseNetwork(id), [id, version]);
  const { data: summary } = useLoad(() => api.caseSummary(id), [id, version]);
  const [picked, setPicked] = useState<string | null>(null);
  const [showIdentity, setShowIdentity] = useState(true);
  // selecting a member shows that member's case transactions (the full case timeline is bounded)
  const { data: memberTl } = useLoad(() => (picked ? api.caseDetail(id, picked) : Promise.resolve(null)), [id, picked, version]);

  // selecting a member lights up its case transactions
  const highlight: Highlight | null = useMemo(() => {
    if (!picked || !g) return null;
    const txnIds = new Set(g.edges.filter((e) => e.source === picked || e.target === picked).flatMap((e) => e.txn_ids));
    return { nodes: new Set([picked]), txnIds };
  }, [picked, g]);

  if (error) return <ErrorBox message={error} />;
  if (!c) return <Spinner />;
  const m = c.metrics;
  const toggle = (acc: string) => setPicked(picked === acc ? null : acc);
  const facts = [
    `${m.accounts} accounts`, `${c.flagged} flagged`,
    c.flagged > 0 ? `${c.confirmed_flagged} of ${c.flagged} flagged confirmed` : null,
    c.decided_not_flagged > 0 ? `${c.decided_not_flagged} decision${c.decided_not_flagged > 1 ? "s" : ""} on not-flagged members` : null,
    m.value_from_origins != null && c.origins.length > 0 ? `${moneyShort(m.value_from_origins)} entered from likely origins` : null,
    m.start && m.end ? `${timeRange(m.start, m.end)} (${duration(m.end - m.start)})` : null,
    m.median_dwell_seconds != null ? `median dwell ${duration(m.median_dwell_seconds)}` : null,
  ].filter(Boolean);
  const members = flaggedFirst(c.members);
  const tl = picked && memberTl?.timeline_member === picked ? memberTl : c;
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-lg font-semibold">Case {c.id}</h1>
        <p className="text-sm text-muted">{facts.join(" · ")}</p>
        {c.flagged === 0 && <p className="text-xs text-muted">No member flagged — roles are not assigned.</p>}
      </div>
      {summary && summary.id === c.id && summary.lines.length > 0 && (
        <section className="card" aria-labelledby="case-summary-title">
          <div className="card-h"><h2 id="case-summary-title" className="card-t">Money-flow summary</h2>
            <div className="flex items-center gap-2"><span className="text-xs text-muted">from the case's computed data</span><MethodButton /></div></div>
          <dl className="grid grid-cols-[minmax(0,1fr)] gap-x-4 gap-y-1 px-4 py-3 text-sm sm:grid-cols-[84px_minmax(0,1fr)] sm:gap-y-2">
            {summary.lines.map((l) => (
              <Fragment key={l.kind}>
                <dt className="label pt-0.5">{l.label}</dt>
                <dd className="mb-1 leading-relaxed text-ink2 [overflow-wrap:anywhere] sm:mb-0">{l.text}</dd>
              </Fragment>
            ))}
          </dl>
        </section>
      )}
      <section className="card">
        <div className="card-h flex-wrap">
          <h2 className="card-t">Case network</h2>
          <div className="flex flex-wrap items-center gap-3 text-xs text-ink2">
            <span className="text-muted">members and the case transactions between them</span>
            <label className="flex items-center gap-1.5 py-1.5"><input type="checkbox" className="h-4 w-4" checked={showIdentity}
              onChange={(e) => setShowIdentity(e.target.checked)} /> Shared attributes</label>
          </div>
        </div>
        {graphErr && <ErrorBox message={graphErr} />}
        {g ? <GraphFrame data={g} highlight={highlight} theme={theme} showIdentity={showIdentity} height={480}
          selected={picked} onSelect={setPicked} onExpand={(acc) => nav(accountPath(acc))} title={`Case ${c.id}`}
          expandHint="Double-click to investigate the account"
          selectedActions={(acc) => <Link className="link flex items-center gap-1 py-1" to={accountPath(acc)}>Investigate <ExternalLink size={11} /></Link>}
          notes={g.truncated ? <div className="text-xs text-muted"><b className="text-ink2">Showing {g.nodes.length} of {g.total_count ?? m.accounts} accounts</b> — the case's most valuable money paths (likely origin → relays → collector → cash-out), kept connected. Every member is listed below.</div> : null} />
          : !graphErr && <Spinner label="Building graph…" />}
      </section>
      <div className="grid grid-cols-[minmax(0,1fr)] gap-4 lg:grid-cols-[420px_minmax(0,1fr)]">
        <section className="card min-w-0">
          <div className="card-h"><h2 className="card-t">Members and observed roles</h2><span className="text-xs text-muted">flagged first · select to highlight</span></div>
          <div className="max-h-[560px] overflow-auto">
            <table className="tbl w-full text-sm">
              <thead className="sticky top-0 z-10 bg-surface"><tr><th>Account</th><th>Role</th><th>Severity</th><th>Status</th></tr></thead>
              <tbody>
                {members.map((mem) => (
                  <tr key={mem.id} onClick={() => toggle(mem.id)} aria-selected={picked === mem.id} tabIndex={0}
                    onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(mem.id); } }}
                    className={`cursor-pointer focus-visible:outline-offset-[-2px] ${picked === mem.id ? "bg-accent-soft" : "hover:bg-sunken/70"}`}>
                    <td className="font-mono [overflow-wrap:anywhere]"><Link className="link" to={accountPath(mem.id)} onClick={(e) => e.stopPropagation()}>{mem.id}</Link></td>
                    <td>{mem.role ? ROLE_LABEL[mem.role] ?? mem.role : "—"}</td>
                    <td><SeverityBadge severity={mem.severity} score={mem.flagged ? mem.score : undefined} /></td>
                    <td><StatusBadge status={mem.status} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
        <Timeline title={tl.timeline_member ? `case transactions of ${tl.timeline_member}` : "case transactions"}
          rows={tl.timeline} total={tl.timeline_total} focus={picked ?? ""} />
      </div>
    </div>
  );
}
