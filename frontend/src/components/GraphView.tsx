import { useEffect, useMemo, useRef, useState } from "react";
import cytoscape, { type Core, type ElementDefinition } from "cytoscape";
import dagre from "cytoscape-dagre";
import { Maximize2 } from "lucide-react";
import type { GraphData } from "../api";
import { clock, dateTime, duration, money, moneyShort, ROLE_LABEL } from "../format";

cytoscape.use(dagre);

export interface Highlight { nodes: Set<string>; txnIds: Set<string> }

interface Props {
  data: GraphData;
  highlight: Highlight | null;
  theme: string;
  showIdentity: boolean;
  onSelect?: (id: string) => void;
  onExpand?: (id: string) => void;
  height?: number;
  expandHint?: string;
}

const ROLE_SHAPE: Record<string, string> = {
  ORIGIN: "diamond", SINK: "round-rectangle", POOLED: "hexagon", HUB: "ellipse", COLLECTOR: "ellipse",
  DISTRIBUTOR: "ellipse", RELAY: "ellipse", CLUSTER_MEMBER: "ellipse", COUNTERPARTY: "ellipse",
};

function tokens() {
  const cs = getComputedStyle(document.documentElement);
  const c = (n: string, a = 1) => `rgba(${cs.getPropertyValue(`--${n}`).trim().split(/\s+/).join(",")},${a})`;
  return {
    ink: c("ink"), ink2: c("ink2"), muted: c("muted"), surface: c("surface"), raised: c("raised"),
    line: c("line-strong"), edge: c("edge"), high: c("high"), medium: c("medium"), low: c("low"),
    good: c("good"), accent: c("accent"), trace: c("trace"), ident: c("ident"), sunken: c("sunken"),
  };
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
    const label = n.aggregate ? n.label! : traced && n.traced != null && !n.focus ? `${n.id}\n${moneyShort(n.traced)}` :
      n.score ? `${n.id}\n${n.score}` : n.id;
    els.push({ data: { id: n.id, label, shape: n.aggregate ? "round-rectangle" : ROLE_SHAPE[n.role ?? ""] ?? "ellipse",
      size: n.focus ? 40 : n.role === "HUB" ? 34 : 28 }, classes: cls });
  }
  const amounts = data.edges.map((e) => (traced ? e.amount : e.total) ?? 0);
  const maxA = Math.max(1, ...amounts);
  for (const e of data.edges) {
    const amt = (traced ? e.amount : e.total) ?? 0;
    const w = 1.2 + 4.5 * (Math.log10(1 + amt / 100) / Math.log10(1 + maxA / 100));
    const label = traced ? `${moneyShort(amt)} traced` :
      `${moneyShort(amt)}${(e.count ?? 1) > 1 ? ` ×${e.count}` : ""} · ${clock(e.first_ts)}`;
    els.push({ data: { id: `e:${e.id}`, source: e.source, target: e.target, label, w, txn: e.txn_ids.join("|") },
      classes: traced ? "traced" : e.suspicious ? "suspicious" : "plain" });
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

export default function GraphView({ data, highlight, theme, showIdentity, onSelect, onExpand, height = 520,
  expandHint = "Double-click to expand" }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const cyRef = useRef<Core | null>(null);
  const [tip, setTip] = useState<{ x: number; y: number; html: React.ReactNode } | null>(null);
  const byId = useMemo(() => new Map(data.nodes.map((n) => [n.id, n])), [data]);
  const edgeById = useMemo(() => new Map(data.edges.map((e) => [`e:${e.id}`, e])), [data]);

  // build / rebuild
  useEffect(() => {
    if (!ref.current) return;
    const t = tokens();
    const cy = cytoscape({
      container: ref.current,
      elements: buildElements(data, showIdentity),
      wheelSensitivity: 0.25,
      minZoom: 0.2,
      maxZoom: 2.5,
      style: [
        { selector: "node", style: {
          "background-color": t.raised, "border-width": 1.5, "border-color": t.line, shape: "data(shape)" as any,
          width: "data(size)", height: "data(size)", label: "data(label)", "font-size": 10, color: t.ink,
          "text-valign": "bottom", "text-margin-y": 4, "text-wrap": "wrap", "text-max-width": "110px",
          "font-family": "system-ui, Segoe UI, sans-serif", "text-background-color": t.surface,
          "text-background-opacity": 0.85, "text-background-padding": "1px", "text-background-shape": "roundrectangle",
        } },
        { selector: "node.sev-HIGH", style: { "background-color": t.high, "border-color": t.high } },
        { selector: "node.sev-MEDIUM", style: { "background-color": t.medium, "border-color": t.medium } },
        { selector: "node.sev-LOW", style: { "background-color": t.low, "border-color": t.low } },
        { selector: "node.focus", style: { "border-width": 4, "border-color": t.accent, "font-weight": "bold" } },
        { selector: "node.confirmed", style: { "border-style": "double", "border-width": 6, "border-color": t.ink } },
        { selector: "node.cleared", style: { "background-opacity": 0.35, "border-color": t.good, "border-width": 3 } },
        { selector: "node.stopped", style: { "border-style": "dashed", "border-width": 3, "border-color": t.ink2 } },
        { selector: "node.aggregate", style: { "background-color": t.sunken, "border-style": "dashed", width: 64, height: 26,
          "text-valign": "center", "text-margin-y": 0, color: t.ink2 } },
        { selector: "edge", style: {
          width: "data(w)", "curve-style": "bezier", "target-arrow-shape": "triangle", "arrow-scale": 0.9,
          "line-color": t.edge, "target-arrow-color": t.edge, label: "data(label)", "font-size": 8.5, color: t.ink2,
          "text-rotation": "autorotate", "text-background-color": t.surface, "text-background-opacity": 0.9,
          "text-background-padding": "1px", "font-family": "system-ui, Segoe UI, sans-serif",
        } },
        { selector: "edge.suspicious", style: { "line-color": t.high, "target-arrow-color": t.high, color: t.ink } },
        // other transactions differ by line style and arrowhead too, not by colour alone (§11)
        { selector: "edge.plain", style: { "line-style": "dotted", "target-arrow-fill": "hollow" } },
        { selector: "edge.traced", style: { "line-color": t.trace, "target-arrow-color": t.trace, "line-style": "solid",
          "target-arrow-shape": "triangle-backcurve", "arrow-scale": 1.1, color: t.ink } },
        { selector: "edge.identity", style: { "line-color": t.ident, "line-style": "dashed", "line-dash-pattern": [5, 4],
          width: 1.5, "target-arrow-shape": "none", "curve-style": "straight", "font-size": 8, color: t.ident } },
        { selector: ".dim", style: { opacity: 0.14 } },
        { selector: "edge.hl", style: { width: 5, "z-index": 10 } },
        { selector: "node.hl", style: { "z-index": 10 } },
      ],
    });
    cyRef.current = cy;
    const run = () => {
      try {
        cy.layout({ name: "dagre", rankDir: "LR", nodeSep: 22, rankSep: 95, edgeSep: 8, animate: false, fit: true, padding: 24 } as any).run();
      } catch {
        cy.layout({ name: "breadthfirst", directed: true, padding: 24 }).run();
      }
    };
    run();
    // the container may still be settling its size on first paint: refit once it has, and on resize
    const refit = () => { cy.resize(); cy.fit(undefined, 28); };
    const raf = requestAnimationFrame(refit);
    const ro = new ResizeObserver(() => refit());
    ro.observe(ref.current);
    cy.one("destroy", () => { cancelAnimationFrame(raf); ro.disconnect(); });
    cy.on("tap", "node", (e) => onSelect?.(e.target.id()));
    cy.on("dbltap", "node", (e) => { if (!e.target.hasClass("aggregate")) onExpand?.(e.target.id()); });
    cy.on("mouseover", "node", (e) => {
      const n = byId.get(e.target.id());
      if (!n) return;
      const p = e.renderedPosition;
      setTip({ x: p.x, y: p.y, html: n.aggregate ? <div>{n.label} · {moneyShort(n.traced)} traced</div> : (
        <div className="space-y-0.5">
          <div className="font-mono font-semibold">{n.id}</div>
          <div>{n.severity ? `${n.severity} · score ${n.score}` : "Not flagged"}{n.role ? ` · ${ROLE_LABEL[n.role] ?? n.role}` : ""}</div>
          {n.traced != null && <div>Traced through: {money(n.traced)}{n.retained ? ` · kept ${money(n.retained)}` : ""}</div>}
          {n.dwell_seconds != null && <div>Median dwell: {duration(n.dwell_seconds)}</div>}
          {n.stopped && <div>Pooled account — attribution stops here</div>}
          {n.status && n.status !== "OPEN" && <div>Analyst: {n.status.toLowerCase()}</div>}
          <div className="text-muted">{expandHint}</div>
        </div>) });
    });
    cy.on("mouseover", "edge", (e) => {
      const ed = edgeById.get(e.target.id());
      const p = e.renderedPosition ?? e.target.midpoint();
      if (!ed) { setTip({ x: p.x, y: p.y, html: <div>Shared {e.target.data("label")}</div> }); return; }
      setTip({ x: p.x, y: p.y, html: (
        <div className="space-y-0.5">
          <div className="font-mono">{ed.source} → {ed.target}</div>
          {data.mode === "flow" ? <div>{money(ed.amount)} traced (FIFO attribution)</div> :
            <div>{money(ed.total)} in {ed.count} transaction{ed.count === 1 ? "" : "s"}</div>}
          <div>{dateTime(ed.first_ts)}{ed.last_ts !== ed.first_ts ? ` – ${dateTime(ed.last_ts)}` : ""}</div>
          <div className="text-muted">{ed.txn_ids.slice(0, 4).join(", ")}{ed.txn_ids.length > 4 ? " …" : ""}</div>
        </div>) });
    });
    cy.on("mouseout", () => setTip(null));
    cy.on("pan zoom", () => setTip(null));
    return () => { cy.destroy(); cyRef.current = null; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, theme, showIdentity]);

  // highlight without relayout
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    cy.elements().removeClass("dim hl");
    if (!highlight || (highlight.nodes.size === 0 && highlight.txnIds.size === 0)) return;
    const hlEdges = cy.edges().filter((e) => {
      const ids: string = e.data("txn") ?? "";
      return ids.split("|").some((t) => highlight.txnIds.has(t));
    });
    const hlNodes = cy.nodes().filter((n) => highlight.nodes.has(n.id()));
    const keep = hlEdges.union(hlNodes).union(hlEdges.connectedNodes());
    cy.elements().not(keep).addClass("dim");
    keep.addClass("hl");
  }, [highlight, data, theme, showIdentity]);

  return (
    <div className="relative" style={{ height }}>
      <div ref={ref} className="absolute inset-0" aria-label="Transaction network graph" role="img" />
      <button className="btn btn-ghost absolute right-2 top-2 px-2 py-1 text-xs" onClick={() => cyRef.current?.fit(undefined, 24)}
        title="Fit graph to view"><Maximize2 size={13} /> Fit</button>
      {tip && (
        <div className="pointer-events-none absolute z-20 max-w-[280px] rounded-md border border-line bg-raised px-2.5 py-1.5 text-xs text-ink shadow-card"
          style={{ left: Math.min(tip.x + 14, (ref.current?.clientWidth ?? 600) - 290), top: tip.y + 14 }}>{tip.html}</div>
      )}
    </div>
  );
}

export function GraphLegend({ mode }: { mode: string }) {
  const sw = (cls: string) => <span className={`inline-block h-2.5 w-2.5 rounded-full ${cls}`} />;
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-2xs text-ink2">
      <span className="flex items-center gap-1">{sw("bg-high")} High</span>
      <span className="flex items-center gap-1">{sw("bg-medium")} Medium</span>
      <span className="flex items-center gap-1">{sw("bg-low")} Low</span>
      <span className="flex items-center gap-1">{sw("bg-raised border border-line-strong")} Not flagged</span>
      <span>◆ origin · ● relay/hub · ■ sink · ⬢ pooled</span>
      {mode === "flow" ? (
        <span className="flex items-center gap-1"><span className="inline-block h-[3px] w-6 bg-trace" /> computed flow link (FIFO attribution)</span>
      ) : (
        <>
          <span className="flex items-center gap-1"><span className="inline-block h-[3px] w-6 bg-high" /> suspicious transactions (solid)</span>
          <span className="flex items-center gap-1"><span className="inline-block w-6 border-t-2 border-dotted" style={{ borderColor: "rgb(var(--edge))" }} /> other transactions (dotted)</span>
          <span className="flex items-center gap-1"><span className="inline-block w-6 border-t-2 border-dashed border-ident" /> shared attribute (dashed)</span>
        </>
      )}
      <span>double border = confirmed · faded = cleared</span>
    </div>
  );
}
