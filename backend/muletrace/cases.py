"""Stages 7–8: raw cases, relay paths, structural roles, possible-victim indicator (ARCHITECTURE §7.1–7.3)."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from .flow import FlowGraph
from .profiles import ESTABLISHED, Dataset

INDICATED, CONTRA, NOT_ASSESSED = "INDICATED", "CONTRA_INDICATED", "NOT_ASSESSED"


@dataclass
class Case:
    id: str
    members: list[str]
    active: list[str]
    edges: list[int]                       # txn idx
    roles: dict[str, str] = field(default_factory=dict)
    origins: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)


@dataclass
class RelayPaths:
    accounts: set[str]
    episodes: set[str]
    best_path: dict[str, dict]             # account -> {"accounts": [...], "txns": [...], "span": s}


@dataclass
class CaseResult:
    cases: list[Case]
    case_of: dict[str, list[str]]          # account -> case ids
    flow_active: set[str]
    corroborated_raw: RelayPaths
    roles: dict[str, str] = field(default_factory=dict)
    origin_of: dict[str, list[str]] = field(default_factory=dict)       # account -> cases it originates
    indicator: dict[str, dict] = field(default_factory=dict)
    direct_links: dict[str, set[str]] = field(default_factory=dict)     # account adjacency through flow

    def case(self, cid: str) -> Case:
        return next(c for c in self.cases if c.id == cid)


def flow_txns(ds: Dataset, fg: FlowGraph, raw: dict) -> set[int]:
    """Transactions of the episodes and paths that made accounts flow-active (raw tier >= MODERATE).

    Only the suspicious movement forms a case — not every linked payment an account ever made."""
    s: set[int] = set()
    for kind in ("RELAY", "HUB"):
        for sig in raw[kind].values():
            for eid in sig.episodes:
                ep = fg.episodes[eid]
                if ep.tier in (0, 1):
                    s.update(ep.in_txns)
                    s.update(ep.out_txns)
    for kind in ("LAYERED_RECEIPT", "ROUND_TRIP"):
        for sig in raw[kind].values():
            if sig.raw_tier in (0, 1):
                s.update(sig.txns)
    return s


def relay_paths(ds: Dataset, fg: FlowGraph, tier_of: dict[str, int | None], max_tier: int,
                span_limit: int | None, exclude: set[str] = frozenset()) -> RelayPaths:
    """Traced paths through >= chain_min_relays consecutive relays (tier <= max_tier)."""
    cfg = ds.cfg
    txns = ds.txns
    relays = {a for a, t in tier_of.items()
              if t is not None and t <= max_tier and a not in exclude and not ds.accounts[a].pooled}
    out = RelayPaths(set(), set(), {})
    if not relays:
        return out

    def forwards(t: int) -> list:
        return [fg.links[l] for l in fg.by_in.get(t, []) if fg.structural(l, cfg)]

    starts = sorted(t for a in relays for t in ds.accounts[a].in_txns if forwards(t))
    for t0 in starts:
        stack = [(t0, (txns[t0].receiver,), (t0,))]
        while stack:
            t, path, tpath = stack.pop()
            acc = txns[t].receiver
            extended = False
            if len(path) <= cfg.trace_max_hops:
                for link in sorted(forwards(t), key=lambda l: (-l.amount, l.out_txn))[:cfg.rt_branch_cap]:
                    nxt = txns[link.out_txn].receiver
                    span = txns[link.out_txn].ts - txns[t0].ts
                    if span_limit is not None and span > span_limit:
                        continue
                    if nxt in relays and nxt not in path and forwards(link.out_txn):
                        stack.append((link.out_txn, path + (nxt,), tpath + (link.out_txn,)))
                        extended = True
            if not extended and len(path) >= cfg.chain_min_relays:
                # close the path with the last relay's outgoing leg for timing and display
                last_out = max((l.out_txn for l in forwards(t)), key=lambda o: txns[o].ts, default=t)
                span = txns[last_out].ts - txns[t0].ts
                if span_limit is not None and span > span_limit:
                    last_out = min((l.out_txn for l in forwards(t)), key=lambda o: txns[o].ts, default=t)
                    span = txns[last_out].ts - txns[t0].ts
                    if span > span_limit:
                        continue
                full = list(tpath) + ([last_out] if last_out != t else [])
                info = {"accounts": list(path), "txns": full, "span": span}
                for i, a in enumerate(path):
                    out.accounts.add(a)
                    ep = fg.episode_of_txn.get((a, tpath[i]))
                    if ep:
                        out.episodes.add(ep)
                    prev = out.best_path.get(a)
                    if prev is None or (len(path), -span) > (len(prev["accounts"]), -prev["span"]):
                        out.best_path[a] = info
    return out


def build(ds: Dataset, fg: FlowGraph, raw: dict[str, dict], identity_signals: dict) -> CaseResult:
    cfg = ds.cfg
    txns = ds.txns
    active = sorted({a for kind in ("RELAY", "HUB", "LAYERED_RECEIPT", "ROUND_TRIP")
                     for a, s in raw[kind].items() if s.raw_tier in (0, 1)})
    active_set = set(active)
    ftx = flow_txns(ds, fg, raw)

    edges: list[int] = []
    for t in sorted(ftx):
        tx = txns[t]
        s_act, r_act = tx.sender in active_set, tx.receiver in active_set
        if not (s_act or r_act):
            continue
        if not (s_act and r_act) and ds.relationship(tx.sender, tx.receiver, tx.ts) == ESTABLISHED:
            continue
        edges.append(t)

    parent: dict[str, str] = {}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for t in edges:
        a, b = txns[t].sender, txns[t].receiver
        parent.setdefault(a, a)
        parent.setdefault(b, b)
        ra, rb = find(a), find(b)
        if ra != rb:
            lo, hi = sorted((ra, rb))
            parent[hi] = lo
    comp_members: dict[str, list[str]] = defaultdict(list)
    for a in sorted(parent):
        comp_members[find(a)].append(a)
    comp_edges: dict[str, list[int]] = defaultdict(list)
    for t in edges:
        comp_edges[find(txns[t].sender)].append(t)

    cases: list[Case] = []
    for k, root in enumerate(sorted(comp_members, key=lambda r: (-len(comp_members[r]), r)), start=1):
        members = comp_members[root]
        cases.append(Case(f"CASE-{k:02d}", members, [m for m in members if m in active_set], comp_edges[root]))
    case_of: dict[str, list[str]] = defaultdict(list)
    for c in cases:
        for m in c.members:
            case_of[m].append(c.id)

    relay_tiers = {a: s.raw_tier for a, s in raw["RELAY"].items()}
    corroborated = relay_paths(ds, fg, relay_tiers, 0, cfg.corroborated_span)
    result = CaseResult(cases, dict(case_of), active_set, corroborated)

    # flow adjacency between accounts (used for relay qualification)
    adj: dict[str, set[str]] = defaultdict(set)
    for t in sorted(ftx):
        adj[txns[t].sender].add(txns[t].receiver)
        adj[txns[t].receiver].add(txns[t].sender)
    result.direct_links = dict(adj)

    _assign_roles(ds, fg, raw, identity_signals, result)
    return result


def _assign_roles(ds: Dataset, fg: FlowGraph, raw: dict, identity_signals: dict, result: CaseResult) -> None:
    cfg = ds.cfg
    txns = ds.txns
    for case in result.cases:
        mset = set(case.members)
        in_edges: dict[str, list[int]] = defaultdict(list)
        out_edges: dict[str, list[int]] = defaultdict(list)
        for t in case.edges:
            out_edges[txns[t].sender].append(t)
            in_edges[txns[t].receiver].append(t)
        for m in case.members:
            acc = ds.accounts[m]
            role = None
            if acc.pooled:
                role = "POOLED"
            elif not in_edges[m] and out_edges[m] and _origin_funded(ds, fg, m, out_edges[m], result.flow_active):
                role = "ORIGIN"
                case.origins.append(m)
                result.origin_of.setdefault(m, []).append(case.id)
            elif m in raw["HUB"] and raw["HUB"][m].raw_tier in (0, 1):
                role = "HUB"
            elif m in raw["RELAY"] and raw["RELAY"][m].raw_tier in (0, 1):
                senders = {txns[t].sender for t in in_edges[m]}
                receivers = {txns[t].receiver for t in out_edges[m]}
                if len(senders) >= 3 and len(receivers) <= 2:
                    role = "COLLECTOR"
                elif len(senders) <= 2 and len(receivers) >= 3:
                    role = "DISTRIBUTOR"
                else:
                    role = "RELAY"
            elif in_edges[m]:
                received = sum(txns[t].amount for t in in_edges[m])
                forwarded = sum(txns[t].amount for t in out_edges[m])
                role = "SINK" if forwarded < cfg.sink_forward_max * received else "RELAY"
            else:
                role = "COUNTERPARTY"
            case.roles[m] = role
            result.roles.setdefault(m, role)
        case.metrics = _case_metrics(ds, fg, case)

    for acc_id in sorted(identity_signals):
        result.roles.setdefault(acc_id, "CLUSTER_MEMBER")

    # possible-victim indicator (assessed for ORIGIN only)
    for acc_id, cids in sorted(result.origin_of.items()):
        reasons = []
        acc = ds.accounts[acc_id]
        for cid in cids:
            case = result.case(cid)
            others = [m for m in case.members if m != acc_id]
            for attr in ("device", "kyc"):
                shared = sorted({m for m in others if acc.attrs[attr] & ds.accounts[m].attrs[attr]})
                if shared:
                    reasons.append(f"shares a {attr} with case member(s) {', '.join(shared[:4])}")
            back = [t for t in acc.in_txns
                    if txns[t].sender in result.flow_active and txns[t].sender in case.members
                    and txns[t].amount > cfg.minor(cfg.victim_return_dust)]
            if back:
                reasons.append(f"received {len(back)} payment(s) back from case members above the dust threshold")
        if acc_id in identity_signals:
            reasons.append("member of a shared-attribute cluster")
        if acc_id in raw["ROUND_TRIP"]:
            reasons.append("part of a circular flow")
        if len(cids) >= 2:
            reasons.append(f"originates funds into {len(cids)} separate cases")
        reasons = sorted(set(reasons))
        result.indicator[acc_id] = {"status": CONTRA if reasons else INDICATED, "reasons": reasons}


def _origin_funded(ds: Dataset, fg: FlowGraph, acc_id: str, outs: list[int], active: set[str]) -> bool:
    cfg = ds.cfg
    txns = ds.txns
    total = sum(txns[o].amount for o in outs)
    own = sum(fg.own_funds.get(o, 0) for o in outs)
    established = 0
    for o in outs:
        for lid in fg.by_out.get(o, []):
            link = fg.links[lid]
            src = txns[link.in_txn]
            if src.sender not in active and ds.relationship(src.sender, acc_id, src.ts) == ESTABLISHED:
                established += link.amount
    covered = all(txns[o].s_bal_before is not None and txns[o].s_bal_before >= txns[o].amount for o in outs)
    return (own >= cfg.origin_own_funds_share * total
            or established >= cfg.established_share * total
            or covered)


def _case_metrics(ds: Dataset, fg: FlowGraph, case: Case) -> dict:
    txns = ds.txns
    edge_set = set(case.edges)
    dwells = sorted(fg.links[l].dwell for m in case.active for l in fg.by_account.get(m, [])
                    if fg.links[l].in_txn in edge_set and fg.links[l].out_txn in edge_set
                    and fg.structural(l, ds.cfg))
    ts = [txns[t].ts for t in case.edges]
    entering = sum(txns[t].amount for t in case.edges if txns[t].sender in case.origins)
    return {
        "accounts": len(case.members), "active": len(case.active), "transactions": len(case.edges),
        "start": min(ts) if ts else None, "end": max(ts) if ts else None,
        "median_dwell_seconds": dwells[len(dwells) // 2] if dwells else None,
        "value_from_origins": entering,
        "value_moved": sum(txns[t].amount for t in case.edges),
    }
