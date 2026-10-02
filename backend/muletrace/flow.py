"""Stages 4â€“5: Fund-Flow Engine â€” FIFO lots, flow links, episodes, tiers, exact tracing (ARCHITECTURE Â§5)."""
from __future__ import annotations

import bisect
from collections import defaultdict, deque
from dataclasses import dataclass, field
from fractions import Fraction

from .config import Config
from .profiles import NOVEL, Dataset

TIER_NAMES = ("STRONG", "MODERATE", "WEAK")


def tier_name(t: int | None) -> str | None:
    return None if t is None else TIER_NAMES[t]


def better(a: int | None, b: int | None) -> int | None:
    """Stronger of two tiers (lower index is stronger)."""
    if a is None:
        return b
    if b is None:
        return a
    return min(a, b)


def weaker(a: int | None, b: int | None) -> int | None:
    if a is None or b is None:
        return None
    return max(a, b)


def dwell_tier(cfg: Config, seconds: float) -> int | None:
    for i, bound in enumerate(cfg.tier_dwell):
        if seconds <= bound:
            return i
    return None


def conservation_tier(cfg: Config, c: float) -> int | None:
    for i, threshold in enumerate(cfg.tier_conservation):
        if c >= threshold:
            return i
    return None


@dataclass(slots=True)
class Link:
    id: int
    account: str
    in_txn: int
    out_txn: int
    amount: int
    dwell: int


@dataclass
class Episode:
    id: str
    account: str
    in_txns: list[int]
    out_txns: list[int]
    links: list[int]
    inflow: int
    outflow: int
    forwarded: int
    dwell: float                  # amount-weighted mean seconds (traced); window bound for window episodes
    c_traced: float
    traced_tier: int | None
    window_tier: int | None
    window_detail: dict | None
    tier: int | None              # raw tier = better(traced, window)
    start: int
    end: int
    kind: str = "traced"          # traced | window (pooled or unlinked lot)
    final_tier: int | None = None
    mitigations: list[str] = field(default_factory=list)
    mitigation_blocked: str | None = None


@dataclass
class FlowGraph:
    links: list[Link]
    by_account: dict[str, list[int]]
    by_in: dict[int, list[int]]        # inflow txn -> links consuming it (at its receiver)
    by_out: dict[int, list[int]]       # outflow txn -> links funding it (at its sender)
    own_funds: dict[int, int]          # outflow txn -> amount not traceable to a live lot
    expired: dict[str, int]
    episodes: dict[str, Episode] = field(default_factory=dict)
    episodes_by_account: dict[str, list[str]] = field(default_factory=dict)
    episode_of_txn: dict[tuple[str, int], str] = field(default_factory=dict)

    def structural(self, link_id: int, cfg: Config) -> bool:
        return self.links[link_id].amount >= cfg.minor(cfg.min_link)


def build_links(ds: Dataset) -> FlowGraph:
    cfg = ds.cfg
    links: list[Link] = []
    by_account: dict[str, list[int]] = defaultdict(list)
    by_in: dict[int, list[int]] = defaultdict(list)
    by_out: dict[int, list[int]] = defaultdict(list)
    own_funds: dict[int, int] = {}
    expired: dict[str, int] = defaultdict(int)
    txns = ds.txns

    for acc in ds.sorted_accounts():
        if acc.pooled:
            for o in acc.out_txns:
                own_funds[o] = txns[o].amount
            continue
        events = [(txns[i].ts, 0, i) for i in acc.in_txns] + [(txns[o].ts, 1, o) for o in acc.out_txns]
        events.sort()
        lots: deque[list[int]] = deque()       # [in_txn, ts, remaining]
        for ts, kind, idx in events:
            while lots and lots[0][1] < ts - cfg.horizon:
                expired[acc.id] += lots.popleft()[2]
            if kind == 0:
                lots.append([idx, ts, txns[idx].amount])
                continue
            need = txns[idx].amount
            # lots inside the horizon but not at the head may also expire; FIFO consumes oldest live lot first
            while need and lots:
                lot = lots[0]
                if lot[1] < ts - cfg.horizon:
                    expired[acc.id] += lots.popleft()[2]
                    continue
                take = min(need, lot[2])
                link = Link(len(links), acc.id, lot[0], idx, take, ts - lot[1])
                links.append(link)
                by_account[acc.id].append(link.id)
                by_in[lot[0]].append(link.id)
                by_out[idx].append(link.id)
                lot[2] -= take
                need -= take
                if lot[2] == 0:
                    lots.popleft()
            own_funds[idx] = need
    return FlowGraph(links, dict(by_account), dict(by_in), dict(by_out), own_funds, dict(expired))


def _window_tier(ds: Dataset, lot_ts: int, lot_amount: int, out_ts: list[int], prefix: list[int]) -> tuple[int | None, dict | None]:
    """Best tier whose window bound and amount-matched conservation are both met."""
    cfg = ds.cfg
    lo = bisect.bisect_left(out_ts, lot_ts)
    best, detail = None, None
    for t, bound in enumerate(cfg.tier_dwell):
        hi = bisect.bisect_right(out_ts, lot_ts + bound)
        total = prefix[hi] - prefix[lo]
        if total <= 0:
            continue
        r = total / lot_amount
        c = min(r, 1 / r)
        if conservation_tier(cfg, c) is not None and conservation_tier(cfg, c) <= t:
            best = t
            detail = {"bound_seconds": bound, "lot_amount": lot_amount, "outflow_in_window": total,
                      "conservation": round(c, 4)}
            break
    return best, detail


def build_episodes(ds: Dataset, fg: FlowGraph) -> None:
    cfg = ds.cfg
    txns = ds.txns
    min_ep = cfg.minor(cfg.min_episode)
    for acc in ds.sorted_accounts():
        eps: list[Episode] = []
        if acc.pooled:
            eps = _pooled_episodes(ds, acc)
        else:
            parent: dict[tuple[str, int], tuple[str, int]] = {}

            def find(x):
                while parent[x] != x:
                    parent[x] = parent[parent[x]]
                    x = parent[x]
                return x

            for lid in fg.by_account.get(acc.id, []):
                if not fg.structural(lid, cfg):
                    continue
                l = fg.links[lid]
                a, b = ("i", l.in_txn), ("o", l.out_txn)
                parent.setdefault(a, a)
                parent.setdefault(b, b)
                ra, rb = find(a), find(b)
                if ra != rb:
                    parent[max(ra, rb)] = min(ra, rb)
            comps: dict[tuple[str, int], list[tuple[str, int]]] = defaultdict(list)
            for node in parent:
                comps[find(node)].append(node)

            out_ts = [txns[o].ts for o in acc.out_txns]
            out_amt = [txns[o].amount for o in acc.out_txns]
            prefix = [0]
            for v in out_amt:
                prefix.append(prefix[-1] + v)

            linked_in: set[int] = set()
            for nodes in comps.values():
                ins = sorted(i for k, i in nodes if k == "i")
                outs = sorted(o for k, o in nodes if k == "o")
                linked_in.update(ins)
                link_ids = sorted({lid for i in ins for lid in fg.by_in.get(i, [])
                                   if fg.links[lid].out_txn in outs and fg.structural(lid, cfg)})
                inflow = sum(txns[i].amount for i in ins)
                outflow = sum(txns[o].amount for o in outs)
                forwarded = sum(fg.links[lid].amount for lid in link_ids)
                dwell = (sum(Fraction(fg.links[lid].amount * fg.links[lid].dwell) for lid in link_ids)
                         / forwarded) if forwarded else 0
                c_t = forwarded / max(inflow, outflow) if max(inflow, outflow) else 0.0
                traced_tier = weaker(dwell_tier(cfg, float(dwell)), conservation_tier(cfg, c_t))
                window_tier, wdetail = None, None
                for i in ins:
                    if txns[i].amount >= min_ep:
                        wt, wd = _window_tier(ds, txns[i].ts, txns[i].amount, out_ts, prefix)
                        if wt is not None and (window_tier is None or wt < window_tier):
                            window_tier, wdetail = wt, {**wd, "lot_txn": i}
                evaluated = inflow >= min_ep
                eps.append(Episode(
                    id="", account=acc.id, in_txns=ins, out_txns=outs, links=link_ids,
                    inflow=inflow, outflow=outflow, forwarded=forwarded, dwell=float(dwell),
                    c_traced=round(c_t, 4),
                    traced_tier=traced_tier if evaluated else None,
                    window_tier=window_tier if evaluated else None, window_detail=wdetail,
                    tier=better(traced_tier, window_tier) if evaluated else None,
                    start=min(txns[x].ts for x in ins + outs), end=max(txns[x].ts for x in ins + outs),
                ))
            # unlinked lots (e.g. hidden behind an earlier reservoir) still get the window test
            for i in acc.in_txns:
                if i in linked_in or txns[i].amount < min_ep:
                    continue
                wt, wd = _window_tier(ds, txns[i].ts, txns[i].amount, out_ts, prefix)
                if wt is None:
                    continue
                bound = wd["bound_seconds"]
                lo = bisect.bisect_left(out_ts, txns[i].ts)
                hi = bisect.bisect_right(out_ts, txns[i].ts + bound)
                outs = acc.out_txns[lo:hi]
                eps.append(Episode(
                    id="", account=acc.id, in_txns=[i], out_txns=list(outs), links=[],
                    inflow=txns[i].amount, outflow=sum(txns[o].amount for o in outs), forwarded=0,
                    dwell=float(bound), c_traced=0.0, traced_tier=None, window_tier=wt,
                    window_detail={**wd, "lot_txn": i}, tier=wt,
                    start=txns[i].ts, end=max([txns[i].ts] + [txns[o].ts for o in outs]), kind="window",
                ))
        eps.sort(key=lambda e: (e.start, min(e.in_txns) if e.in_txns else -1, e.kind))
        ids = []
        for k, e in enumerate(eps, start=1):
            e.id = f"EP-{acc.id}-{k}"
            fg.episodes[e.id] = e
            ids.append(e.id)
            for x in e.in_txns:
                fg.episode_of_txn.setdefault((acc.id, x), e.id)
            for x in e.out_txns:
                fg.episode_of_txn.setdefault((acc.id, x), e.id)
        fg.episodes_by_account[acc.id] = ids


def _pooled_episodes(ds: Dataset, acc) -> list[Episode]:
    """Amount-matched NOVEL -> NOVEL window episodes for pooled accounts (Â§7.6)."""
    cfg = ds.cfg
    txns = ds.txns
    min_ep = cfg.minor(cfg.min_episode)
    novel_outs = [o for o in acc.out_txns
                  if ds.relationship(acc.id, txns[o].receiver, txns[o].ts) == NOVEL]
    out_ts = [txns[o].ts for o in novel_outs]
    prefix = [0]
    for o in novel_outs:
        prefix.append(prefix[-1] + txns[o].amount)
    eps = []
    for i in acc.in_txns:
        t = txns[i]
        if t.amount < min_ep or ds.relationship(t.sender, acc.id, t.ts) != NOVEL:
            continue
        wt, wd = _window_tier(ds, t.ts, t.amount, out_ts, prefix)
        if wt is None:
            continue
        lo = bisect.bisect_left(out_ts, t.ts)
        hi = bisect.bisect_right(out_ts, t.ts + wd["bound_seconds"])
        outs = novel_outs[lo:hi]
        eps.append(Episode(
            id="", account=acc.id, in_txns=[i], out_txns=outs, links=[], inflow=t.amount,
            outflow=sum(txns[o].amount for o in outs), forwarded=0, dwell=float(wd["bound_seconds"]),
            c_traced=0.0, traced_tier=None, window_tier=wt, window_detail={**wd, "lot_txn": i},
            tier=wt, start=t.ts, end=max([t.ts] + [txns[o].ts for o in outs]), kind="window",
        ))
    return eps


# ---------------------------------------------------------------- exact tracing

@dataclass
class TraceResult:
    direction: str
    start: dict[int, Fraction]
    edge_amounts: dict[tuple[str, str], Fraction]
    edge_txns: dict[tuple[str, str], set[int]]
    node_dwell: dict[str, list[int]]           # dwell of links at each account
    node_amount: dict[str, Fraction]           # traced amount reaching (fwd) / originating at (back)
    retained: dict[str, Fraction]              # fwd: kept at account; back: own funds of account
    stopped: dict[str, Fraction]               # pooled boundary
    truncated: Fraction
    hops: dict[str, int]

    def total_start(self) -> Fraction:
        return sum(self.start.values(), Fraction(0))

    def accounted(self) -> Fraction:
        return (sum(self.retained.values(), Fraction(0)) + sum(self.stopped.values(), Fraction(0))
                + self.truncated)


def trace(ds: Dataset, fg: FlowGraph, start_txns: list[int], direction: str, max_hops: int) -> TraceResult:
    """Exact proportional trace. Forward: where did these transactions' funds go.
    Backward: where did these transactions' funds come from."""
    txns = ds.txns
    accounts = ds.accounts
    res = TraceResult(direction, {}, defaultdict(Fraction), defaultdict(set), defaultdict(list),
                      defaultdict(Fraction), defaultdict(Fraction), defaultdict(Fraction), Fraction(0), {})
    level: dict[int, Fraction] = {}
    for t in sorted(set(start_txns)):
        level[t] = Fraction(txns[t].amount)
        res.start[t] = Fraction(txns[t].amount)
    depth = 0
    while level:
        nxt: dict[int, Fraction] = defaultdict(Fraction)
        for t in sorted(level):
            amt = level[t]
            tx = txns[t]
            key = (tx.sender, tx.receiver)
            res.edge_amounts[key] += amt
            res.edge_txns[key].add(t)
            here = tx.receiver if direction == "fwd" else tx.sender
            res.node_amount[here] += amt
            res.hops[here] = min(res.hops.get(here, depth + 1), depth + 1)
            if accounts[here].pooled:
                res.stopped[here] += amt
                continue
            link_ids = fg.by_in.get(t, []) if direction == "fwd" else fg.by_out.get(t, [])
            linked = sum(fg.links[l].amount for l in link_ids)
            rest = amt * Fraction(tx.amount - linked, tx.amount)
            if rest:
                res.retained[here] += rest
            for l in link_ids:
                link = fg.links[l]
                share = amt * Fraction(link.amount, tx.amount)
                follow = link.out_txn if direction == "fwd" else link.in_txn
                res.node_dwell[here].append(link.dwell)
                if depth + 1 >= max_hops:
                    res.truncated += share
                else:
                    nxt[follow] += share
        level = dict(nxt)
        depth += 1
    return res
