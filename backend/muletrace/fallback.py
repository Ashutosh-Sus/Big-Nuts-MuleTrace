"""Fallback engine (engine=window): window-based signals behind the same contract (ARCHITECTURE §10).

No FIFO attribution: every inflow is evaluated with the window test only, cycles use a greedy
temporal walk over transactions, and traces are reported as plain transactions.
"""
from __future__ import annotations

from .flow import FlowGraph, build_episodes
from .profiles import Dataset
from .signals import CIRCULARITY, Finding, Signal, classify_round_trip, hub_signals, relay_signals


def build_window_engine(ds: Dataset):
    fg = FlowGraph(links=[], by_account={}, by_in={}, by_out={},
                   own_funds={t.idx: t.amount for t in ds.txns}, expired={})
    build_episodes(ds, fg)          # without links every lot gets the window test
    raw = {"RELAY": relay_signals(ds, fg), "HUB": hub_signals(ds, fg), "LAYERED_RECEIPT": {}}
    raw["ROUND_TRIP"], findings = _greedy_cycles(ds)
    return fg, raw, findings, {}


def _greedy_cycles(ds: Dataset):
    cfg = ds.cfg
    txns = ds.txns
    cycles: dict[tuple[str, ...], dict] = {}
    for acc in ds.sorted_accounts():
        if acc.pooled:
            continue
        for o in acc.out_txns:
            if txns[o].amount < cfg.minor(cfg.min_episode):
                continue
            start = txns[o]
            stack = [(o, (acc.id,), (o,), start.amount)]
            while stack:
                t, path, tpath, low = stack.pop()
                tx = txns[t]
                if tx.receiver == acc.id and len(path) >= 3:
                    span = tx.ts - start.ts
                    ratio = low / start.amount
                    tier = classify_round_trip(cfg, ratio, span)
                    if tier is not None:
                        rot = path.index(min(path))
                        key = path[rot:] + path[:rot]
                        prev = cycles.get(key)
                        if prev is None or (tier, -ratio) < (prev["tier"], -prev["ratio"]):
                            cycles[key] = {"tier": tier, "ratio": ratio, "span": span, "txns": list(tpath),
                                           "path": path, "sent": start.amount, "returned": low}
                    continue
                nxt = tx.receiver
                if nxt in path or ds.accounts[nxt].pooled or len(path) >= cfg.rt_max_hops:
                    continue
                cands = [n for n in ds.accounts[nxt].out_txns
                         if txns[n].ts >= tx.ts and txns[n].ts - start.ts <= cfg.rt_moderate_span
                         and txns[n].amount >= cfg.rt_moderate_return * start.amount]
                cands.sort(key=lambda n: (txns[n].ts, n))
                for n in cands[:cfg.rt_branch_cap]:
                    stack.append((n, path + (nxt,), tpath + (n,), min(low, txns[n].amount)))
    signals, findings = {}, []
    for k, key in enumerate(sorted(cycles, key=lambda c: (cycles[c]["tier"], -cycles[c]["ratio"], c)), start=1):
        c = cycles[key]
        fid = f"F-RT-{k:03d}"
        metrics = {"returned": c["returned"], "sent": c["sent"], "ratio": round(c["ratio"], 4),
                   "span_seconds": c["span"], "occurrences": 1, "hops": len(key),
                   "cycle": list(c["path"]) + [c["path"][0]]}
        findings.append(Finding(fid, "ROUND_TRIP", list(key), c["txns"], metrics, c["tier"], path=list(c["path"])))
        for a in key:
            if a not in signals or c["tier"] < signals[a].raw_tier:
                signals[a] = Signal(account=a, kind="ROUND_TRIP", family=CIRCULARITY, raw_tier=c["tier"],
                                    metrics=dict(metrics), txns=list(c["txns"]), finding=fid)
    return signals, findings
