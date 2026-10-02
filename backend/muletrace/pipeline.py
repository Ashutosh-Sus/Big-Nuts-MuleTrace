"""Runs the fixed 12-stage pipeline (ARCHITECTURE §2). Pure function of (transactions, config)."""
from __future__ import annotations

from dataclasses import dataclass, field

from . import cases as cases_mod
from . import explain, identity as identity_mod, profiles, scoring, signals as sig_mod
from .config import DAY, Config
from .flow import FlowGraph, build_episodes, build_links
from .ingest import SYMBOLS, Txn


@dataclass
class Analysis:
    cfg: Config
    ds: profiles.Dataset
    fg: FlowGraph
    raw: dict
    identity: identity_mod.IdentityResult
    cases: cases_mod.CaseResult
    results: dict[str, scoring.AccountResult]
    round_trip_findings: list
    reciprocal: dict
    fmt: explain.Fmt
    currency: str
    history_limited: bool
    engine: str
    obs_cache: dict = field(default_factory=dict)
    flagged_cases: set = field(default_factory=set)

    def in_flagged_case(self, a: str) -> bool:
        return any(c in self.flagged_cases for c in self.cases.case_of.get(a, []))

    def role(self, a: str) -> str | None:
        """Structural role shown to analysts: only within cases that contain a flagged account."""
        if self.ds.accounts[a].pooled:
            return "POOLED"
        r = self.cases.roles.get(a)
        if r == "CLUSTER_MEMBER" or self.in_flagged_case(a) or self.results[a].flagged:
            return r
        return None

    def observations(self, a: str) -> list[dict]:
        if a not in self.obs_cache:
            self.obs_cache[a] = explain.observations(a, self)
        return self.obs_cache[a]


def analyze(txns: list[Txn], cfg: Config, currency: str = "INR") -> Analysis:
    ds = profiles.build(txns, cfg)                                      # 2, 3
    if cfg.engine == "window":
        from .fallback import build_window_engine
        fg, raw, rt_findings, reciprocal = build_window_engine(ds)
    else:
        fg = build_links(ds)                                            # 4
        build_episodes(ds, fg)                                          # 5
        raw = {"RELAY": sig_mod.relay_signals(ds, fg)}                  # 6
        raw["HUB"] = sig_mod.hub_signals(ds, fg)
        raw["LAYERED_RECEIPT"] = sig_mod.receipt_signals(
            ds, fg, {a: s.raw_tier for a, s in raw["RELAY"].items()})
        raw["ROUND_TRIP"], rt_findings, reciprocal = sig_mod.round_trip_signals(ds, fg)
    ident = identity_mod.build(ds)
    cres = cases_mod.build(ds, fg, raw, ident.signals)                  # 7, 8
    scoring.apply_mitigations(ds, fg, cres)                             # 9
    results = scoring.score(ds, fg, raw, ident, cres)                   # 10, 11
    fmt = explain.Fmt(currency, SYMBOLS.get(currency, currency + " "), cfg.local_offset_minutes)
    an = Analysis(cfg, ds, fg, raw, ident, cres, results, rt_findings, reciprocal, fmt, currency,
                  ds.span < cfg.relationship_days * DAY, cfg.engine)
    _finalise(an)                                                       # 12
    return an


def _finalise(an: Analysis) -> None:
    txns = an.ds.txns
    an.flagged_cases = {c.id for c in an.cases.cases if any(an.results[m].flagged for m in c.members)}
    for a, r in an.results.items():
        reasons = {k: explain.signal_reason(s, an.fmt, txns) for k, s in r.signals.items()}
        for c in r.components:
            c.detail = explain.component_detail(c, reasons, r, an.fmt)
        if r.components:
            top = max((c for c in r.components if c.points > 0), key=lambda c: c.points)
            r.primary_reason = top.detail
        exposure = 0
        for kind, s in r.signals.items():
            if not s.qualifies:
                continue
            m = s.metrics
            exposure = max(exposure, m.get("forwarded") or 0, m.get("matched") or 0,
                           m.get("total_received") or 0, m.get("sent") or 0,
                           (m.get("window") or {}).get("outflow_in_window") or 0)
        r.exposure = exposure
