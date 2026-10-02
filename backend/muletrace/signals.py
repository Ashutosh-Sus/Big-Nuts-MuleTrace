"""Stage 6: raw FLOW and CIRCULARITY signals (ARCHITECTURE §6)."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from fractions import Fraction

from .flow import FlowGraph, better, conservation_tier, dwell_tier, weaker
from .profiles import Dataset

FLOW, CIRCULARITY, IDENTITY = "FLOW", "CIRCULARITY", "IDENTITY"


@dataclass
class Signal:
    account: str
    kind: str                      # RELAY | HUB | LAYERED_RECEIPT | ROUND_TRIP | IDENTITY
    family: str
    raw_tier: int | None
    metrics: dict = field(default_factory=dict)
    txns: list[int] = field(default_factory=list)
    episodes: list[str] = field(default_factory=list)
    finding: str | None = None
    final_tier: int | None = None
    qualifies: bool = False
    points: int = 0
    reason: str = ""
    notes: list[str] = field(default_factory=list)


@dataclass
class Finding:
    id: str
    pattern: str                   # ROUND_TRIP | IDENTITY_CLUSTER | HUB_BURST
    accounts: list[str]
    txns: list[int]
    metrics: dict
    tier: int | None
    path: list[str] = field(default_factory=list)


# ---------------------------------------------------------------- RELAY

def relay_signals(ds: Dataset, fg: FlowGraph) -> dict[str, Signal]:
    out: dict[str, Signal] = {}
    for acc in ds.sorted_accounts():
        eps = [fg.episodes[e] for e in fg.episodes_by_account.get(acc.id, []) if fg.episodes[e].tier is not None]
        if not eps:
            continue
        best = min(eps, key=lambda e: (e.tier, -max(e.forwarded, min(e.inflow, e.outflow)), e.start))
        out[acc.id] = Signal(
            account=acc.id, kind="RELAY", family=FLOW, raw_tier=best.tier,
            metrics=_episode_metrics(best),
            txns=sorted(set(best.in_txns) | set(best.out_txns)),
            episodes=[e.id for e in sorted(eps, key=lambda e: e.start)],
        )
    return out


def _episode_metrics(e) -> dict:
    return {
        "episode": e.id, "kind": e.kind, "inflow": e.inflow, "outflow": e.outflow,
        "forwarded": e.forwarded, "dwell_seconds": round(e.dwell), "conservation": e.c_traced,
        "traced_tier": e.traced_tier, "window_tier": e.window_tier, "window": e.window_detail,
        "start": e.start, "end": e.end, "senders_in": len(e.in_txns), "payouts": len(e.out_txns),
    }


# ---------------------------------------------------------------- HUB

def hub_signals(ds: Dataset, fg: FlowGraph, use_final: bool = False) -> dict[str, Signal]:
    cfg = ds.cfg
    txns = ds.txns
    out: dict[str, Signal] = {}
    for acc in ds.sorted_accounts():
        eps = [fg.episodes[e] for e in fg.episodes_by_account.get(acc.id, [])]
        eps = [e for e in eps if (e.final_tier if use_final else e.tier) in (0, 1)]
        if not eps:
            continue
        eps.sort(key=lambda e: (e.start, e.id))
        bursts: list[list] = []
        for e in eps:
            if bursts and e.start <= bursts[-1][0].start + cfg.hub_burst:
                bursts[-1].append(e)
            else:
                bursts.append([e])
        best = None
        for b in bursts:
            senders = sorted({txns[i].sender for e in b for i in e.in_txns})
            receivers = sorted({txns[o].receiver for e in b for o in e.out_txns})
            if len(senders) < cfg.hub_min_senders or len(receivers) < cfg.hub_min_receivers:
                continue
            inflow = sum(e.inflow for e in b)
            outflow = sum(e.outflow for e in b)
            matched = sum(e.forwarded if e.kind == "traced" else min(e.inflow, e.outflow) for e in b)
            dwell = sum(e.dwell * (e.forwarded if e.kind == "traced" else min(e.inflow, e.outflow)) for e in b)
            dwell = dwell / matched if matched else 0
            c = matched / max(inflow, outflow) if max(inflow, outflow) else 0
            tier = weaker(dwell_tier(cfg, dwell), conservation_tier(cfg, c))
            if tier is None or tier > 1:
                continue
            rank = (tier, -(len(senders) + len(receivers)), b[0].start)
            if best is None or rank < best[0]:
                best = (rank, b, senders, receivers, inflow, outflow, matched, dwell, c, tier)
        if best:
            _, b, senders, receivers, inflow, outflow, matched, dwell, c, tier = best
            out[acc.id] = Signal(
                account=acc.id, kind="HUB", family=FLOW, raw_tier=tier,
                metrics={"senders": senders, "receivers": receivers, "inflow": inflow, "outflow": outflow,
                         "matched": matched, "dwell_seconds": round(dwell), "conservation": round(c, 4),
                         "start": min(e.start for e in b), "end": max(e.end for e in b)},
                txns=sorted({x for e in b for x in e.in_txns + e.out_txns}),
                episodes=[e.id for e in b],
            )
    return out


# ---------------------------------------------------------------- LAYERED_RECEIPT

def receipt_signals(ds: Dataset, fg: FlowGraph, relay_tiers: dict[str, int | None]) -> dict[str, Signal]:
    """Account receives funds that passed through >= 2 upstream relays and keeps them."""
    cfg = ds.cfg
    txns = ds.txns
    is_relay = {a for a, t in relay_tiers.items() if t in (0, 1)}
    out: dict[str, Signal] = {}

    def upstream(t: int, seen: tuple[str, ...], depth: int) -> tuple[int, int, list[int]]:
        """Longest run of consecutive relays funding txn t: (relay count, earliest ts, txn path)."""
        sender = txns[t].sender
        if sender not in is_relay or sender in seen or depth > cfg.trace_max_hops:
            return 0, txns[t].ts, [t]
        cands = []
        for lid in fg.by_out.get(t, []):
            if not fg.structural(lid, cfg):
                continue
            n, earliest, path = upstream(fg.links[lid].in_txn, seen + (sender,), depth + 1)
            cands.append((n + 1, min(earliest, txns[t].ts), path + [t]))
        if not cands:
            return 1, txns[t].ts, [t]
        # most relays first; among equals the shortest span (latest start)
        return max(cands, key=lambda c: (c[0], c[1]))

    for acc in ds.sorted_accounts():
        receipts = []
        for t in acc.in_txns:
            tx = txns[t]
            if tx.amount < cfg.minor(cfg.min_link):
                continue
            forwarded = sum(fg.links[l].amount for l in fg.by_in.get(t, []) if fg.structural(l, cfg))
            if forwarded > cfg.sink_forward_max * tx.amount:
                continue
            n, earliest, path = upstream(t, (acc.id,), 0)
            if n < cfg.receipt_min_relays:
                continue
            span = tx.ts - earliest
            tier = 0 if span <= cfg.receipt_strong_span else (1 if span <= cfg.receipt_moderate_span else None)
            if tier is None:
                continue
            receipts.append((tier, t, n, span, path))
        if not receipts:
            continue
        receipts.sort(key=lambda r: (r[0], -txns[r[1]].amount, r[1]))
        tier, t, n, span, path = receipts[0]
        upstream_relays = sorted({txns[r[1]].sender for r in receipts})
        out[acc.id] = Signal(
            account=acc.id, kind="LAYERED_RECEIPT", family=FLOW, raw_tier=tier,
            metrics={"relays_upstream": n, "span_seconds": span, "amount": txns[t].amount,
                     "receipts": len(receipts), "upstream_senders": upstream_relays,
                     "total_received": sum(txns[r[1]].amount for r in receipts),
                     "consolidation": len(upstream_relays) >= 2,
                     "path_accounts": [txns[x].sender for x in path] + [acc.id]},
            txns=sorted({x for r in receipts for x in r[4]}),
        )
    return out


# ---------------------------------------------------------------- ROUND_TRIP

def round_trip_signals(ds: Dataset, fg: FlowGraph) -> tuple[dict[str, Signal], list[Finding], dict[str, list]]:
    cfg = ds.cfg
    txns = ds.txns
    cycles: dict[tuple[str, ...], dict] = {}
    reciprocal: dict[str, list] = defaultdict(list)

    for acc in ds.sorted_accounts():
        if acc.pooled:
            continue
        for o in acc.out_txns:
            if txns[o].amount < cfg.minor(cfg.min_episode):
                continue
            start_ts = txns[o].ts
            stack = [(o, Fraction(txns[o].amount), (acc.id,), (o,))]
            while stack:
                t, amt, path, tpath = stack.pop()
                r = txns[t].receiver
                if txns[t].ts - start_ts > cfg.rt_moderate_span:
                    continue
                if r == acc.id:
                    if len(path) >= 3:
                        _record_cycle(cfg, cycles, path, tpath, amt, txns[o].amount, txns[t].ts - start_ts)
                    elif len(path) == 2:
                        reciprocal[acc.id].append({"with": path[1], "txns": list(tpath),
                                                   "returned": int(amt)})
                    continue
                if r in path or ds.accounts[r].pooled or len(path) >= cfg.rt_max_hops:
                    continue
                links = [fg.links[l] for l in fg.by_in.get(t, []) if fg.structural(l, cfg)]
                links.sort(key=lambda l: (-l.amount, l.out_txn))
                for link in links[:cfg.rt_branch_cap]:
                    share = amt * Fraction(link.amount, txns[t].amount)
                    stack.append((link.out_txn, share, path + (r,), tpath + (link.out_txn,)))

    findings: list[Finding] = []
    signals: dict[str, Signal] = {}
    for k, key in enumerate(sorted(cycles, key=lambda c: (cycles[c]["tier"], -cycles[c]["ratio"], c)), start=1):
        c = cycles[key]
        fid = f"F-RT-{k:03d}"
        findings.append(Finding(fid, "ROUND_TRIP", list(key), c["txns"], {
            "returned": c["returned"], "sent": c["sent"], "ratio": round(c["ratio"], 4),
            "span_seconds": c["span"], "occurrences": c["count"], "hops": len(key)}, c["tier"],
            path=list(c["path"])))
        for a in key:
            prev = signals.get(a)
            if prev is None or (c["tier"], -c["ratio"]) < (prev.raw_tier, -prev.metrics["ratio"]):
                signals[a] = Signal(account=a, kind="ROUND_TRIP", family=CIRCULARITY, raw_tier=c["tier"],
                                    metrics={**findings[-1].metrics, "cycle": list(c["path"]) + [c["path"][0]]},
                                    txns=list(c["txns"]), finding=fid)
    return signals, findings, dict(reciprocal)


def _record_cycle(cfg, cycles, path, tpath, returned: Fraction, sent: int, span: int) -> None:
    ratio = float(returned / sent)
    tier = classify_round_trip(cfg, ratio, span)
    if tier is None:
        return
    rot = path.index(min(path))
    key = path[rot:] + path[:rot]
    entry = cycles.get(key)
    rank = (tier, -ratio, span)
    if entry is None:
        cycles[key] = {"tier": tier, "ratio": ratio, "returned": int(returned), "sent": sent, "span": span,
                       "txns": list(tpath), "path": path, "count": 1, "_seen": {frozenset(tpath)}}
        return
    if frozenset(tpath) not in entry["_seen"]:
        entry["_seen"].add(frozenset(tpath))
        entry["count"] += 1
    if rank < (entry["tier"], -entry["ratio"], entry["span"]):
        entry.update(tier=tier, ratio=ratio, returned=int(returned), sent=sent, span=span,
                     txns=list(tpath), path=path)


def classify_round_trip(cfg, ratio: float, span: int) -> int | None:
    if span <= cfg.rt_strong_span and ratio >= cfg.rt_strong_return:
        return 0
    if span <= cfg.rt_moderate_span and ratio >= cfg.rt_moderate_return:
        return 1
    return None
