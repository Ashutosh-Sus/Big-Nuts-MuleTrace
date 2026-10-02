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
    parents: dict[str, set[str]] = defaultdict(set)     # neighbours one hop closer to the focus
    via_suspicious: dict[str, bool] = defaultdict(bool)
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
                if dist[b] == h:
                    parents[b].add(a)
                    via_suspicious[b] = via_suspicious[b] or t in susp
        frontier = sorted(nxt)

    volume: dict[str, int] = defaultdict(int)
    for a in dist:
        acc = ds.accounts[a]
        volume[a] = acc.in_total + acc.out_total

    def rank(a: str):
        r = an.results[a]
        return (a != focus, dist[a], not (a in case_members), not r.flagged, -volume[a], a)

    shown = _select_by_level(dist, parents, via_suspicious, rank, hops, cfg.network_max_nodes, suspicious_only)
    hidden = len(dist) - len(shown)

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

    return {
        "mode": "network",
        "focus": focus,
        "nodes": [_node(an, a, dispositions, focus, dist[a]) for a in sorted(shown, key=rank)],
        "edges": sorted(edges.values(), key=lambda e: (e["first_ts"], e["id"])),
        "identity_edges": _identity_edges(an, shown),
        "hidden_count": hidden,
        "total_count": len(dist),
        "truncated": hidden > 0,
    }


def _select_by_level(dist: dict, parents: dict, via_suspicious: dict, rank, hops: int, cap: int,
                     suspicious_only: bool) -> set[str]:
    """Which accounts of a k-hop neighbourhood are drawn. Under the cap: all of them. Over it, each hop level
    gets a share of the cap (so raising the hop count visibly adds the next ring), every drawn account is
    attached to a drawn account one hop closer (the picture stays connected), and with "suspicious flows
    only" off, accounts reached only through ordinary transactions take turns with the others."""
    if len(dist) <= cap:
        return set(dist)
    focus = next(a for a, h in dist.items() if h == 0)
    shown = {focus}
    by_level = defaultdict(list)
    for a, h in dist.items():
        if h:
            by_level[h].append(a)

    def candidates(h: int) -> list[str]:
        ready = sorted((a for a in by_level[h] if a not in shown and parents[a] & shown), key=rank)
        if suspicious_only:
            return ready
        sus = [a for a in ready if via_suspicious[a]]
        other = [a for a in ready if not via_suspicious[a]]
        mixed = []
        for i in range(max(len(sus), len(other))):
            mixed += ([sus[i]] if i < len(sus) else []) + ([other[i]] if i < len(other) else [])
        return mixed

    for h in range(1, hops + 1):
        share = -(-(cap - len(shown)) // (hops - h + 1))           # ceiling of an even split of what is left
        shown.update(candidates(h)[:share])
    # room left by thin levels goes to the best attachable accounts, closest levels first
    while len(shown) < cap:
        added = False
        for h in range(1, hops + 1):
            nxt = candidates(h)
            if nxt:
                shown.add(nxt[0])
                added = True
                break
        if not added:
            break
    return shown


def _identity_edges(an, shown: set[str]) -> list[dict]:
    out = []
    for cl in an.identity.clusters:
        for att in cl.metrics["attributes"]:
            ms = [m for m in att["members"] if m in shown]
            for i in range(len(ms)):
                for j in range(i + 1, len(ms)):
                    out.append({"source": ms[i], "target": ms[j], "attr": att["type"], "value": att["value"]})
    return out[:300]


CASE_ROLE_ORDER = {"ORIGIN": 0, "HUB": 1, "COLLECTOR": 2, "DISTRIBUTOR": 3, "RELAY": 4, "POOLED": 5,
                   "SINK": 6, "COUNTERPARTY": 7}


def case_network(an, case, dispositions: dict) -> dict:
    """The whole case on one graph: its members and the case transactions between them, same contract as
    `network` (no focus account). Over the node cap, a connected part built from the case's most valuable
    money paths is drawn (`_case_story`)."""
    ds = an.ds
    txns = ds.txns
    susp = an.suspicious_cache if hasattr(an, "suspicious_cache") else suspicious_txns(an)
    an.suspicious_cache = susp

    def rank(a: str):
        r = an.results[a]
        return (CASE_ROLE_ORDER.get(case.roles.get(a), 9) != 0, not r.flagged, -r.score,
                CASE_ROLE_ORDER.get(case.roles.get(a), 9), a)

    cap = an.cfg.network_max_nodes
    shown = set(case.members) if len(case.members) <= cap else _case_story(an, case, cap)
    hidden = len(case.members) - len(shown)

    edges: dict[tuple[str, str], dict] = {}
    for t in sorted(case.edges, key=lambda t: (txns[t].ts, t)):
        tx = txns[t]
        if tx.sender not in shown or tx.receiver not in shown:
            continue
        e = edges.setdefault((tx.sender, tx.receiver), {
            "id": f"{tx.sender}->{tx.receiver}", "source": tx.sender, "target": tx.receiver,
            "count": 0, "total": 0, "first_ts": tx.ts, "last_ts": tx.ts, "txn_ids": [], "suspicious": False})
        e["count"] += 1
        e["total"] += tx.amount
        e["last_ts"] = tx.ts
        if len(e["txn_ids"]) < 50:
            e["txn_ids"].append(tx.txn_id)
        e["suspicious"] = e["suspicious"] or t in susp
    # roles of this case (an account in several cases can differ per case); shown only for a case with a
    # flagged member, as everywhere else (ARCHITECTURE §7.2)
    labelled = any(an.results[m].flagged for m in case.members)
    nodes = []
    for a in sorted(shown, key=rank):
        n = _node(an, a, dispositions, "", 0)
        if labelled:
            n["role"] = case.roles.get(a)
        nodes.append(n)
    return {
        "mode": "network",
        "focus": "",
        "case": case.id,
        "label": "case transactions",
        "nodes": nodes,
        "edges": sorted(edges.values(), key=lambda e: (e["first_ts"], e["id"])),
        "identity_edges": _identity_edges(an, shown),
        "hidden_count": hidden,
        "total_count": len(case.members),
        "truncated": hidden > 0,
    }


def _case_story(an, case, cap: int) -> set[str]:
    """The drawn part of a case larger than the node cap: its most valuable money paths, kept connected.

    A path starts at a likely origin (or, if the case has none, at a member that receives no case
    transaction) and follows the largest outgoing case transaction until the money leaves the case. Paths are
    taken in order of the value entering them; each path after the first must share an account with what is
    already drawn. Room that is left goes to the highest-scoring flagged neighbours. The result shows victims,
    relays, collectors and cash-out together instead of whichever role happens to rank first."""
    txns = an.ds.txns
    members = set(case.members)
    out: dict[str, list[int]] = defaultdict(list)
    has_in: set[str] = set()
    adj: dict[str, set[str]] = defaultdict(set)
    for t in sorted(case.edges):
        s, r = txns[t].sender, txns[t].receiver
        out[s].append(t)
        has_in.add(r)
        adj[s].add(r)
        adj[r].add(s)
    best_out = {a: sorted(ts, key=lambda t: (-txns[t].amount, txns[t].ts, t)) for a, ts in out.items()}
    starts = sorted(a for a in members if case.roles.get(a) == "ORIGIN" and a in best_out)
    if not starts:
        starts = sorted(a for a in members if a not in has_in and a in best_out)
    paths = []
    for s in starts:
        path, seen, cur = [s], {s}, s
        while True:
            nxt = next((txns[t].receiver for t in best_out.get(cur, []) if txns[t].receiver not in seen), None)
            if nxt is None:
                break
            path.append(nxt)
            seen.add(nxt)
            cur = nxt
        if len(path) > 1:
            paths.append((-txns[best_out[s][0]].amount, s, path))
    paths.sort()

    shown: set[str] = set()

    def add_path(path: list[str]) -> None:
        # nearest-to-the-drawn-part first, so a path that does not fit whole is still attached
        on = [i for i, a in enumerate(path) if a in shown] or [0]
        order = sorted(range(len(path)), key=lambda i: (min(abs(i - j) for j in on), i))
        for i in order:
            if len(shown) >= cap:
                return
            shown.add(path[i])
        # where the money left the case: each path account's largest payees that move nothing further
        # (a path follows only the largest transfer, so a second cash-out account would otherwise be missing)
        for a in path:
            ends = [txns[t].receiver for t in best_out.get(a, []) if txns[t].receiver not in best_out]
            for b in list(dict.fromkeys(ends))[:2]:
                if len(shown) >= cap:
                    return
                shown.add(b)

    def score_rank(a: str):
        r = an.results[a]
        return (not r.flagged, -r.score, CASE_ROLE_ORDER.get(case.roles.get(a), 9), a)

    pending = [p for _, _, p in paths]
    if not pending:
        shown.add(min(members, key=score_rank))
    def gain(p: list[str]) -> int:
        """Accounts other than victims that the path would add: prefer paths reaching new relays, collectors
        and cash-out accounts over many paths that only add another victim to an already drawn chain."""
        return sum(1 for a in p if a not in shown and case.roles.get(a) != "ORIGIN")

    while len(shown) < cap:
        touching = [(-gain(p), i, p) for i, p in enumerate(pending) if (not shown or set(p) & shown) and gain(p)]
        fit = min(touching)[2] if touching else None
        if fit is not None:
            pending.remove(fit)
            add_path(fit)
            continue
        # no remaining path adds anything but another victim: take one neighbour — not a victim if avoidable,
        # preferably one on a remaining path (so further paths can join), then flagged members by score
        on_path = {a for p in pending for a in p}
        border = {b for a in shown for b in adj[a] if b not in shown}
        if not border:
            break
        shown.add(min(border, key=lambda b: (case.roles.get(b) == "ORIGIN", b not in on_path, score_rank(b))))
    return shown


def directional_view(an, account: str, direction: str, dispositions: dict) -> dict:
    """Fallback engine (no flow tracing): the suspicious transactions leading into the account (`back`) or out
    of it (`fwd`), followed hop by hop in that direction only. Transaction-level, not traced amounts."""
    ds = an.ds
    txns = ds.txns
    hops = 2
    susp = an.suspicious_cache if hasattr(an, "suspicious_cache") else suspicious_txns(an)
    an.suspicious_cache = susp
    dist = {account: 0}
    used: list[int] = []
    frontier = [account]
    for h in range(1, hops + 1):
        nxt = []
        for a in frontier:
            acc = ds.accounts[a]
            for t in sorted(acc.in_txns if direction == "back" else acc.out_txns):
                if t not in susp:
                    continue
                b = txns[t].sender if direction == "back" else txns[t].receiver
                if b not in dist:
                    dist[b] = h
                    nxt.append(b)
                if dist[b] == h:
                    used.append(t)
        frontier = sorted(nxt)

    def rank(a: str):
        r = an.results[a]
        return (a != account, dist[a], not r.flagged, -r.score, a)

    shown = set(sorted(dist, key=rank)[:an.cfg.network_max_nodes])
    edges: dict[tuple[str, str], dict] = {}
    for t in sorted(used, key=lambda t: (txns[t].ts, t)):
        tx = txns[t]
        if tx.sender not in shown or tx.receiver not in shown:
            continue
        e = edges.setdefault((tx.sender, tx.receiver), {
            "id": f"{tx.sender}->{tx.receiver}", "source": tx.sender, "target": tx.receiver,
            "count": 0, "total": 0, "first_ts": tx.ts, "last_ts": tx.ts, "txn_ids": [], "suspicious": True})
        e["count"] += 1
        e["total"] += tx.amount
        e["last_ts"] = tx.ts
        if len(e["txn_ids"]) < 50:
            e["txn_ids"].append(tx.txn_id)
    into = direction == "back"
    return {
        "mode": "transactions", "direction": direction, "focus": account,
        "label": (f"suspicious transactions {'into' if into else 'out of'} this account, up to {hops} hops "
                  f"{'back' if into else 'on'} (not traced) — flow tracing unavailable in fallback mode"),
        "nodes": [_node(an, a, dispositions, account, dist[a]) for a in sorted(shown, key=rank)],
        "edges": sorted(edges.values(), key=lambda e: (e["first_ts"], e["id"])),
        "identity_edges": [],
        "hidden_count": len(dist) - len(shown),
        "total_count": len(dist),
        "truncated": len(dist) > len(shown),
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
        return directional_view(an, account, direction, dispositions)
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
