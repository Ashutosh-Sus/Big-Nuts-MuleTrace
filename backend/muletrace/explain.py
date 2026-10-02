"""Stage 12: plain-language reasons, evidence chains and observations (ARCHITECTURE §9).

Every sentence is generated from computed metrics only.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .cases import CONTRA, INDICATED
from .flow import TIER_NAMES

VICTIM_TEXT = "Indicators consistent with a possible victim. This is not a determination."


class Fmt:
    def __init__(self, currency: str, symbol: str, offset_minutes: int):
        self.currency = currency
        self.symbol = symbol
        self.tz = timezone(timedelta(minutes=offset_minutes))

    def money(self, minor: int | float) -> str:
        major = int(round(minor)) // 100
        if self.currency == "INR":
            s = str(abs(major))
            if len(s) > 3:
                head, tail = s[:-3], s[-3:]
                groups = []
                while len(head) > 2:
                    groups.insert(0, head[-2:])
                    head = head[:-2]
                if head:
                    groups.insert(0, head)
                s = ",".join(groups) + "," + tail
            return f"{'-' if major < 0 else ''}{self.symbol}{s}"
        return f"{self.symbol}{major:,}"

    def time(self, ts: int) -> str:
        return datetime.fromtimestamp(ts, self.tz).strftime("%d %b %H:%M")

    def clock(self, ts: int) -> str:
        return datetime.fromtimestamp(ts, self.tz).strftime("%H:%M")

    @staticmethod
    def duration(seconds: float) -> str:
        s = int(round(seconds))
        if s < 60:
            return f"{s} s"
        if s < 3600:
            return f"{s // 60} min"
        if s < 86400:
            h, m = divmod(s // 60, 60)
            return f"{h} h {m} min" if m else f"{h} h"
        d, rem = divmod(s, 86400)
        return f"{d} d {rem // 3600} h" if rem >= 3600 else f"{d} d"

    @staticmethod
    def pct(x: float) -> str:
        return f"{x * 100:.1f}%".replace(".0%", "%")


def signal_reason(sig, f: Fmt, txns) -> str:
    m = sig.metrics
    if sig.kind == "RELAY":
        if m.get("kind") == "window" or not m.get("forwarded"):
            w = m.get("window") or {}
            return (f"Received {f.money(w.get('lot_amount', m['inflow']))} and sent "
                    f"{f.money(w.get('outflow_in_window', m['outflow']))} onward within "
                    f"{f.duration(w.get('bound_seconds', m['dwell_seconds']))} "
                    f"({f.pct(w.get('conservation', 0))} amount match).")
        return (f"Received {f.money(m['inflow'])} and forwarded {f.money(m['forwarded'])} "
                f"({f.pct(m['conservation'])} conserved) after an average of {f.duration(m['dwell_seconds'])} "
                f"({f.time(m['start'])}–{f.clock(m['end'])}).")
    if sig.kind == "HUB":
        return (f"Funds from {len(m['senders'])} senders ({f.money(m['inflow'])}) were passed to "
                f"{len(m['receivers'])} receivers ({f.money(m['outflow'])}) between {f.time(m['start'])} "
                f"and {f.clock(m['end'])}; {f.pct(m['conservation'])} of the money moved on.")
    if sig.kind == "LAYERED_RECEIPT":
        path = " → ".join(m["path_accounts"])
        extra = (f" Received layered funds from {len(m['upstream_senders'])} separate chains."
                 if m.get("consolidation") else "")
        return (f"Received {f.money(m['amount'])} that had passed through {m['relays_upstream']} relay accounts "
                f"in {f.duration(m['span_seconds'])} ({path}) and kept it.{extra}")
    if sig.kind == "ROUND_TRIP":
        cyc = " → ".join(m["cycle"])
        rep = f" Seen {m['occurrences']} times." if m.get("occurrences", 1) > 1 else ""
        return (f"{f.money(m['returned'])} of {f.money(m['sent'])} ({f.pct(m['ratio'])}) returned to its "
                f"starting account in {f.duration(m['span_seconds'])}: {cyc}.{rep}")
    if sig.kind == "IDENTITY":
        parts = []
        for v in m["values"]:
            who = ", ".join(v["shared_with"][:5]) + (f" +{len(v['shared_with']) - 5}" if len(v["shared_with"]) > 5 else "")
            label = {"device": "device", "kyc": "KYC identifier", "ip": "IP address"}[v["type"]]
            parts.append(f"{label} {v['value']} with {who}")
        tail = ""
        if m.get("ip_only"):
            tail = " Weak evidence: IP only"
            if m.get("establishment") == "UNKNOWN":
                tail += "; account age unknown, shared network not ruled out"
            tail += "."
        new = {"NEW": " New account", "UNKNOWN": "", "ESTABLISHED": " Established account"}[m["establishment"]]
        new = f"{new} ({m['establishment_basis']})." if new else ""
        return "Shares " + "; ".join(parts) + "." + new + tail
    return ""


def component_detail(comp, sig_reason: dict[str, str], r, f: Fmt) -> str:
    if comp.rule in sig_reason:
        return sig_reason[comp.rule]
    if comp.rule == "SHARED_ATTRIBUTE":
        return sig_reason.get("IDENTITY", comp.detail)
    if comp.rule in ("CHAIN", "CORROBORATED_LAYERING"):
        p = r.corroborated if comp.rule == "CORROBORATED_LAYERING" else r.chain
        return (f"Part of a traced path through {len(p['accounts'])} relay accounts "
                f"({' → '.join(p['accounts'])}) spanning {f.duration(p['span'])}.")
    return comp.detail


def observations(a, analysis) -> list[dict]:
    """Considered-but-not-scored evidence for one account ("why not flagged")."""
    ds, fg, cases, f = analysis.ds, analysis.fg, analysis.cases, analysis.fmt
    acc = ds.accounts[a]
    r = analysis.results[a]
    obs: list[dict] = []

    if acc.pooled:
        obs.append({"kind": "POOLED", "text": (
            f"Pooled account: {len(acc.counterparties)} counterparties over "
            f"{f.duration(acc.last_seen - acc.first_seen)}. Money is mixed beyond reliable attribution, "
            "so traced flows stop here. Detection on this account itself stays active.")})

    if a in cases.origin_of and analysis.in_flagged_case(a):
        ind = cases.indicator[a]
        text = ("Observed role: likely origin of funds — money it sent into the flow came from its own "
                "balance or long-standing relationships, not from a recent inflow.")
        if ind["status"] == INDICATED:
            had_flow = any(k in r.signals for k in ("RELAY", "HUB", "LAYERED_RECEIPT"))
            obs.append({"kind": "ORIGIN_ZEROED", "text": text
                        + (" Its flow signals are not scored. " if had_flow else " ") + VICTIM_TEXT})
        else:
            obs.append({"kind": "ORIGIN", "text": text + " Not consistent with a possible victim: "
                        + "; ".join(ind["reasons"]) + "."})

    for kind, sig in r.signals.items():
        if sig.qualifies:
            continue
        reason = signal_reason(sig, f, ds.txns)
        if "ORIGIN_ZEROED" in sig.notes:
            continue
        if "ISOLATED_RELAY" in sig.notes:
            tail = (" Pass-through is not scored separately: single episode, not linked to other "
                    "pass-through accounts." if r.flagged else
                    " Single episode, not linked to other pass-through accounts — consistent with "
                    "ordinary payments; not part of a chain.")
            obs.append({"kind": "ISOLATED_RELAY", "text": reason + tail})
        elif "UNCORROBORATED" in sig.notes:
            obs.append({"kind": "UNCORROBORATED", "text": f"{kind.replace('_', ' ').title()} at moderate strength "
                        f"without corroboration: {reason}"})
        elif sig.raw_tier is not None and sig.final_tier is None:
            pass  # mitigated away — reported below per episode
        elif sig.final_tier == 2 or sig.raw_tier == 2:
            obs.append({"kind": "NEAR_MISS", "text": f"Below reporting strength (weak): {reason}"})

    for eid in fg.episodes_by_account.get(a, []):
        ep = fg.episodes[eid]
        if ep.mitigations and ep.tier is not None:
            before = TIER_NAMES[ep.tier]
            after = TIER_NAMES[ep.final_tier] if ep.final_tier is not None else "not reportable"
            why = []
            if "ESTABLISHED_FUNDING" in ep.mitigations:
                why.append("the money came from counterparties with at least "
                           f"{ds.cfg.relationship_days} days of prior history")
            if "ESTABLISHED_PAYEES" in ep.mitigations:
                why.append(f"it went to payees paid at least {ds.cfg.relationship_days} days earlier")
            obs.append({"kind": "MITIGATED", "text": (
                f"Pass-through episode on {f.time(ep.start)} ({f.money(ep.inflow)} in, {f.money(ep.outflow)} out) "
                f"downgraded {before} → {after} because " + " and ".join(why) + "."), "episode": eid})

    attr_label = {"device": "Device", "ip": "IP address", "kyc": "KYC identifier"}
    for g in analysis.infra_groups_of(a):
        share = len(g.established) / len(g.sharers)
        obs.append({"kind": "INFRA_ATTRIBUTE", "text": (
            f"{attr_label[g.attr]} {g.value} is shared by {len(g.sharers)} accounts, {f.pct(share)} of them "
            "established — treated as shared infrastructure, not as evidence.")})

    for rec in analysis.reciprocal.get(a, [])[:3]:
        obs.append({"kind": "RECIPROCAL", "text": (
            f"Two-party back-and-forth with {rec['with']} ({f.money(rec['returned'])} returned) — "
            "common for refunds and repayments; recorded, not scored.")})

    if analysis.history_limited:
        obs.append({"kind": "HISTORY_UNAVAILABLE", "text": (
            f"The dataset spans {f.duration(ds.span)}; relationship-history checks need at least "
            f"{ds.cfg.relationship_days} days, so mitigations based on prior relationships are unavailable.")})

    if not obs and not r.flagged:
        obs.append({"kind": "NO_PATTERN", "text": (
            "No pass-through, fan-in/fan-out, circular or shared-attribute pattern was found for this account.")})
    return obs


def indicator_view(a: str, analysis) -> dict:
    cases = analysis.cases
    if a not in cases.indicator or not analysis.in_flagged_case(a):
        return {"status": "NOT_ASSESSED", "text": None, "reasons": []}
    ind = cases.indicator[a]
    return {"status": ind["status"],
            "text": VICTIM_TEXT if ind["status"] == INDICATED else "Not consistent with a possible victim.",
            "reasons": ind["reasons"]}


__all__ = ["Fmt", "signal_reason", "component_detail", "observations", "indicator_view", "CONTRA", "VICTIM_TEXT"]
