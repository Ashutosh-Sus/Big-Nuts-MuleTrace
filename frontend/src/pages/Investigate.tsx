import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, ArrowLeftToLine, ArrowRightToLine, ExternalLink, Network } from "lucide-react";
import { api, type AccountDetail, type CaseDetail, type GraphData, type TxnRow } from "../api";
import { useApp, useLoad } from "../state";
import { ErrorBox, RoleBadge, SeverityBadge, Spinner, StatusBadge } from "../components/Badges";
import GraphView, { GraphLegend, type Highlight } from "../components/GraphView";
import { CaseCard, DispositionPanel, IndicatorNote, ProfileCard, ScoreCard, SignalCard, Timeline, WhyNot } from "../components/Investigation";
import { dateTime, money, PATTERN_LABEL } from "../format";

type Mode = "network" | "back" | "fwd";

function merge(a: GraphData, b: GraphData): GraphData {
  const nodes = new Map(a.nodes.map((n) => [n.id, n]));
  for (const n of b.nodes) if (!nodes.has(n.id)) nodes.set(n.id, { ...n, focus: false });
  const edges = new Map(a.edges.map((e) => [e.id, e]));
  for (const e of b.edges) if (!edges.has(e.id)) edges.set(e.id, e);
  const ids = new Map((a.identity_edges ?? []).map((e) => [`${e.source}|${e.target}|${e.attr}`, e]));
  for (const e of b.identity_edges ?? []) ids.set(`${e.source}|${e.target}|${e.attr}`, e);
  return { ...a, nodes: [...nodes.values()], edges: [...edges.values()], identity_edges: [...ids.values()] };
}

export default function Investigate() {
  const { id = "" } = useParams();
  const nav = useNavigate();
  const { version, bump, analyst, theme } = useApp();
  const { data: d, error, setData } = useLoad(() => api.account(id), [id, version]);
  const [mode, setMode] = useState<Mode>("network");
  const [hops, setHops] = useState(2);
  const [suspiciousOnly, setSuspiciousOnly] = useState(true);
  const [showIdentity, setShowIdentity] = useState(true);
  const [graph, setGraph] = useState<GraphData | null>(null);
  const [graphErr, setGraphErr] = useState<string | null>(null);
  const [selectedSignal, setSelectedSignal] = useState<string | null>(null);
  const [picked, setPicked] = useState<string | null>(null);
  const [caseD, setCaseD] = useState<CaseDetail | null>(null);
  const [txns, setTxns] = useState<TxnRow[] | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => { setSelectedSignal(null); setPicked(null); setTxns(null); setMode("network"); }, [id]);

  useEffect(() => {
    let live = true;
    setGraphErr(null);
    const p = mode === "network" ? api.network(id, hops, suspiciousOnly) : api.trace(id, mode);
    p.then((g) => { if (live) setGraph(g); }).catch((e) => live && setGraphErr(e.message));
    return () => { live = false; };
  }, [id, mode, hops, suspiciousOnly, version]);

  useEffect(() => {
    setCaseD(null);
    if (d?.cases.length) api.caseDetail(d.cases[0]).then(setCaseD).catch(() => setCaseD(null));
  }, [d]);

  const scored = useMemo(() => d?.signals.filter((s) => s.qualifies) ?? [], [d]);
  useEffect(() => {
    if (d && selectedSignal == null) {
      const first = scored.find((s) => s.timeline.length) ?? null;
      setSelectedSignal(first ? first.kind : null);
    }
  }, [d, scored, selectedSignal]);

  const sig = d?.signals.find((s) => s.kind === selectedSignal) ?? null;
  const highlight: Highlight | null = useMemo(() => {
    if (!sig) return null;
    const txIds = new Set(sig.timeline.map((t) => t.txn_id));
    const path = new Set(sig.path);
    if (sig.kind === "IDENTITY") (sig.metrics.values as any[]).forEach((v) => v.shared_with.forEach((a: string) => path.add(a)));
    if (sig.kind === "RELAY" && d) {
      const p = d.corroborated ?? d.chain;
      p?.txn_ids.forEach((t) => txIds.add(t));
      p?.accounts.forEach((a) => path.add(a));
    }
    path.add(id);
    return { nodes: path, txnIds: txIds };
  }, [sig, d, id]);

  const pointsFor = (kind: string) =>
    d?.components.filter((c) => c.rule === kind || (kind === "IDENTITY" && c.family === "IDENTITY" && c.rule !== "FAMILY_CAP"))
      .reduce((a, c) => a + c.points, 0) ?? 0;

  const expand = async (node: string) => {
    if (!graph) return;
    try {
      const more = mode === "network" ? await api.network(node, 1, suspiciousOnly) : await api.trace(node, mode);
      setGraph(merge(graph, more));
    } catch (e: any) { setGraphErr(e.message); }
  };

  const decide = async (status: string, note: string) => {
    if (!d) return;
    setBusy(true);
    try {
      const r = await api.dispose(d.id, status, note, analyst);
      setData({ ...d, disposition: r.disposition, audit: r.audit } as AccountDetail);
      bump();
    } finally { setBusy(false); }
  };

  if (error) return <ErrorBox message={error} />;
  if (!d) return <Spinner />;

  const timelineRows = sig?.timeline ?? [];
  return (
    <div className="space-y-4">
      {/* header */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <button className="mb-1 flex items-center gap-1 text-xs text-muted hover:text-ink" onClick={() => nav(-1)}><ArrowLeft size={13} /> Back</button>
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="font-mono text-2xl font-semibold tracking-tight">{d.id}</h1>
            <SeverityBadge severity={d.severity} score={d.flagged ? d.score : undefined} />
            <RoleBadge role={d.role} />
            <StatusBadge status={d.disposition.status} />
          </div>
          <p className="mt-1 max-w-4xl text-sm text-ink2">{d.flagged ? d.primary_reason :
            "Not flagged. “Why this account is not flagged” lists what was considered and why it was set aside."}</p>
        </div>
      </div>
      <IndicatorNote d={d} />

      <div className="grid gap-4 xl:grid-cols-[340px_minmax(0,1fr)_380px]">
        {/* left */}
        <div className="space-y-4">
          <ScoreCard d={d} />
          <DispositionPanel d={d} busy={busy} onDecide={decide} />
          <ProfileCard d={d} />
        </div>

        {/* centre */}
        <div className="min-w-0 space-y-4">
          <section className="card">
            <div className="card-h flex-wrap">
              <div className="flex flex-wrap items-center gap-1" role="tablist" aria-label="Graph mode">
                {([["network", "Network", Network], ["back", "Where money came from", ArrowLeftToLine],
                  ["fwd", "Where money went", ArrowRightToLine]] as const).map(([m, label, Icon]) => (
                  <button key={m} role="tab" aria-selected={mode === m} onClick={() => setMode(m)}
                    className={`flex items-center gap-1.5 rounded-md px-2.5 py-1 text-[13px] font-medium ${mode === m ? "bg-accent text-white" : "text-ink2 hover:bg-sunken"}`}>
                    <Icon size={14} /> {label}</button>
                ))}
              </div>
              {mode === "network" ? (
                <div className="flex flex-wrap items-center gap-3 text-xs text-ink2">
                  <label className="flex items-center gap-1">Hops
                    <select className="input py-0.5" value={hops} onChange={(e) => setHops(Number(e.target.value))}>
                      {[1, 2, 3].map((h) => <option key={h}>{h}</option>)}</select></label>
                  <label className="flex items-center gap-1"><input type="checkbox" checked={suspiciousOnly}
                    onChange={(e) => setSuspiciousOnly(e.target.checked)} /> Suspicious flows only</label>
                  <label className="flex items-center gap-1"><input type="checkbox" checked={showIdentity}
                    onChange={(e) => setShowIdentity(e.target.checked)} /> Shared attributes</label>
                </div>
              ) : (
                <span className="text-xs text-muted">{graph?.label}</span>
              )}
            </div>
            {graphErr && <ErrorBox message={graphErr} />}
            {graph ? (
              graph.nodes.length <= 1 ? <div className="px-4 py-16 text-center text-sm text-muted">
                {mode === "network" ? "No transactions match the current filters — untick “Suspicious flows only” to see all activity." :
                  "No traced flow from this account in this direction."}</div> :
              <GraphView data={graph} highlight={highlight} theme={theme} showIdentity={showIdentity && mode === "network"}
                onSelect={setPicked} onExpand={expand} />
            ) : <Spinner label="Building graph…" />}
            <div className="space-y-1.5 border-t border-line px-4 py-2">
              <GraphLegend mode={graph?.mode ?? "network"} />
              <div className="flex flex-wrap items-center justify-between gap-2 text-2xs text-muted">
                <span>Click a node to select · double-click to expand its neighbourhood · scroll to zoom
                  {graph?.truncated && <> · <b className="text-ink2">{graph.hidden_count ?? graph.aggregated_accounts} more accounts not drawn</b> (bounded view)</>}</span>
                {graph?.accounting && <span>
                  {money(graph.accounting.start)} traced · {graph.direction === "back" ? "originated from account balances" : "kept along the way"} {money(graph.accounting.retained)}
                  {graph.accounting.stopped_at_pooled > 0 && <> · stopped at pooled {money(graph.accounting.stopped_at_pooled)}</>}
                  {graph.accounting.exact && " · exact"}</span>}
              </div>
              {picked && picked !== d.id && picked !== "__others__" && (
                <div className="flex items-center gap-2 text-xs">
                  <span>Selected <b className="font-mono">{picked}</b></span>
                  <Link className="link flex items-center gap-1" to={`/account/${picked}`}>Investigate <ExternalLink size={11} /></Link>
                </div>
              )}
            </div>
          </section>
          <Timeline title={sig ? PATTERN_LABEL[sig.kind] : ""} rows={timelineRows} focus={d.id} />
          <TxnTable id={d.id} rows={txns} onLoad={() => api.transactions(d.id).then((r) => setTxns(r.items))} />
        </div>

        {/* right */}
        <div className="space-y-4">
          <section className="card">
            <div className="card-h"><h2 className="card-t">Evidence</h2><span className="text-xs text-muted">select to trace in graph</span></div>
            <div className="space-y-2 p-3">
              {scored.length === 0 ? <div className="px-1 py-2 text-sm text-muted">No scored evidence for this account.</div> :
                scored.map((s) => <SignalCard key={s.kind} s={s} points={pointsFor(s.kind)} active={selectedSignal === s.kind}
                  onSelect={() => setSelectedSignal(selectedSignal === s.kind ? null : s.kind)} />)}
              {(d.corroborated || d.chain) && (
                <div className="rounded-md border border-dashed border-line px-3 py-2 text-xs text-ink2">
                  Traced relay path: <span className="font-mono">{(d.corroborated ?? d.chain)!.accounts.join(" → ")}</span>
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

function TxnTable({ id, rows, onLoad }: { id: string; rows: TxnRow[] | null; onLoad: () => void }) {
  return (
    <section className="card">
      <div className="card-h">
        <h2 className="card-t">Transactions</h2>
        {!rows && <button className="btn text-xs" onClick={onLoad}>Show all transactions</button>}
      </div>
      {rows && (
        <div className="max-h-[360px] overflow-auto">
          <table className="tbl w-full text-sm">
            <thead><tr><th>Time</th><th>Direction</th><th>Counterparty</th><th className="text-right">Amount</th><th>ID</th></tr></thead>
            <tbody>
              {[...rows].reverse().map((r) => (
                <tr key={r.txn_id} className={r.suspicious ? "bg-high-soft/40" : ""}>
                  <td className="num whitespace-nowrap">{dateTime(r.ts)}</td>
                  <td>{r.direction === "in" ? "Received" : "Sent"}{r.suspicious && <span className="ml-1 text-2xs font-semibold text-high-ink">· in flagged flow</span>}</td>
                  <td className="font-mono text-[13px]"><Link className="link" to={`/account/${r.direction === "in" ? r.sender : r.receiver}`}>
                    {r.direction === "in" ? r.sender : r.receiver}</Link></td>
                  <td className="num text-right">{money(r.amount)}</td>
                  <td className="font-mono text-xs text-muted">{r.txn_id}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {!rows && <div className="px-4 py-3 text-xs text-muted">Full transaction history for {id}.</div>}
    </section>
  );
}
