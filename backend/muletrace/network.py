"""Bounded graph views for the UI: k-hop transaction network and traced flow (ARCHITECTURE §10)."""
from __future__ import annotations

from collections import defaultdict
from fractions import Fraction

from .explain import indicator_view
from .flow import trace

TRACE_LABEL = "computed flow links (FIFO attribution)"


def _node(an, a: str, dispositions: dict, focus: str, hop: int) -> dict:
    r = an.results[a]
    acc = an.ds.accounts[a]
    return {"id": a, "score": r.score, "severity": r.severity, "flagged": r.flagged,
            "role": an.role(a), "status": dispositions.get(a, {}).get("status", "OPEN"),
            "pooled": acc.pooled, "focus": a == focus, "hop": hop,
            "indicator": indicator_view(a, an)["status"]}


def suspicious_txns(an) -> set[int]:
    s: set[int] = set()
    for c in an.cases.cases:
        if any(an.results[m].flagged for m in c.members):
            s.update(c.edges)
    for r in an.results.values():
        for sig in r.signals.values():
            if sig.qualifies and sig.kind != "IDENTITY":
                s.update(sig.txns)
    return s


def network(an, focus: str, hops: int, min_amount: int, suspicious_only: bool, dispositions: dict) -> dict:
    ds = an.ds
    txns = ds.txns
    cfg = an.cfg
    hops = max(1, min(3, hops))
    susp = an.suspicious_cache if hasattr(an, "suspicious_cache") else suspicious_txns(an)
    an.suspicious_cache = susp
    case_members = {m for cid in an.cases.case_of.get(focus, []) for m in an.cases.case(cid).members}

    def keep(t: int) -> bool:
        if txns[t].amount < min_amount:
            return False
        return not suspicious_only or t in susp

    dist = {focus: 0}
    frontier = [focus]
    for h in range(1, hops + 1):
        nxt = []
        for a in frontier:
            acc = ds.accounts[a]
            for t in acc.in_txns + acc.out_txns:
                if not keep(t):
                    continue
                b = txns[t].receiver if txns[t].sender == a else txns[t].sender
                if b not in dist:
                    dist[b] = h
                    nxt.append(b)
        frontier = sorted(nxt)

    volume: dict[str, int] = defaultdict(int)
    for a in dist:
        acc = ds.accounts[a]
        volume[a] = acc.in_total + acc.out_total

    def rank(a: str):
        r = an.results[a]
        return (a != focus, dist[a], not (a in case_members), not r.flagged, -volume[a], a)

    ordered = sorted(dist, key=rank)
    shown = set(ordered[:cfg.network_max_nodes])
    hidden = len(ordered) - len(shown)

    edges: dict[tuple[str, str], dict] = {}
    for a in sorted(shown):
        for t in ds.accounts[a].out_txns:
            tx = txns[t]
            if tx.receiver not in shown or not keep(t):
                continue
            e = edges.setdefault((tx.sender, tx.receiver), {
                "id": f"{tx.sender}->{tx.receiver}", "source": tx.sender, "target": tx.receiver,
                "count": 0, "total": 0, "first_ts": tx.ts, "last_ts": tx.ts, "txn_ids": [], "suspicious": False})
            e["count"] += 1
            e["total"] += tx.amount
            e["first_ts"] = min(e["first_ts"], tx.ts)
            e["last_ts"] = max(e["last_ts"], tx.ts)
            if len(e["txn_ids"]) < 50:
                e["txn_ids"].append(tx.txn_id)
            e["suspicious"] = e["suspicious"] or t in susp

    identity_edges = []
    for cl in an.identity.clusters:
        members = [m for m in cl.accounts if m in shown]
        for att in cl.metrics["attributes"]:
            ms = [m for m in att["members"] if m in shown]
            for i in range(len(ms)):
                for j in range(i + 1, len(ms)):
                    identity_edges.append({"source": ms[i], "target": ms[j], "attr": att["type"],
                                           "value": att["value"]})
        del members
    return {
        "mode": "network",
        "focus": focus,
        "nodes": [_node(an, a, dispositions, focus, dist[a]) for a in sorted(shown, key=rank)],
        "edges": sorted(edges.values(), key=lambda e: (e["first_ts"], e["id"])),
        "identity_edges": identity_edges[:300],
        "hidden_count": hidden,
        "truncated": hidden > 0,
    }


def _start_txns(an, account: str, direction: str) -> list[int]:
    acc = an.ds.accounts[account]
    pool = acc.out_txns if direction == "fwd" else acc.in_txns
    r = an.results[account]
    preferred = {t for s in r.signals.values() if s.qualifies for t in s.txns}
    case_edges = {t for cid in an.cases.case_of.get(account, []) for t in an.cases.case(cid).edges}
    txns = an.ds.txns
    ranked = sorted(pool, key=lambda t: (t not in preferred, t not in case_edges, -txns[t].amount, t))
    chosen = [t for t in ranked if t in preferred or t in case_edges][:25]
    return chosen or ranked[:10]


def trace_view(an, account: str, direction: str, dispositions: dict) -> dict:
    cfg = an.cfg
    txns = an.ds.txns
    if an.engine != "flow":
        view = network(an, account, 2, 0, True, dispositions)
        view.update(mode="transactions", direction=direction,
                    label="transactions (not traced) — flow tracing unavailable in fallback mode")
        return view
    starts = _start_txns(an, account, direction)
    tr = trace(an.ds, an.fg, starts, direction, cfg.trace_max_hops)
    involved = defaultdict(Fraction)
    for (s, r), amt in tr.edge_amounts.items():
        involved[s] += amt
        involved[r] += amt
    involved[account] += Fraction(10 ** 18)        # always keep the start account
    ranked = sorted(involved, key=lambda a: (-involved[a], a))
    keep = set(ranked[:cfg.trace_max_nodes - 1])
    dropped = [a for a in ranked if a not in keep]
    AGG = "__others__"

    def nid(a: str) -> str:
        return a if a in keep else AGG

    edges: dict[tuple[str, str], dict] = {}
    for (s, r), amt in sorted(tr.edge_amounts.items()):
        key = (nid(s), nid(r))
        if key[0] == key[1]:
            continue
        e = edges.setdefault(key, {"id": f"{key[0]}=>{key[1]}", "source": key[0], "target": key[1],
                                   "amount": Fraction(0), "txn_ids": [], "first_ts": None, "last_ts": None})
        e["amount"] += amt
        for t in sorted(tr.edge_txns[(s, r)]):
            if len(e["txn_ids"]) < 30:
                e["txn_ids"].append(txns[t].txn_id)
            e["first_ts"] = txns[t].ts if e["first_ts"] is None else min(e["first_ts"], txns[t].ts)
            e["last_ts"] = txns[t].ts if e["last_ts"] is None else max(e["last_ts"], txns[t].ts)
    nodes = []
    for a in sorted(keep, key=lambda a: (tr.hops.get(a, 0), a)):
        n = _node(an, a, dispositions, account, tr.hops.get(a, 0) if a != account else 0)
        n.update(traced=_money(tr.node_amount.get(a, Fraction(0))),
                 retained=_money(tr.retained.get(a, Fraction(0))),
                 stopped=a in tr.stopped,
                 dwell_seconds=sorted(tr.node_dwell.get(a, []))[len(tr.node_dwell.get(a, [])) // 2]
                 if tr.node_dwell.get(a) else None)
        nodes.append(n)
    if dropped:
        nodes.append({"id": AGG, "aggregate": True, "count": len(dropped),
                      "traced": _money(sum((tr.node_amount.get(a, Fraction(0)) for a in dropped), Fraction(0))),
                      "label": f"+{len(dropped)} accounts"})
    for e in edges.values():
        e["amount"] = _money(e["amount"])
    total = tr.total_start()
    return {
        "mode": "flow", "label": TRACE_LABEL, "direction": direction, "focus": account,
        "nodes": nodes, "edges": sorted(edges.values(), key=lambda e: (e["first_ts"] or 0, e["id"])),
        "start_txn_ids": [txns[t].txn_id for t in starts],
        "accounting": {
            "start": _money(total),
            "retained": _money(sum(tr.retained.values(), Fraction(0))),
            "stopped_at_pooled": _money(sum(tr.stopped.values(), Fraction(0))),
            "beyond_hop_limit": _money(tr.truncated),
            "exact": tr.accounted() == total,
        },
        "aggregated_accounts": len(dropped),
        "truncated": bool(dropped),
    }


def _money(x: Fraction) -> int:
    """Round a traced Fraction to minor units for display (exact value kept internally)."""
    return int(round(x))
