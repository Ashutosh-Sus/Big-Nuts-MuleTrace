import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { ArrowLeft, ArrowLeftToLine, ArrowRightToLine, ExternalLink, Network, X } from "lucide-react";
import { api, type AccountDetail, type CaseDetail, type GraphData, type TxnRow } from "../api";
import { useApp, useLoad } from "../state";
import { ErrorBox, RoleBadge, SeverityBadge, Spinner, StatusBadge } from "../components/Badges";
import { GraphFrame, type Highlight } from "../components/GraphView";
import { CaseCard, DispositionPanel, IndicatorNote, ProfileCard, ScoreCard, SignalCard, Timeline, WhyNot } from "../components/Investigation";
import { dateTime, money, PATTERN_LABEL } from "../format";
import { timelineKind, toggleEvidence } from "../lib/evidence";
import { expandAction, mergeNetwork, withStatus, type GraphMode } from "../lib/graphState";
import { accountPath } from "../lib/paths";
import { submitDecision } from "../lib/decision";

const MODES: [GraphMode, string, typeof Network][] = [["network", "Network", Network],
  ["back", "Where money came from", ArrowLeftToLine], ["fwd", "Where money went", ArrowRightToLine]];

export default function Investigate() {
  const { id = "" } = useParams();
  const [sp, setSp] = useSearchParams();
  const nav = useNavigate();
  const { version, bump, analyst, theme } = useApp();
  const { data: d, error, setData } = useLoad(() => api.account(id), [id, version]);
  // the graph view is part of the address, so a refresh or a shared link opens the same view
  const view = sp.get("view");
  const mode: GraphMode = view === "back" || view === "fwd" ? view : "network";
  const setMode = (m: GraphMode) => {
    const next = new URLSearchParams(sp);
    if (m === "network") next.delete("view"); else next.set("view", m);
    setSp(next, { replace: true });
  };
  const [hops, setHops] = useState(2);
  const [suspiciousOnly, setSuspiciousOnly] = useState(true);
  const filterTouched = useRef(false);
  const [autoAll, setAutoAll] = useState(false);
  const [showIdentity, setShowIdentity] = useState(true);
  const [graph, setGraph] = useState<GraphData | null>(null);
  const [graphErr, setGraphErr] = useState<string | null>(null);
  const [selectedSignal, setSelectedSignal] = useState<string | null>(null);
  const [picked, setPicked] = useState<string | null>(null);
  const [caseD, setCaseD] = useState<CaseDetail | null>(null);
  const [txns, setTxns] = useState<{ items: TxnRow[]; total: number } | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setSelectedSignal(null); setPicked(null); setTxns(null); setGraph(null);
    filterTouched.current = false; setAutoAll(false); setSuspiciousOnly(true);
  }, [id]);

  // A decision changes one account's status, which is patched into the drawing (see `decide`), so the graph
  // is fetched only when the account, view or filters change — expanded neighbourhoods survive a decision.
  useEffect(() => {
    let live = true;
    setGraphErr(null);
    const p = mode === "network" ? api.network(id, hops, suspiciousOnly) : api.trace(id, mode);
    p.then((g) => {
      if (!live) return;
      // an account with no suspicious flows opens on all of its activity rather than an empty graph
      if (mode === "network" && suspiciousOnly && g.nodes.length <= 1 && !filterTouched.current) {
        setAutoAll(true);
        setSuspiciousOnly(false);
        return;
      }
      setGraph(g);
    }).catch((e) => live && setGraphErr(e.message));
    return () => { live = false; };
  }, [id, mode, hops, suspiciousOnly]);

  useEffect(() => {
    setCaseD(null);
    if (d?.cases.length) api.caseDetail(d.cases[0]).then(setCaseD).catch(() => setCaseD(null));
  }, [d]);

  const scored = useMemo(() => d?.signals.filter((s) => s.qualifies) ?? [], [d]);
  // no evidence is highlighted until the analyst picks a card; the timeline then follows the pick
  const sel = d?.signals.find((s) => s.kind === selectedSignal) ?? null;
  const shownKind = timelineKind(selectedSignal, scored);
  const shown = d?.signals.find((s) => s.kind === shownKind) ?? null;
  const highlight: Highlight | null = useMemo(() => {
    if (!sel) return null;
    const txIds = new Set(sel.timeline.map((t) => t.txn_id));
    const path = new Set(sel.path);
    if (sel.kind === "IDENTITY") (sel.metrics.values as any[]).forEach((v) => v.shared_with.forEach((a: string) => path.add(a)));
    if (sel.kind === "RELAY" && d) {
      const p = d.corroborated ?? d.chain;
      p?.txn_ids.forEach((t) => txIds.add(t));
      p?.accounts.forEach((a) => path.add(a));
    }
    path.add(id);
    return { nodes: path, txnIds: txIds };
  }, [sel, d, id]);

  const pointsFor = (kind: string) =>
    d?.components.filter((c) => c.rule === kind || (kind === "IDENTITY" && c.family === "IDENTITY" && c.rule !== "FAMILY_CAP"))
      .reduce((a, c) => a + c.points, 0) ?? 0;

  const expand = async (node: string) => {
    if (!graph || node === "__others__") return;
    if (expandAction(mode) === "open-trace") {          // traces are never merged: open that account's own trace
      if (node !== id && mode !== "network") nav(accountPath(node, mode));
      return;
    }
    try {
      const more = await api.network(node, 1, suspiciousOnly);
      setGraph((g) => (g ? mergeNetwork(g, more) : g));
    } catch (e: any) { setGraphErr(e.message); }
  };

  const decide = async (status: string, note: string) => {
    if (!d) return { ok: false as const, error: "Account not loaded" };
    setBusy(true);
    try {
      const r = await submitDecision(async () => {
        const res = await api.dispose(d.id, status, note, analyst);
        setData({ ...d, disposition: res.disposition, audit: res.audit } as AccountDetail);
        setGraph((g) => (g ? withStatus(g, d.id, res.disposition.status) : g));
      });
      if (r.ok) bump();
      return r;
    } finally { setBusy(false); }
  };

  const onTabKey = (e: KeyboardEvent<HTMLButtonElement>, i: number) => {
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft" && e.key !== "Home" && e.key !== "End") return;
    e.preventDefault();
    const j = e.key === "Home" ? 0 : e.key === "End" ? MODES.length - 1 : (i + (e.key === "ArrowRight" ? 1 : -1) + MODES.length) % MODES.length;
    setMode(MODES[j][0]);
    document.getElementById(`graph-tab-${MODES[j][0]}`)?.focus();
  };

  if (error) return <ErrorBox message={error} />;
  if (!d) return <Spinner />;

  const total = graph?.total_count ?? (graph ? graph.nodes.length + (graph.hidden_count ?? 0) : 0);
  return (
    <div className="space-y-4">
      {/* header */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <button className="mb-1 flex items-center gap-1 py-1 text-xs text-muted hover:text-ink" onClick={() => nav(-1)}><ArrowLeft size={13} /> Back</button>
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="min-w-0 font-mono text-2xl font-semibold tracking-tight [overflow-wrap:anywhere]">{d.id}</h1>
            <SeverityBadge severity={d.severity} score={d.flagged ? d.score : undefined} />
            <RoleBadge role={d.role} />
            <StatusBadge status={d.disposition.status} />
          </div>
          <p className="mt-1 max-w-4xl text-sm text-ink2">{d.flagged ? d.primary_reason :
            "Not flagged. “Why this account is not flagged” lists what was considered and why it was set aside."}</p>
        </div>
      </div>
      <IndicatorNote d={d} />

      <div className="grid grid-cols-[minmax(0,1fr)] gap-4 xl:grid-cols-[340px_minmax(0,1fr)_380px]">
        {/* left */}
        <div className="min-w-0 space-y-4">
          <ScoreCard d={d} />
          <DispositionPanel d={d} busy={busy} onDecide={decide} />
          <ProfileCard d={d} />
        </div>

        {/* centre */}
        <div className="min-w-0 space-y-4">
          <section className="card">
            <div className="card-h flex-wrap">
              <div className="flex flex-wrap items-center gap-1" role="tablist" aria-label="Graph view">
                {MODES.map(([m, label, Icon], i) => (
                  <button key={m} id={`graph-tab-${m}`} role="tab" aria-selected={mode === m} aria-controls="graph-panel"
                    tabIndex={mode === m ? 0 : -1} onClick={() => setMode(m)} onKeyDown={(e) => onTabKey(e, i)}
                    className={`flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-[13px] font-medium ${mode === m ? "bg-accent text-on-accent" : "text-ink2 hover:bg-sunken"}`}>
                    <Icon size={14} /> {label}</button>
                ))}
              </div>
              {mode === "network" ? (
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink2">
                  <label className="flex items-center gap-1.5 py-1">Hops
                    <select className="input py-1" value={hops} onChange={(e) => setHops(Number(e.target.value))}>
                      {[1, 2, 3].map((h) => <option key={h}>{h}</option>)}</select></label>
                  <label className="flex items-center gap-1.5 py-1.5"><input type="checkbox" className="h-4 w-4" checked={suspiciousOnly}
                    onChange={(e) => { filterTouched.current = true; setAutoAll(false); setSuspiciousOnly(e.target.checked); }} /> Suspicious flows only</label>
                  <label className="flex items-center gap-1.5 py-1.5"><input type="checkbox" className="h-4 w-4" checked={showIdentity}
                    onChange={(e) => setShowIdentity(e.target.checked)} /> Shared attributes</label>
                </div>
              ) : (
                <span className="text-xs text-muted">{graph?.label}</span>
              )}
            </div>
            <div id="graph-panel" role="tabpanel" aria-labelledby={`graph-tab-${mode}`}>
              {sel && (
                <div className="flex flex-wrap items-center gap-2 border-b border-line bg-accent-soft/40 px-4 py-1.5 text-xs text-accent-ink">
                  <span>Highlighting the <b>{PATTERN_LABEL[sel.kind] ?? sel.label}</b> evidence — other accounts and links are faded.</span>
                  <button type="button" className="link flex items-center gap-0.5 py-1" onClick={() => setSelectedSignal(null)}><X size={12} /> Show all</button>
                </div>
              )}
              {autoAll && mode === "network" && (
                <div className="border-b border-line px-4 py-1.5 text-xs text-ink2">No suspicious flows for this account — showing all of its activity.</div>
              )}
              {graphErr && <ErrorBox message={graphErr} />}
              {graph ? (
                graph.nodes.length <= 1 ? <div className="px-4 py-16 text-center text-sm text-muted">
                  {mode === "network" ? "No transactions match the current filters — untick “Suspicious flows only” to see all activity." :
                    "No traced flow from this account in this direction."}</div> :
                <GraphFrame data={graph} highlight={highlight} theme={theme} showIdentity={showIdentity && mode === "network"}
                  selected={picked} onSelect={setPicked} onExpand={expand} title={`${d.id} · ${MODES.find((x) => x[0] === mode)![1]}`}
                  expandHint={mode === "network" ? "Double-click to expand its neighbourhood" : "Double-click to trace from it"}
                  legendHighlight={!!sel}
                  selectedActions={(acc) => acc !== d.id ? (
                    <Link className="link flex items-center gap-1 py-1" to={accountPath(acc, mode === "network" ? undefined : mode)}>
                      {mode === "network" ? "Investigate" : "Trace from this account"} <ExternalLink size={11} /></Link>) : null}
                  notes={<div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted">
                    {!graph.truncated ? <span /> : graph.mode === "flow" ? (
                      <span><b className="text-ink2">{graph.aggregated_accounts} accounts</b> with the smallest traced amounts are grouped into the “+{graph.aggregated_accounts} accounts” node</span>
                    ) : (
                      <span><b className="text-ink2">Showing {graph.nodes.length} of {total} accounts</b> — the closest and most suspicious at each hop are drawn; raise Hops or untick the filter to change which</span>
                    )}
                    {graph.accounting && <span>
                      {money(graph.accounting.start)} traced · {graph.direction === "back" ? "originated from account balances" : "kept along the way"} {money(graph.accounting.retained)}
                      {graph.accounting.stopped_at_pooled > 0 && <> · stopped at pooled {money(graph.accounting.stopped_at_pooled)}</>}
                      {graph.accounting.exact && " · exact"}</span>}
                  </div>} />
              ) : <Spinner label="Building graph…" />}
            </div>
          </section>
          <Timeline title={shown ? PATTERN_LABEL[shown.kind] : ""} rows={shown?.timeline ?? []} total={shown?.timeline_total} focus={d.id} />
          <TxnTable id={d.id} data={txns} onLoad={() => api.transactions(d.id).then((r) => setTxns(r))} />
        </div>

        {/* right */}
        <div className="min-w-0 space-y-4">
          <section className="card">
            <div className="card-h"><h2 className="card-t">Evidence</h2><span className="text-xs text-muted">select to highlight in the graph</span></div>
            <div className="space-y-2 p-3">
              {scored.length === 0 ? <div className="px-1 py-2 text-sm text-muted">No scored evidence for this account.</div> :
                scored.map((s) => <SignalCard key={s.kind} s={s} points={pointsFor(s.kind)} active={selectedSignal === s.kind}
                  onSelect={() => setSelectedSignal((cur) => toggleEvidence(cur, s.kind))} />)}
              {(d.corroborated || d.chain) && (
                <div className="rounded-md border border-dashed border-line px-3 py-2 text-xs text-ink2">
                  Traced relay path: <span className="font-mono [overflow-wrap:anywhere]">{(d.corroborated ?? d.chain)!.accounts.join(" → ")}</span>
                </div>
              )}
            </div>
          </section>
          {caseD && <CaseCard c={caseD} focus={d.id} />}
          <WhyNot d={d} />
        </div>
      </div>
    </div>
  );
}

function TxnTable({ id, data, onLoad }: { id: string; data: { items: TxnRow[]; total: number } | null; onLoad: () => void }) {
  const rows = data?.items ?? null;
  return (
    <section className="card">
      <div className="card-h">
        <h2 className="card-t">Transactions</h2>
        {!rows ? <button className="btn text-xs" onClick={onLoad}>Show all transactions</button> :
          <span className="text-xs text-muted">{data!.total > rows.length ? `latest ${rows.length} of ${data!.total}` : `${rows.length}`} · times in IST</span>}
      </div>
      {rows && (
        <div className="max-h-[360px] overflow-auto">
          <table className="tbl w-full text-sm">
            <thead><tr><th>Time</th><th>Direction</th><th>Counterparty</th><th className="text-right">Amount</th><th>ID</th></tr></thead>
            <tbody>
              {[...rows].reverse().map((r) => {
                const other = r.direction === "in" ? r.sender : r.receiver;
                return (
                  <tr key={r.txn_id} className={r.suspicious ? "bg-high-soft/40" : ""}>
                    <td className="num whitespace-nowrap">{dateTime(r.ts)}</td>
                    <td>{r.direction === "in" ? "Received" : "Sent"}{r.suspicious && <span className="ml-1 text-2xs font-semibold text-high-ink">· in flagged flow</span>}</td>
                    <td className="font-mono text-[13px] [overflow-wrap:anywhere]"><Link className="link" to={accountPath(other)}>{other}</Link></td>
                    <td className="num text-right">{money(r.amount)}</td>
                    <td className="font-mono text-xs text-muted">{r.txn_id}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      {!rows && <div className="px-4 py-3 text-xs text-muted">Full transaction history for {id}.</div>}
    </section>
  );
}
