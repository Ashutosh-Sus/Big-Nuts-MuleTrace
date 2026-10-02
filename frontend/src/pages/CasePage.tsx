import { useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ExternalLink } from "lucide-react";
import { api } from "../api";
import { useApp, useLoad } from "../state";
import { ErrorBox, SeverityBadge, Spinner, StatusBadge } from "../components/Badges";
import GraphView, { GraphLegend, type Highlight } from "../components/GraphView";
import { Timeline } from "../components/Investigation";
import { duration, moneyShort, ROLE_LABEL } from "../format";

export default function CasePage() {
  const { id = "" } = useParams();
  const nav = useNavigate();
  const { version, theme } = useApp();
  const { data: c, error } = useLoad(() => api.caseDetail(id), [id, version]);
  const { data: g, error: graphErr } = useLoad(() => api.caseNetwork(id), [id, version]);
  const [picked, setPicked] = useState<string | null>(null);
  const [showIdentity, setShowIdentity] = useState(true);

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
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-lg font-semibold">Case {c.id}</h1>
        <p className="text-sm text-muted">{m.accounts} accounts · {c.flagged} flagged · {c.confirmed} confirmed ·
          {" "}{m.value_from_origins != null ? <>{moneyShort(m.value_from_origins)} entered from likely origins</> : "value from origins —"} ·
          {" "}{m.start && m.end ? duration(m.end - m.start) : ""} window · median dwell {duration(m.median_dwell_seconds)}</p>
        {c.flagged === 0 && <p className="text-xs text-muted">No member flagged — roles are not assigned.</p>}
      </div>
      <section className="card">
        <div className="card-h flex-wrap">
          <h2 className="card-t">Case network</h2>
          <div className="flex flex-wrap items-center gap-3 text-xs text-ink2">
            <span className="text-muted">every member and the case transactions between them</span>
            <label className="flex items-center gap-1"><input type="checkbox" checked={showIdentity}
              onChange={(e) => setShowIdentity(e.target.checked)} /> Shared attributes</label>
          </div>
        </div>
        {graphErr && <ErrorBox message={graphErr} />}
        {g ? <GraphView data={g} highlight={highlight} theme={theme} showIdentity={showIdentity} height={460}
          onSelect={(acc) => setPicked(acc)} onExpand={(acc) => nav(`/account/${encodeURIComponent(acc)}`)}
          expandHint="Double-click to investigate" /> : !graphErr && <Spinner label="Building graph…" />}
        <div className="space-y-1.5 border-t border-line px-4 py-2">
          <GraphLegend mode="network" />
          <div className="text-2xs text-muted">Click a node or a member row to light up its transactions · double-click a node to investigate · scroll to zoom
            {g?.truncated && <> · <b className="text-ink2">{g.hidden_count} more accounts not drawn</b> (bounded view)</>}</div>
          {picked && (
            <div className="flex items-center gap-2 text-xs">
              <span>Selected <b className="font-mono">{picked}</b></span>
              <Link className="link flex items-center gap-1" to={`/account/${encodeURIComponent(picked)}`}>Investigate <ExternalLink size={11} /></Link>
              <button className="link" onClick={() => setPicked(null)}>Clear selection</button>
            </div>
          )}
        </div>
      </section>
      <div className="grid gap-4 lg:grid-cols-[420px_minmax(0,1fr)]">
        <section className="card">
          <div className="card-h"><h2 className="card-t">Members and observed roles</h2></div>
          <table className="tbl w-full text-sm">
            <thead><tr><th>Account</th><th>Role</th><th>Severity</th><th>Status</th></tr></thead>
            <tbody>
              {c.members.map((mem) => (
                <tr key={mem.id} onClick={() => toggle(mem.id)} aria-selected={picked === mem.id}
                  className={`cursor-pointer ${picked === mem.id ? "bg-accent-soft" : "hover:bg-sunken/70"}`}>
                  <td className="font-mono"><Link className="link" to={`/account/${mem.id}`} onClick={(e) => e.stopPropagation()}>{mem.id}</Link></td>
                  <td>{mem.role ? ROLE_LABEL[mem.role] ?? mem.role : "—"}</td>
                  <td><SeverityBadge severity={mem.severity} score={mem.flagged ? mem.score : undefined} /></td>
                  <td><StatusBadge status={mem.status} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
        <Timeline title="all case transactions" rows={c.timeline} focus={picked ?? ""} />
      </div>
    </div>
  );
}
