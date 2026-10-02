"""Stages 2–3: account profiles, establishment, relationships, pooled classification (ARCHITECTURE §4)."""
from __future__ import annotations

from dataclasses import dataclass, field

from .config import DAY, Config
from .ingest import Txn

ESTABLISHED, NEW, UNKNOWN, NOVEL = "ESTABLISHED", "NEW", "UNKNOWN", "NOVEL"


@dataclass
class Account:
    id: str
    first_seen: int
    last_seen: int
    in_txns: list[int] = field(default_factory=list)
    out_txns: list[int] = field(default_factory=list)
    in_total: int = 0
    out_total: int = 0
    in_cps: set[str] = field(default_factory=set)
    out_cps: set[str] = field(default_factory=set)
    attrs: dict[str, set[str]] = field(default_factory=lambda: {"device": set(), "ip": set(), "kyc": set()})
    created: int | None = None
    establishment: str = UNKNOWN
    establishment_basis: str = ""
    pooled: bool = False

    @property
    def counterparties(self) -> set[str]:
        return self.in_cps | self.out_cps

    @property
    def age_days(self) -> float | None:
        if self.created is None:
            return None
        return (self.first_seen - self.created) / DAY


@dataclass
class Dataset:
    txns: list[Txn]
    accounts: dict[str, Account]
    cfg: Config
    start: int
    end: int
    first_contact: dict[tuple[str, str], int]
    establishment_evidence: bool

    @property
    def span(self) -> int:
        return self.end - self.start

    def relationship(self, a: str, b: str, t: int) -> str:
        """State of the (a, b) relationship at time t."""
        key = (a, b) if a <= b else (b, a)
        first = self.first_contact.get(key, t)
        window = self.cfg.relationship_days * DAY
        if first <= t - window:
            return ESTABLISHED
        if t >= self.start + window:
            return NOVEL
        return UNKNOWN

    def sorted_accounts(self) -> list[Account]:
        return [self.accounts[k] for k in sorted(self.accounts)]


def build(txns: list[Txn], cfg: Config) -> Dataset:
    accounts: dict[str, Account] = {}
    first_contact: dict[tuple[str, str], int] = {}

    def acct(aid: str, ts: int) -> Account:
        a = accounts.get(aid)
        if a is None:
            a = accounts[aid] = Account(aid, ts, ts)
        a.first_seen = min(a.first_seen, ts)
        a.last_seen = max(a.last_seen, ts)
        return a

    for t in txns:
        s = acct(t.sender, t.ts)
        r = acct(t.receiver, t.ts)
        s.out_txns.append(t.idx)
        s.out_total += t.amount
        s.out_cps.add(t.receiver)
        r.in_txns.append(t.idx)
        r.in_total += t.amount
        r.in_cps.add(t.sender)
        for acc, dev, ip, kyc, created in ((s, t.s_device, t.s_ip, t.s_kyc, t.s_created),
                                           (r, t.r_device, t.r_ip, t.r_kyc, t.r_created)):
            if dev:
                acc.attrs["device"].add(dev)
            if ip:
                acc.attrs["ip"].add(ip)
            if kyc:
                acc.attrs["kyc"].add(kyc)
            if created is not None:
                acc.created = created if acc.created is None else min(acc.created, created)
        key = (t.sender, t.receiver) if t.sender <= t.receiver else (t.receiver, t.sender)
        if key not in first_contact:
            first_contact[key] = t.ts

    start = txns[0].ts if txns else 0
    end = txns[-1].ts if txns else 0
    any_created = any(a.created is not None for a in accounts.values())
    long_span = (end - start) >= cfg.establishment_span_days * DAY
    ds = Dataset(txns, accounts, cfg, start, end, first_contact, any_created or long_span)

    for a in accounts.values():
        a.in_txns.sort()
        a.out_txns.sort()
        if a.created is not None:
            new = a.age_days is not None and a.age_days <= cfg.new_account_days
            a.establishment = NEW if new else ESTABLISHED
            a.establishment_basis = f"account opened {max(0, round(a.age_days or 0))} days before first activity"
        elif long_span:
            history = (a.last_seen - a.first_seen) / DAY
            a.establishment = ESTABLISHED if history >= cfg.establishment_span_days else NEW
            a.establishment_basis = f"{history:.0f} days of observed activity (no opening date in data)"
        else:
            a.establishment = UNKNOWN
            a.establishment_basis = "account age unavailable"
        a.pooled = (len(a.counterparties) >= cfg.pooled_min_counterparties
                    and (a.last_seen - a.first_seen) >= cfg.pooled_min_span)
    return ds
