import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import cytoscape, { type Core, type ElementDefinition } from "cytoscape";
import dagre from "cytoscape-dagre";
import { Maximize2, Minimize2, Scan, X } from "lucide-react";
import type { GraphData, GraphNode } from "../api";
import { dateTime, duration, money, moneyShort, ROLE_LABEL } from "../format";
import { wrapColumns } from "../lib/layout";

cytoscape.use(dagre);

export interface Highlight { nodes: Set<string>; txnIds: Set<string> }

/** Fit / centre commands for the toolbar around a graph. */
export interface GraphControl { fitAll: () => void; centre: (id: string) => void }

interface Props {
  data: GraphData;
  highlight: Highlight | null;
  theme: string;
  showIdentity: boolean;
  selected?: string | null;
  onSelect?: (id: string | null) => void;
  onExpand?: (id: string) => void;
  height?: number | string;
  expandHint?: string;
  /** false: a still preview (no pan / zoom / drag), used inline on phones so the page scrolls normally */
  interactive?: boolean;
  control?: { current: GraphControl | null };
  /** reports whether the view shows only part of the graph (zoomed in for readable labels) */
  onPartialView?: (partial: boolean) => void;
}

const ROLE_SHAPE: Record<string, string> = {
  ORIGIN: "diamond", SINK: "round-rectangle", POOLED: "hexagon", HUB: "ellipse", COLLECTOR: "ellipse",
  DISTRIBUTOR: "ellipse", RELAY: "ellipse", CLUSTER_MEMBER: "ellipse", COUNTERPARTY: "ellipse",
};
const NODE_FONT = 11;
const EDGE_FONT = 9.5;
/** below this zoom node labels would render under 8 px; the first view of a large graph does not go lower */
const MIN_READABLE_ZOOM = 0.78;
const MAX_INITIAL_ZOOM = 1.5;
const LABELLED_EDGE_LIMIT = 14;

const sevWord = (s: string | null | undefined) => (s ? s[0] + s.slice(1).toLowerCase() : "");
const statusWord = (s: string | undefined) => (s === "CONFIRMED" ? "confirmed" : s === "CLEARED" ? "cleared" : "");

function tokens() {
  const cs = getComputedStyle(document.documentElement);
  const c = (n: string, a = 1) => `rgba(${cs.getPropertyValue(`--${n}`).trim().split(/\s+/).join(",")},${a})`;
  return {
    ink: c("ink"), ink2: c("ink2"), muted: c("muted"), surface: c("surface"), raised: c("raised"),
    line: c("line-strong"), edge: c("edge"), high: c("high"), medium: c("medium"), low: c("low"),
    good: c("good"), accent: c("accent"), trace: c("trace"), ident: c("ident"), sunken: c("sunken"),
  };
}

/** Second label line: score and severity in words (colour is never the only cue), traced amount in a trace,
 *  and the analyst decision. */
export function nodeLabel(n: GraphNode, traced: boolean): string {
  if (n.aggregate) return n.label ?? "";
  const parts: string[] = [];
  if (traced && n.traced != null && !n.focus) parts.push(moneyShort(n.traced));
  else if (n.severity) parts.push(`${n.score} ${sevWord(n.severity)}`);
  if (traced && n.severity && !n.focus) parts.push(sevWord(n.severity));
  const st = statusWord(n.status);
  if (st) parts.push(st);
  return parts.length ? `${n.id}\n${parts.join(" · ")}` : n.id;
}

function buildElements(data: GraphData, showIdentity: boolean): ElementDefinition[] {
  const els: ElementDefinition[] = [];
  const traced = data.mode === "flow";
  for (const n of data.nodes) {
    const cls = [
      n.aggregate ? "aggregate" : "",
      n.severity ? `sev-${n.severity}` : "plain",
      n.focus ? "focus" : "",
      n.status === "CONFIRMED" ? "confirmed" : n.status === "CLEARED" ? "cleared" : "",
      n.stopped ? "stopped" : "",
    ].filter(Boolean).join(" ");
    els.push({ data: { id: n.id, label: nodeLabel(n, traced), shape: n.aggregate ? "round-rectangle" : ROLE_SHAPE[n.role ?? ""] ?? "ellipse",
      size: n.focus ? 40 : n.role === "HUB" ? 34 : 28 }, classes: cls });
  }
  const amounts = data.edges.map((e) => (traced ? e.amount : e.total) ?? 0);
  const maxA = Math.max(1, ...amounts);
  const labelAll = data.edges.length <= LABELLED_EDGE_LIMIT;
  for (const e of data.edges) {
    const amt = (traced ? e.amount : e.total) ?? 0;
    const w = 1.2 + 4.5 * (Math.log10(1 + amt / 100) / Math.log10(1 + maxA / 100));
    const label = traced ? moneyShort(amt) : `${moneyShort(amt)}${(e.count ?? 1) > 1 ? ` ×${e.count}` : ""}`;
    els.push({ data: { id: `e:${e.id}`, source: e.source, target: e.target, label, w, txn: e.txn_ids.join("|") },
      classes: [traced ? "traced" : e.suspicious ? "suspicious" : "plain", labelAll ? "lbl" : ""].filter(Boolean).join(" ") });
  }
  if (showIdentity && data.identity_edges) {
    const seen = new Set(data.nodes.map((n) => n.id));
    data.identity_edges.forEach((e, i) => {
      if (seen.has(e.source) && seen.has(e.target)) {
        els.push({ data: { id: `id:${i}`, source: e.source, target: e.target, label: e.attr }, classes: "identity" });
      }
    });
  }
  return els;
}

/** What a node is, in words: shared by the hover tooltip and the selection panel (touch and keyboard). */
export function NodeInfo({ n, hint }: { n: GraphNode; hint?: string }) {
  if (n.aggregate) return <div>{n.label} · {moneyShort(n.traced)} traced to accounts not drawn individually</div>;
  return (
    <div className="space-y-0.5">
      <div className="font-mono font-semibold [overflow-wrap:anywhere]">{n.id}</div>
      <div>{n.severity ? `${sevWord(n.severity)} severity · score ${n.score}` : "Not flagged"}{n.role ? ` · ${ROLE_LABEL[n.role] ?? n.role}` : ""}</div>
      {n.traced != null && <div>Traced through: {money(n.traced)}{n.retained ? ` · kept ${money(n.retained)}` : ""}</div>}
      {n.dwell_seconds != null && <div>Median dwell: {duration(n.dwell_seconds)}</div>}
      {n.stopped && <div>Pooled account — attribution stops here</div>}
      {n.status && n.status !== "OPEN" && <div>Analyst decision: {statusWord(n.status)}</div>}
      {hint && <div className="text-muted">{hint}</div>}
    </div>
  );
}

export default function GraphView({ data, highlight, theme, showIdentity, selected = null, onSelect, onExpand,
  height = 520, expandHint = "Double-click to expand", interactive = true, control, onPartialView }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const cyRef = useRef<Core | null>(null);
  const [tip, setTip] = useState<{ x: number; y: number; html: ReactNode } | null>(null);
  const byId = useMemo(() => new Map(data.nodes.map((n) => [n.id, n])), [data]);
  const edgeById = useMemo(() => new Map(data.edges.map((e) => [`e:${e.id}`, e])), [data]);
  const handlers = useRef({ onSelect, onExpand, onPartialView });
  handlers.current = { onSelect, onExpand, onPartialView };
  const selectedRef = useRef(selected);
  selectedRef.current = selected;

  // build / rebuild
  useEffect(() => {
    if (!ref.current) return;
    const t = tokens();
    const cy = cytoscape({
      container: ref.current,
      elements: buildElements(data, showIdentity),
      wheelSensitivity: 0.25,
      minZoom: 0.15,
      maxZoom: 2.5,
      userPanningEnabled: interactive,
      userZoomingEnabled: interactive,
      autoungrabify: !interactive,
      boxSelectionEnabled: false,
      autounselectify: true,
      style: [
        { selector: "node", style: {
          "background-color": t.raised, "border-width": 1.5, "border-color": t.line, shape: "data(shape)" as any,
          width: "data(size)", height: "data(size)", label: "data(label)", "font-size": NODE_FONT, color: t.ink,
          "min-zoomed-font-size": 8, "text-valign": "bottom", "text-margin-y": 4, "text-wrap": "wrap",
          "text-max-width": "120px", "font-family": "system-ui, Segoe UI, sans-serif",
          "text-background-color": t.surface, "text-background-opacity": 0.85, "text-background-padding": "1px",
          "text-background-shape": "roundrectangle",
        } },
        { selector: "node.sev-HIGH", style: { "background-color": t.high, "border-color": t.high } },
        { selector: "node.sev-MEDIUM", style: { "background-color": t.medium, "border-color": t.medium } },
        { selector: "node.sev-LOW", style: { "background-color": t.low, "border-color": t.low } },
        { selector: "node.confirmed", style: { "border-style": "double", "border-width": 6, "border-color": t.ink } },
        { selector: "node.cleared", style: { "border-width": 3.5, "border-color": t.good } },
        { selector: "node.stopped", style: { "border-style": "dashed", "border-width": 3, "border-color": t.ink2 } },
        { selector: "node.focus", style: { "border-width": 4, "border-color": t.accent, "font-weight": "bold" } },
        { selector: "node.focus.confirmed", style: { "border-width": 6, "border-color": t.accent } },
        { selector: "node.aggregate", style: { "background-color": t.sunken, "border-style": "dashed", width: 70, height: 26,
          "text-valign": "center", "text-margin-y": 0, color: t.ink2 } },
        { selector: "node.selected", style: { "underlay-color": t.accent, "underlay-padding": 9, "underlay-opacity": 0.42,
          "underlay-shape": "ellipse", "font-weight": "bold", "z-index": 30 } as any },
        { selector: "edge", style: {
          width: "data(w)", "curve-style": "bezier", "target-arrow-shape": "triangle", "arrow-scale": 1,
          "line-color": t.edge, "target-arrow-color": t.edge, "font-size": EDGE_FONT, color: t.ink2,
          "min-zoomed-font-size": 8, "text-rotation": "autorotate", "text-background-color": t.surface,
          "text-background-opacity": 0.92, "text-background-padding": "2px", "font-family": "system-ui, Segoe UI, sans-serif",
        } },
        { selector: "edge.lbl, edge.hl, edge.seledge", style: { label: "data(label)" } },
        { selector: "edge.suspicious", style: { "line-color": t.high, "target-arrow-color": t.high, color: t.ink } },
        // other transactions differ by line style and arrowhead too, not by colour alone (§11)
        { selector: "edge.plain", style: { "line-style": "dotted", "target-arrow-fill": "hollow" } },
        { selector: "edge.traced", style: { "line-color": t.trace, "target-arrow-color": t.trace, "line-style": "solid",
          "target-arrow-shape": "triangle-backcurve", "arrow-scale": 1.15, color: t.ink } },
        // money moving back (circular flow) is drawn as an arc, so it never reads as forward flow
        { selector: "edge.back", style: { "curve-style": "unbundled-bezier", "control-point-distances": [-48] as any,
          "control-point-weights": [0.5] as any } },
        { selector: "edge.identity", style: { "line-color": t.ident, "line-style": "dashed", "line-dash-pattern": [5, 4],
          width: 1.5, "target-arrow-shape": "none", "curve-style": "straight", "font-size": 8.5, color: t.ident } },
        { selector: ".dim", style: { opacity: 0.2 } },
        { selector: "edge.hl", style: { width: 5, "z-index": 10 } },
        { selector: "node.hl", style: { "z-index": 10 } },
        { selector: "edge.seledge", style: { "z-index": 20, "underlay-color": t.accent, "underlay-padding": 3,
          "underlay-opacity": 0.3 } as any },
      ],
    });
    cyRef.current = cy;

    const box = () => ({ w: ref.current?.clientWidth ?? 600, h: ref.current?.clientHeight ?? 400 });
    // money transactions decide the layout; shared-attribute links are drawn but do not move anyone
    const layout = () => {
      const flow = cy.elements().not(".identity");
      try {
        flow.layout({ name: "dagre", rankDir: "LR", nodeSep: 40, rankSep: 110, edgeSep: 10, acyclicer: "greedy",
          animate: false, fit: false } as any).run();
      } catch {
        flow.layout({ name: "breadthfirst", directed: true, animate: false, fit: false } as any).run();
      }
      const per = Math.max(4, Math.floor(box().h / 70));
      const placed = wrapColumns(cy.nodes().map((n) => ({ id: n.id(), ...n.position() })), per, 100, 68);
      const at = new Map(placed.map((p) => [p.id, p]));
      cy.nodes().positions((n) => { const p = at.get(n.id())!; return { x: p.x, y: p.y }; });
      cy.edges().not(".identity").forEach((e) => {
        e.toggleClass("back", e.target().position("x") < e.source().position("x") - 5);
      });
    };
    // first view: whole graph if its labels stay readable, otherwise a readable zoom around the account that
    // matters most (focus, selection, highest score); "Fit" always shows everything
    const initialView = () => {
      cy.resize();
      cy.fit(undefined, 28);
      let partial = false;
      if (interactive && cy.zoom() < MIN_READABLE_ZOOM && cy.nodes().length > 1) {
        const anchor = cy.$id(selectedRef.current ?? "").nonempty() ? cy.$id(selectedRef.current!)
          : cy.nodes(".focus").nonempty() ? cy.nodes(".focus").first()
          : cy.nodes().max((n) => byId.get(n.id())?.score ?? 0).ele;
        cy.zoom(MIN_READABLE_ZOOM);
        cy.center(anchor);
        partial = true;
      } else if (cy.zoom() > MAX_INITIAL_ZOOM) {
        cy.zoom(MAX_INITIAL_ZOOM);
        cy.center();
      }
      handlers.current.onPartialView?.(partial);
    };
    layout();
    initialView();
    // the container may still be settling its size on first paint: set the first view again once it has
    let last = `${box().w}x${box().h}`;
    const raf = requestAnimationFrame(initialView);
    const ro = new ResizeObserver(() => {
      const now = `${box().w}x${box().h}`;
      if (now !== last) { last = now; initialView(); }
    });
    ro.observe(ref.current);
    if (control) control.current = {
      fitAll: () => { cy.fit(undefined, 24); handlers.current.onPartialView?.(false); },
      centre: (id) => {
        const n = cy.$id(id);
        if (!n.nonempty()) return;
        if (cy.zoom() < MIN_READABLE_ZOOM) cy.zoom(MIN_READABLE_ZOOM);
        cy.center(n);
      },
    };
    cy.one("destroy", () => { cancelAnimationFrame(raf); ro.disconnect(); });
    cy.on("tap", (e) => { if (e.target === cy) handlers.current.onSelect?.(null); });
    cy.on("tap", "node", (e) => handlers.current.onSelect?.(e.target.id()));
    cy.on("dbltap", "node", (e) => { if (!e.target.hasClass("aggregate")) handlers.current.onExpand?.(e.target.id()); });
    cy.on("mouseover", "node", (e) => {
      const n = byId.get(e.target.id());
      if (!n) return;
      const p = e.renderedPosition;
      setTip({ x: p.x, y: p.y, html: <NodeInfo n={n} hint={n.aggregate ? undefined : `Click to select · ${expandHint.toLowerCase()}`} /> });
    });
    cy.on("mouseover", "edge", (e) => {
      const ed = edgeById.get(e.target.id());
      const p = e.renderedPosition ?? e.target.midpoint();
      if (!ed) { setTip({ x: p.x, y: p.y, html: <div>Shared {e.target.data("label")} — the same attribute on both accounts, not a payment</div> }); return; }
      setTip({ x: p.x, y: p.y, html: (
        <div className="space-y-0.5">
          <div className="font-mono [overflow-wrap:anywhere]">{ed.source} → {ed.target}</div>
          {data.mode === "flow" ? <div>{money(ed.amount)} traced (FIFO attribution)</div> :
            <div>{money(ed.total)} in {ed.count} transaction{ed.count === 1 ? "" : "s"}{ed.suspicious ? " · suspicious" : ""}</div>}
          <div>{dateTime(ed.first_ts)}{ed.last_ts !== ed.first_ts ? ` – ${dateTime(ed.last_ts)}` : ""} IST</div>
          <div className="text-muted">{ed.txn_ids.slice(0, 4).join(", ")}{ed.txn_ids.length > 4 ? " …" : ""}</div>
        </div>) });
    });
    cy.on("mouseout", () => setTip(null));
    cy.on("pan zoom", () => setTip(null));
    return () => { cy.destroy(); cyRef.current = null; if (control) control.current = null; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, theme, showIdentity, interactive]);

  // evidence highlight and selection, without relayout
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    cy.elements().removeClass("dim hl selected seledge");
    if (highlight && (highlight.nodes.size || highlight.txnIds.size)) {
      const hlEdges = cy.edges().filter((e) => {
        const ids: string = e.data("txn") ?? "";
        return ids.split("|").some((t) => highlight.txnIds.has(t));
      });
      const hlNodes = cy.nodes().filter((n) => highlight.nodes.has(n.id()));
      const keep = hlEdges.union(hlNodes).union(hlEdges.connectedNodes());
      cy.elements().not(keep).addClass("dim");
      keep.addClass("hl");
    }
    if (selected) {
      const n = cy.$id(selected);
      n.addClass("selected");
      n.connectedEdges().not(".identity").addClass("seledge");
    }
  }, [highlight, selected, data, theme, showIdentity, interactive]);

  return (
    <div className="relative" style={{ height }}>
      <div ref={ref} className={`absolute inset-0 ${interactive ? "" : "pointer-events-none"}`} style={interactive ? { touchAction: "none" } : undefined}
        role="img" aria-label={`Transaction graph: ${data.nodes.length} accounts, ${data.edges.length} links. Use “Find account in graph” to select one.`} />
      {tip && interactive && (
        <div className="pointer-events-none absolute z-20 max-w-[280px] rounded-md border border-line bg-raised px-2.5 py-1.5 text-xs text-ink shadow-card"
          style={{ left: Math.max(4, Math.min(tip.x + 14, (ref.current?.clientWidth ?? 600) - 290)),
            top: Math.min(tip.y + 14, Math.max(4, (ref.current?.clientHeight ?? 400) - 120)) }}>{tip.html}</div>
      )}
    </div>
  );
}

function useNarrow(): boolean {
  const q = "(max-width: 639px)";
  const [narrow, setNarrow] = useState(() => typeof window !== "undefined" && window.matchMedia(q).matches);
  useEffect(() => {
    const m = window.matchMedia(q);
    const on = () => setNarrow(m.matches);
    m.addEventListener("change", on);
    return () => m.removeEventListener("change", on);
  }, []);
  return narrow;
}

interface FrameProps {
  data: GraphData;
  highlight: Highlight | null;
  theme: string;
  showIdentity: boolean;
  selected: string | null;
  onSelect: (id: string | null) => void;
  onExpand?: (id: string) => void;
  expandHint?: string;
  height?: number;
  title: string;
  /** links or actions for the selected account (e.g. "Investigate") */
  selectedActions?: (id: string) => ReactNode;
  /** page-specific notes under the graph (accounting, bounded view) */
  notes?: ReactNode;
  legendHighlight?: boolean;
}

/** A graph with its toolbar (find account, fit, full screen), selection details and legend. On a phone the
 *  inline graph is a still preview — the page scrolls past it — and opens a full-screen explorer. */
export function GraphFrame(p: FrameProps) {
  const narrow = useNarrow();
  const [full, setFull] = useState(false);
  const inline = useRef<GraphControl | null>(null);
  const big = useRef<GraphControl | null>(null);
  const [partial, setPartial] = useState(false);
  const closeRef = useRef<HTMLButtonElement>(null);
  const openRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!full) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    closeRef.current?.focus();
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") setFull(false); };
    window.addEventListener("keydown", esc);
    return () => { document.body.style.overflow = prev; window.removeEventListener("keydown", esc); openRef.current?.focus(); };
  }, [full]);

  const sel = p.selected ? p.data.nodes.find((n) => n.id === p.selected) ?? null : null;
  const ordered = useMemo(() => [...p.data.nodes].filter((n) => !n.aggregate).sort((a, b) =>
    Number(!!b.focus) - Number(!!a.focus) || (b.score ?? 0) - (a.score ?? 0) || a.id.localeCompare(b.id)), [p.data]);
  const hasAggregate = p.data.nodes.some((n) => n.aggregate);
  const hasFocus = p.data.nodes.some((n) => n.focus);

  const toolbar = (ctl: { current: GraphControl | null }, isFull: boolean) => (
    <div className="flex flex-wrap items-center gap-2 text-xs">
      <label className="flex min-w-0 items-center gap-1.5 text-ink2">
        <span className="shrink-0">Find account in graph</span>
        <select className="input min-w-0 max-w-[14rem] py-1" value={p.selected ?? ""}
          onChange={(e) => { const v = e.target.value || null; p.onSelect(v); if (v) ctl.current?.centre(v); }}>
          <option value="">—</option>
          {ordered.map((n) => <option key={n.id} value={n.id}>{n.id}{n.severity ? ` · ${sevWord(n.severity)} ${n.score}` : ""}{n.focus ? " (this account)" : ""}</option>)}
        </select>
      </label>
      <button type="button" className="btn px-2 py-1 text-xs" onClick={() => ctl.current?.fitAll()} title="Show the whole graph">
        <Scan size={13} /> Fit all</button>
      {isFull ? (
        <button ref={closeRef} type="button" className="btn px-2 py-1 text-xs" onClick={() => setFull(false)}>
          <Minimize2 size={13} /> Close</button>
      ) : (
        <button ref={openRef} type="button" className="btn px-2 py-1 text-xs" onClick={() => setFull(true)}>
          <Maximize2 size={13} /> Full screen</button>
      )}
    </div>
  );

  const details = sel && (
    <div className="flex flex-wrap items-start justify-between gap-2 rounded-md border border-accent/50 bg-accent-soft/40 px-3 py-2 text-xs" aria-live="polite">
      <NodeInfo n={sel} />
      <div className="flex items-center gap-3">
        {p.selectedActions?.(sel.id)}
        <button type="button" className="link py-1" onClick={() => p.onSelect(null)}>Clear selection</button>
      </div>
    </div>
  );
  const legend = <GraphLegend mode={p.data.mode} hasFocus={hasFocus} hasAggregate={hasAggregate}
    showIdentity={p.showIdentity && p.data.mode !== "flow"} hasHighlight={!!p.legendHighlight} />;
  const hint = p.data.mode === "flow" ? "Click an account to select it · double-click to trace from it"
    : `Click an account to select it · ${(p.expandHint ?? "double-click to expand its neighbourhood").toLowerCase()} · scroll or pinch to zoom, drag to move`;

  return (
    <>
      <div className="border-b border-line px-4 py-2">{toolbar(inline, false)}</div>
      {narrow ? (
        <div className="relative">
          <GraphView data={p.data} highlight={p.highlight} theme={p.theme} showIdentity={p.showIdentity}
            selected={p.selected} height={260} interactive={false} />
          <button type="button" onClick={() => setFull(true)}
            className="absolute inset-x-0 bottom-3 mx-auto w-max rounded-full border border-accent bg-raised px-4 py-2 text-sm font-medium text-accent-ink shadow-card">
            <Maximize2 size={14} className="mr-1.5 inline" />Open graph to explore</button>
        </div>
      ) : (
        <GraphView data={p.data} highlight={p.highlight} theme={p.theme} showIdentity={p.showIdentity}
          selected={p.selected} onSelect={p.onSelect} onExpand={p.onExpand} expandHint={p.expandHint}
          height={p.height ?? 520} control={inline} onPartialView={setPartial} />
      )}
      <div className="space-y-2 border-t border-line px-4 py-2">
        {details}
        {partial && !narrow && (
          <div className="text-xs text-ink2">Zoomed in so labels are readable — <button type="button" className="link" onClick={() => inline.current?.fitAll()}>Fit all</button> shows every account (labels hide when they would be too small to read).</div>
        )}
        {legend}
        <div className="text-xs text-muted">{hint}</div>
        {p.notes}
      </div>
      {full && (
        <div className="fixed inset-0 z-[60] flex flex-col bg-page" role="dialog" aria-modal="true" aria-label={p.title}>
          <div className="flex items-center justify-between gap-2 border-b border-line bg-surface px-4 py-2">
            <h2 className="card-t truncate">{p.title}</h2>
            <button type="button" className="btn btn-ghost px-2" onClick={() => setFull(false)} aria-label="Close full screen graph"><X size={16} /></button>
          </div>
          <div className="border-b border-line bg-surface px-4 py-2">{toolbar(big, true)}</div>
          <div className="min-h-0 flex-1">
            <GraphView data={p.data} highlight={p.highlight} theme={p.theme} showIdentity={p.showIdentity}
              selected={p.selected} onSelect={p.onSelect} onExpand={p.onExpand} expandHint={p.expandHint}
              height="100%" control={big} />
          </div>
          <div className="max-h-[40vh] space-y-2 overflow-auto border-t border-line bg-surface px-4 py-2">
            {details}
            {legend}
            <div className="text-xs text-muted">{narrow ? "Tap an account for details · pinch to zoom, drag to move" : hint}</div>
          </div>
        </div>
      )}
    </>
  );
}

function Swatch({ children }: { children: ReactNode }) {
  return <svg width="26" height="14" viewBox="0 0 26 14" aria-hidden className="shrink-0 overflow-visible">{children}</svg>;
}
const Item = ({ sw, children }: { sw: ReactNode; children: ReactNode }) =>
  <span className="flex items-center gap-1.5">{sw}{children}</span>;

/** Every visual encoding the graph uses, in words. */
export function GraphLegend({ mode, hasFocus = true, hasAggregate = false, showIdentity = true, hasHighlight = false }: {
  mode: string; hasFocus?: boolean; hasAggregate?: boolean; showIdentity?: boolean; hasHighlight?: boolean;
}) {
  const v = (n: string) => `rgb(var(--${n}))`;
  const dot = (fill: string, stroke = fill, extra = {}) => <Swatch><circle cx="13" cy="7" r="5.5" fill={fill} stroke={stroke} strokeWidth="1.5" {...extra} /></Swatch>;
  const line = (color: string, dash?: string, arrow: "filled" | "hollow" | "none" = "filled") => (
    <Swatch>
      <line x1="1" y1="7" x2={arrow === "none" ? 25 : 19} y2="7" stroke={color} strokeWidth="2.2" strokeDasharray={dash} />
      {arrow !== "none" && <path d="M18 3 L25 7 L18 11 Z" fill={arrow === "filled" ? color : v("surface")} stroke={color} strokeWidth="1.3" />}
    </Swatch>
  );
  const traced = mode === "flow";
  return (
    <div className="space-y-1 text-xs text-ink2" aria-label="Graph legend">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
        <span className="label">Accounts</span>
        <Item sw={dot(v("high"))}>High</Item>
        <Item sw={dot(v("medium"))}>Medium</Item>
        <Item sw={dot(v("low"))}>Low</Item>
        <Item sw={dot(v("raised"), v("line-strong"))}>Not flagged</Item>
        <span>{traced ? "₹ under an account = money traced through it" : "number = score, with severity in words"}</span>
        <span>◆ likely origin · ● relay, hub, collector or distributor · ■ sink (cash-out) · ⬢ pooled</span>
        {hasAggregate && <Item sw={<Swatch><rect x="2" y="2" width="22" height="10" rx="3" fill={v("sunken")} stroke={v("ink2")} strokeDasharray="3 2" /></Swatch>}>“+N accounts” = smaller amounts grouped</Item>}
      </div>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
        <span className="label">Markers</span>
        {hasFocus && <Item sw={dot(v("raised"), v("accent"), { strokeWidth: 3 })}>account under investigation</Item>}
        <Item sw={<Swatch><circle cx="13" cy="7" r="7" fill={v("accent")} opacity="0.4" /><circle cx="13" cy="7" r="4" fill={v("raised")} stroke={v("line-strong")} /></Swatch>}>halo = selected</Item>
        <Item sw={<Swatch><circle cx="13" cy="7" r="5.5" fill={v("raised")} stroke={v("ink")} strokeWidth="1" /><circle cx="13" cy="7" r="3.5" fill="none" stroke={v("ink")} strokeWidth="1" /></Swatch>}>double ring = confirmed</Item>
        <Item sw={dot(v("raised"), v("good"), { strokeWidth: 2.5 })}>green ring = cleared</Item>
        {traced && <Item sw={dot(v("raised"), v("ink2"), { strokeWidth: 2, strokeDasharray: "2 2" })}>dashed ring = trace stops (pooled account)</Item>}
        {hasHighlight && <span>faded = not part of the highlighted evidence</span>}
      </div>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
        <span className="label">Links</span>
        {traced ? (
          <Item sw={line(v("trace"))}>money traced from account to account (FIFO attribution)</Item>
        ) : (
          <>
            <Item sw={line(v("high"))}>suspicious transactions (solid)</Item>
            <Item sw={line(v("edge"), "2 3", "hollow")}>other transactions (dotted)</Item>
            {showIdentity && <Item sw={line(v("ident"), "5 3", "none")}>shared device / IP / KYC (dashed, not a payment)</Item>}
          </>
        )}
        <span>arrow = direction money moved · arc = money flowing back</span>
      </div>
    </div>
  );
}
