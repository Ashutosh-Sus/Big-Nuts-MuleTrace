"""Stages 9–11: mitigations, qualification, scoring and severity (ARCHITECTURE §7.4–§8)."""
from __future__ import annotations

from dataclasses import dataclass, field

from .cases import CONTRA, CaseResult, relay_paths
from .flow import FlowGraph, TIER_NAMES
from .identity import IdentityResult
from .profiles import ESTABLISHED, NOVEL, Dataset
from .signals import CIRCULARITY, FLOW, IDENTITY, Signal, hub_signals, receipt_signals


@dataclass
class Component:
    family: str
    rule: str
    points: int
    tier: str | None
    detail: str
    ref: str | None = None


@dataclass
class AccountResult:
    id: str
    score: int = 0
    severity: str | None = None
    flagged: bool = False
    components: list[Component] = field(default_factory=list)
    signals: dict[str, Signal] = field(default_factory=dict)
    families: list[str] = field(default_factory=list)
    exposure: int = 0
    chain: dict | None = None
    corroborated: dict | None = None
    repeated_episodes: int = 0
    origin_zeroed: bool = False
    observations: list[dict] = field(default_factory=list)
    primary_reason: str = ""


# ---------------------------------------------------------------- stage 9

def apply_mitigations(ds: Dataset, fg: FlowGraph, cases: CaseResult) -> None:
    cfg = ds.cfg
    txns = ds.txns
    blocked_eps = cases.corroborated_raw.episodes
    for ep in fg.episodes.values():
        ep.final_tier = ep.tier
        ep.mitigations = []
        ep.mitigation_blocked = None
        if ep.tier is None or ep.kind == "window" and ds.accounts[ep.account].pooled:
            continue
        acc = ep.account
        in_states = [(ds.relationship(txns[i].sender, acc, txns[i].ts), txns[i]) for i in ep.in_txns]
        out_states = [(ds.relationship(acc, txns[o].receiver, txns[o].ts), txns[o]) for o in ep.out_txns]
        if ep.id in blocked_eps:
            ep.mitigation_blocked = "episode lies on a corroborated layering path"
            continue
        if in_states and out_states and all(s == NOVEL for s, _ in in_states) and all(s == NOVEL for s, _ in out_states):
            ep.mitigation_blocked = "new counterparties on both sides"
            continue
        funded = sum(t.amount for s, t in in_states if s == ESTABLISHED and t.sender not in cases.flow_active)
        paid = sum(t.amount for s, t in out_states if s == ESTABLISHED and t.receiver not in cases.flow_active)
        if ep.inflow and funded >= cfg.established_share * ep.inflow:
            ep.mitigations.append("ESTABLISHED_FUNDING")
        if ep.outflow and paid >= cfg.established_share * ep.outflow:
            ep.mitigations.append("ESTABLISHED_PAYEES")
        if ep.mitigations:
            t = ep.tier + len(ep.mitigations)
            ep.final_tier = t if t <= 2 else None


# ---------------------------------------------------------------- stages 10–11

def score(ds: Dataset, fg: FlowGraph, raw: dict[str, dict], identity: IdentityResult,
          cases: CaseResult) -> dict[str, AccountResult]:
    cfg = ds.cfg
    results: dict[str, AccountResult] = {a: AccountResult(a) for a in sorted(ds.accounts)}

    # final RELAY tiers from mitigated episodes
    relay: dict[str, Signal] = {}
    for a, sig in raw["RELAY"].items():
        eps = [fg.episodes[e] for e in sig.episodes]
        finals = [e for e in eps if e.final_tier is not None]
        sig.final_tier = min((e.final_tier for e in finals), default=None)
        results[a].repeated_episodes = sum(1 for e in eps if e.final_tier in (0, 1))
        if finals:
            best = min(finals, key=lambda e: (e.final_tier, -max(e.forwarded, min(e.inflow, e.outflow)), e.start))
            sig.metrics = {**sig.metrics, **_ep_brief(best)}
            sig.txns = sorted(set(best.in_txns) | set(best.out_txns))
        relay[a] = sig
    hub_final = hub_signals(ds, fg, use_final=True)
    for a, sig in raw["HUB"].items():
        final = hub_final.get(a)
        sig.final_tier = final.raw_tier if final else None
        if final:
            sig.metrics, sig.txns, sig.episodes = final.metrics, final.txns, final.episodes
    for sig in raw["ROUND_TRIP"].values():
        sig.final_tier = sig.raw_tier
    id_signals = dict(identity.signals)
    for sig in id_signals.values():
        sig.final_tier = sig.raw_tier

    # ORIGIN zeroing (unless the possible-victim indicator is contra-indicated)
    zeroed: set[str] = set()
    for a in cases.origin_of:
        if cases.indicator.get(a, {}).get("status") != CONTRA:
            zeroed.add(a)
            results[a].origin_zeroed = True
            for kind in ("RELAY", "HUB", "LAYERED_RECEIPT"):
                if a in raw[kind]:
                    raw[kind][a].notes.append("ORIGIN_ZEROED")

    # identity restoration for accounts that share a flow case (precedence rule)
    _restore_identity(ds, identity, cases, id_signals)

    relay_tier = {a: s.final_tier for a, s in relay.items() if a not in zeroed}

    # layered receipts re-evaluated against final relays (origin accounts are not relays)
    receipt_final = receipt_signals(ds, fg, relay_tier)
    for a, sig in raw["LAYERED_RECEIPT"].items():
        final = receipt_final.get(a)
        sig.final_tier = final.raw_tier if final else None
        if final:
            sig.metrics, sig.txns = final.metrics, final.txns
    chain = relay_paths(ds, fg, relay_tier, 1, None)
    corroborated = relay_paths(ds, fg, relay_tier, 0, cfg.corroborated_span)
    relays_ok = {a for a, t in relay_tier.items() if t in (0, 1)}

    def other_family(a: str, fam: str) -> bool:
        fams = set()
        if a in raw["ROUND_TRIP"] and raw["ROUND_TRIP"][a].final_tier in (0, 1):
            fams.add(CIRCULARITY)
        if a in id_signals:
            fams.add(IDENTITY)
        if any(a in raw[k] and raw[k][a].final_tier in (0, 1) and a not in zeroed
               for k in ("RELAY", "HUB", "LAYERED_RECEIPT")):
            fams.add(FLOW)
        return bool(fams - {fam})

    def case_relays(a: str) -> int:
        return max((len([m for m in cases.case(c).members if m in relays_ok]) for c in cases.case_of.get(a, [])),
                   default=0)

    for a in sorted(ds.accounts):
        r = results[a]
        sigs = {}
        for kind in ("RELAY", "HUB", "LAYERED_RECEIPT", "ROUND_TRIP"):
            if a in raw[kind]:
                sigs[kind] = raw[kind][a]
        if a in id_signals:
            sigs["IDENTITY"] = id_signals[a]
        r.signals = sigs
        r.chain = chain.best_path.get(a)
        r.corroborated = corroborated.best_path.get(a)

        for kind, sig in sigs.items():
            sig.qualifies = False
            sig.points = 0
            tier = sig.final_tier
            if tier not in (0, 1):
                continue
            if kind in ("RELAY", "HUB", "LAYERED_RECEIPT") and a in zeroed:
                continue
            if kind == "RELAY":
                linked = any(n in relays_ok and n != a for n in cases.direct_links.get(a, ()))
                sig.metrics["linked_relays"] = sorted(n for n in cases.direct_links.get(a, ())
                                                      if n in relays_ok and n != a)
                sig.qualifies = (linked or r.repeated_episodes >= cfg.repeated_min_episodes
                                 or other_family(a, FLOW))
                if not sig.qualifies:
                    sig.notes.append("ISOLATED_RELAY")
            elif kind == "IDENTITY":
                sig.qualifies = True
            else:
                fam = CIRCULARITY if kind == "ROUND_TRIP" else FLOW
                sig.qualifies = tier == 0 or other_family(a, fam) or case_relays(a) >= cfg.chain_min_relays
                if not sig.qualifies:
                    sig.notes.append("UNCORROBORATED")

        _score_account(cfg, r)
    return results


def _ep_brief(e) -> dict:
    return {"episode": e.id, "kind": e.kind, "inflow": e.inflow, "outflow": e.outflow,
            "forwarded": e.forwarded, "dwell_seconds": round(e.dwell), "conservation": e.c_traced,
            "window": e.window_detail, "start": e.start, "end": e.end,
            "mitigations": e.mitigations, "raw_tier": e.tier, "final_tier": e.final_tier}


def _restore_identity(ds: Dataset, identity: IdentityResult, cases: CaseResult, id_signals: dict) -> None:
    for g in identity.groups:
        if not (g.infrastructure or (g.qualifying and g.established)):
            continue
        candidates = g.sharers if g.infrastructure else g.established
        by_case: dict[str, list[str]] = {}
        for m in g.sharers:
            if m not in cases.flow_active:      # only accounts that themselves move the money
                continue
            for cid in cases.case_of.get(m, []):
                by_case.setdefault(cid, []).append(m)
        for cid, ms in sorted(by_case.items()):
            if len(ms) < 2:
                continue
            for m in ms:
                if m not in candidates:
                    continue
                sig = id_signals.get(m)
                entry = {"type": g.attr, "value": g.value, "shared_with": [x for x in ms if x != m],
                         "restored_via_case": cid}
                if sig is None:
                    sig = id_signals[m] = Signal(
                        account=m, kind="IDENTITY", family=IDENTITY, raw_tier=None,
                        metrics={"link_types": [], "values": [], "cluster_size": len(ms), "ip_only": True,
                                 "collapsed": False, "restored": True,
                                 "establishment": ds.accounts[m].establishment,
                                 "establishment_basis": ds.accounts[m].establishment_basis})
                if g.attr not in sig.metrics["link_types"]:
                    sig.metrics["link_types"] = sorted(sig.metrics["link_types"] + [g.attr])
                sig.metrics["values"].append(entry)
                sig.metrics["restored"] = True
                sig.metrics["ip_only"] = not any(t in ("device", "kyc") for t in sig.metrics["link_types"])
                sig.final_tier = 1 if sig.metrics["ip_only"] else 0
                sig.raw_tier = sig.final_tier if sig.raw_tier is None else min(sig.raw_tier, sig.final_tier)


def _score_account(cfg, r: AccountResult) -> None:
    comps: list[Component] = []
    s = r.signals
    q = {k: v for k, v in s.items() if v.qualifies}

    # FLOW family
    base = []
    pts = {"RELAY": cfg.pts_relay, "HUB": cfg.pts_hub, "LAYERED_RECEIPT": cfg.pts_receipt}
    for kind in ("RELAY", "HUB", "LAYERED_RECEIPT"):
        if kind in q:
            base.append((pts[kind][q[kind].final_tier], kind))
    flow_comps: list[Component] = []
    if base:
        base.sort(key=lambda x: (-x[0], x[1]))
        top_pts, top_kind = base[0]
        flow_comps.append(Component(FLOW, top_kind, top_pts, TIER_NAMES[q[top_kind].final_tier], "strongest flow signal"))
        for p, kind in base[1:]:
            flow_comps.append(Component(FLOW, kind, cfg.pts_extra_base, TIER_NAMES[q[kind].final_tier],
                                        "additional flow signal"))
        if "RELAY" in q:
            if r.repeated_episodes >= cfg.repeated_min_episodes:
                flow_comps.append(Component(FLOW, "REPEATED", cfg.pts_repeated, None,
                                            f"{r.repeated_episodes} pass-through episodes"))
            if r.corroborated:
                flow_comps.append(Component(FLOW, "CORROBORATED_LAYERING", cfg.pts_corroborated, None,
                                            f"{len(r.corroborated['accounts'])} rapid relays in one traced path"))
            elif r.chain:
                flow_comps.append(Component(FLOW, "CHAIN", cfg.pts_chain, None,
                                            f"{len(r.chain['accounts'])} relays in one traced path"))
        if "LAYERED_RECEIPT" in q and q["LAYERED_RECEIPT"].metrics.get("consolidation"):
            flow_comps.append(Component(FLOW, "CONSOLIDATION", cfg.pts_consolidation, None,
                                        "receives layered funds from several chains"))
    comps += _capped(flow_comps, cfg.cap_flow)

    if "ROUND_TRIP" in q:
        comps += _capped([Component(CIRCULARITY, "ROUND_TRIP", cfg.pts_round_trip[q["ROUND_TRIP"].final_tier],
                                    TIER_NAMES[q["ROUND_TRIP"].final_tier], "circular money flow",
                                    q["ROUND_TRIP"].finding)], cfg.cap_circularity)

    if "IDENTITY" in q:
        sig = q["IDENTITY"]
        types = sig.metrics["link_types"]
        strong = any(t in ("device", "kyc") for t in types)
        id_comps = [Component(IDENTITY, "SHARED_ATTRIBUTE",
                              cfg.pts_identity_strong if strong else cfg.pts_identity_ip,
                              "STRONG" if strong else "WEAK_EVIDENCE",
                              ("shared " + "/".join(types)) if strong else "shared IP only (weak evidence)",
                              sig.finding)]
        for extra in types[1:]:
            id_comps.append(Component(IDENTITY, "ADDITIONAL_LINK_TYPE", cfg.pts_identity_extra, None,
                                      f"also shares {extra}"))
        comps += _capped(id_comps, cfg.cap_identity)

    r.components = comps
    r.score = sum(c.points for c in comps)
    r.families = sorted({c.family for c in comps})
    r.flagged = r.score > 0
    if r.flagged:
        r.severity = "HIGH" if r.score >= cfg.severity_high else "MEDIUM" if r.score >= cfg.severity_medium else "LOW"


def _capped(comps: list[Component], cap: int) -> list[Component]:
    """Trim components so the family total never exceeds its cap (cap shown as a reduction)."""
    total = sum(c.points for c in comps)
    if total > cap:
        comps = comps + [Component(comps[0].family, "FAMILY_CAP", cap - total, None, f"family capped at {cap}")]
    return comps
