"""Small deterministic scenario builder used by the test suite."""
from __future__ import annotations

import csv
import io
import random
from datetime import datetime, timedelta

from muletrace.config import DEFAULT, Config
from muletrace.ingest import parse_csv
from muletrace.pipeline import analyze

BASE = datetime(2024, 3, 1, 0, 0)
FIELDS = ["txn_id", "timestamp", "sender_account", "receiver_account", "amount",
          "sender_device_id", "sender_ip", "sender_kyc_id", "receiver_device_id", "receiver_ip",
          "receiver_kyc_id", "sender_account_created", "receiver_account_created",
          "sender_balance_before", "receiver_balance_before"]


def at(day: int, hh: int = 0, mm: int = 0, ss: int = 0) -> datetime:
    return BASE + timedelta(days=day, hours=hh, minutes=mm, seconds=ss)


class Scenario:
    def __init__(self, name: str = "s"):
        self.name = name
        self.rows: list[dict] = []
        self.created: dict[str, datetime] = {}
        self.attrs: dict[str, dict] = {}

    def account(self, acc: str, created: datetime | None = None, device=None, ip=None, kyc=None) -> "Scenario":
        if created is not None:
            self.created[acc] = created
        self.attrs[acc] = {"device": device, "ip": ip, "kyc": kyc}
        return self

    def tx(self, sender: str, receiver: str, amount: float, when: datetime, txn_id: str | None = None,
           **extra) -> "Scenario":
        tid = txn_id or f"{self.name}-{len(self.rows) + 1:05d}"
        row = {"txn_id": tid, "timestamp": when.strftime("%Y-%m-%d %H:%M:%S"),
               "sender_account": sender, "receiver_account": receiver, "amount": f"{amount:.2f}"}
        sa, ra = self.attrs.get(sender, {}), self.attrs.get(receiver, {})
        row["sender_device_id"] = sa.get("device") or ""
        row["sender_ip"] = sa.get("ip") or ""
        row["sender_kyc_id"] = sa.get("kyc") or ""
        row["receiver_device_id"] = ra.get("device") or ""
        row["receiver_ip"] = ra.get("ip") or ""
        row["receiver_kyc_id"] = ra.get("kyc") or ""
        row["sender_account_created"] = self.created[sender].strftime("%Y-%m-%d") if sender in self.created else ""
        row["receiver_account_created"] = self.created[receiver].strftime("%Y-%m-%d") if receiver in self.created else ""
        row.update({k: v for k, v in extra.items()})
        self.rows.append(row)
        return self

    def chain(self, accounts: list[str], amount: float, start: datetime, gap_minutes: float,
              keep: float = 0.005) -> "Scenario":
        """Money moves along accounts[0] -> ... -> accounts[-1], each hop keeping `keep`."""
        t = start
        amt = amount
        for a, b in zip(accounts, accounts[1:]):
            self.tx(a, b, round(amt), t)
            amt = amt * (1 - keep)
            t = t + timedelta(minutes=gap_minutes)
        return self

    def background(self, days: int = 30, people: int = 30, seed: int = 7, prefix: str = "BG") -> "Scenario":
        """Ordinary activity: salaries, rent, groceries among established accounts."""
        rng = random.Random(seed)
        employer, landlord, shop = f"{prefix}-EMP", f"{prefix}-LAND", f"{prefix}-SHOP"
        people_ids = [f"{prefix}-P{i:02d}" for i in range(people)]
        for p in people_ids + [employer, landlord, shop]:
            self.account(p, created=BASE - timedelta(days=900 + rng.randint(0, 400)))
        for d in range(0, days):
            for p in people_ids:
                if rng.random() < 0.35:
                    self.tx(p, shop, rng.randint(150, 2500), at(d, rng.randint(8, 21), rng.randint(0, 59)))
            if d % 30 == 0:
                for p in people_ids:
                    self.tx(employer, p, rng.randint(40, 90) * 1000, at(d, 9, rng.randint(0, 59)))
            if d % 30 == 3:
                for p in people_ids:
                    self.tx(p, landlord, rng.randint(12, 25) * 1000, at(d, 11, rng.randint(0, 59)))
        return self

    def csv_bytes(self, shuffle_seed: int | None = None) -> bytes:
        rows = list(self.rows)
        if shuffle_seed is not None:
            random.Random(shuffle_seed).shuffle(rows)
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=FIELDS + sorted({k for r in rows for k in r} - set(FIELDS)))
        w.writeheader()
        for r in rows:
            w.writerow(r)
        return buf.getvalue().encode()

    def run(self, cfg: Config = DEFAULT, shuffle_seed: int | None = None):
        res = parse_csv(self.csv_bytes(shuffle_seed), cfg)
        return analyze(res.txns, cfg, res.report["currency"])


def flagged(an) -> dict[str, tuple[int, str]]:
    return {a: (r.score, r.severity) for a, r in an.results.items() if r.flagged}


def kinds(an, acc: str) -> set[str]:
    return {k for k, s in an.results[acc].signals.items() if s.qualifies}
