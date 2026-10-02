"""Deterministic demonstration dataset: a month of ordinary activity with embedded mule networks
and look-alike legitimate behaviour. Same seed -> byte-identical CSV."""
from __future__ import annotations

import csv
import io
import random
from datetime import datetime, timedelta

BASE = datetime(2024, 3, 1)
DAYS = 31
FIELDS = ["txn_id", "timestamp", "sender_account", "receiver_account", "amount", "currency", "channel",
          "sender_device_id", "sender_ip", "sender_kyc_id", "receiver_device_id", "receiver_ip",
          "receiver_kyc_id", "sender_account_created", "receiver_account_created"]

# Accounts the presenter refers to (see DEMO.md)
HERO = {
    "V1": "AC2207", "V2": "AC3318", "EMP_V2": "AC9002",
    "M1": "AC5521", "M2": "AC5530", "M3": "AC5547", "M4": "AC5562", "M5": "AC5579",
    "C1": "AC6610", "C2": "AC6624", "C3": "AC6637", "C4": "AC6651",
}
DECOYS = {"MERCHANT": "AC8800", "MERCHANT_BANK": "AC8801", "PAYROLL": "AC7100", "PARENT": "AC7000",
          "NEAR_MISS": "AC6101", "OFFICE_IP": "10.20.0.15"}


class Gen:
    def __init__(self, seed: int):
        self.rng = random.Random(seed)
        self.rows: list[dict] = []
        self.acct: dict[str, dict] = {}
        self.n = 0

    def account(self, aid: str, created: datetime, device: str | None = None, ip: str | None = None,
                kyc: str | None = None) -> str:
        h = self.rng.randrange(16 ** 6)
        self.acct[aid] = {"created": created, "device": device or f"DV-{h:06X}",
                          "ip": ip or f"49.{36 + h % 40}.{h % 251}.{(h >> 8) % 251}",
                          "kyc": kyc or f"KYC-{self.rng.randrange(16 ** 8):08X}"}
        return aid

    def tx(self, s: str, r: str, amount: float, when: datetime, channel: str = "UPI") -> None:
        self.n += 1
        a, b = self.acct[s], self.acct[r]
        self.rows.append({
            "txn_id": f"TX{100000 + self.n}", "timestamp": when.strftime("%Y-%m-%d %H:%M:%S"),
            "sender_account": s, "receiver_account": r, "amount": f"{amount:.2f}", "currency": "INR",
            "channel": channel,
            "sender_device_id": a["device"], "sender_ip": a["ip"], "sender_kyc_id": a["kyc"],
            "receiver_device_id": b["device"], "receiver_ip": b["ip"], "receiver_kyc_id": b["kyc"],
            "sender_account_created": a["created"].strftime("%Y-%m-%d"),
            "receiver_account_created": b["created"].strftime("%Y-%m-%d"),
        })


def at(day: int, hh: int, mm: int = 0, ss: int = 0) -> datetime:
    return BASE + timedelta(days=day, hours=hh, minutes=mm, seconds=ss)


def generate(seed: int = 20240301) -> bytes:
    g = Gen(seed)
    rng = g.rng
    old = lambda: BASE - timedelta(days=rng.randint(700, 2200))

    # ---- ordinary population ------------------------------------------------
    people = [g.account(f"AC{1000 + i}", old()) for i in range(120)]
    office = people[:22]
    for p in office:
        g.acct[p]["ip"] = DECOYS["OFFICE_IP"]
    employers = [g.account(f"AC{9000 + k}", old()) for k in range(4)]
    landlords = [g.account(f"AC{9100 + k}", old()) for k in range(8)]
    shops = [g.account(f"AC{9200 + k}", old()) for k in range(10)]
    utilities = [g.account(f"AC{9300 + k}", old()) for k in range(3)]

    v1 = g.account(HERO["V1"], BASE - timedelta(days=1500), ip=DECOYS["OFFICE_IP"])
    v2 = g.account(HERO["V2"], BASE - timedelta(days=1100))
    emp_v2 = g.account(HERO["EMP_V2"], old())
    population = people + [v1, v2]
    employer_of = {p: employers[i % len(employers)] for i, p in enumerate(people)}
    employer_of[v1] = employers[0]
    employer_of[v2] = emp_v2
    landlord_of = {p: landlords[i % len(landlords)] for i, p in enumerate(population)}

    # salaries (day 0 and day 30, V2's on day 24 is the scam day — see below), rent, utilities
    for p in population:
        salary = rng.randint(35, 120) * 1000
        for d in (0, 30):
            if not (p == v2 and d == 30):
                g.tx(employer_of[p], p, salary, at(d, 9, rng.randint(0, 50)), "NEFT")
        g.tx(p, landlord_of[p], rng.randint(10, 28) * 1000, at(rng.randint(2, 5), rng.randint(10, 20), rng.randint(0, 59)), "IMPS")
        g.tx(p, utilities[rng.randrange(3)], rng.randint(800, 3500), at(rng.randint(6, 12), 18, rng.randint(0, 59)))
    g.tx(emp_v2, v2, 125_000, at(24, 9, 40), "NEFT")          # V2 salary 21 min before the scam transfer

    # everyday spending and P2P
    for d in range(DAYS):
        for p in population:
            if rng.random() < 0.30:
                g.tx(p, shops[rng.randrange(len(shops))], rng.randint(120, 2800),
                     at(d, rng.randint(8, 21), rng.randint(0, 59), rng.randint(0, 59)))
            if rng.random() < 0.04:
                q = population[rng.randrange(len(population))]
                if q != p:
                    g.tx(p, q, rng.randint(5, 60) * 100, at(d, rng.randint(9, 22), rng.randint(0, 59)))

    # ---- decoy: high-volume merchant (pooled) with daily settlement -----------
    merch = g.account(DECOYS["MERCHANT"], BASE - timedelta(days=1800))
    mbank = g.account(DECOYS["MERCHANT_BANK"], BASE - timedelta(days=1800))
    customers = [g.account(f"AC{1200 + i}", old()) for i in range(70)]
    for d in range(DAYS):
        day_total = 0
        for _ in range(9):
            c = (customers + population)[rng.randrange(len(customers) + len(population))]
            amt = rng.randint(200, 3000)
            day_total += amt
            g.tx(c, merch, amt, at(d, rng.randint(9, 20), rng.randint(0, 59), rng.randint(0, 59)))
        g.tx(merch, mbank, round(day_total * 0.95), at(d, 21, 30), "NEFT")

    # ---- decoy: payroll company — funded, then fans out within minutes --------
    parent = g.account(DECOYS["PARENT"], BASE - timedelta(days=2500))
    payco = g.account(DECOYS["PAYROLL"], BASE - timedelta(days=2000))
    staff = [g.account(f"AC{7200 + i}", old()) for i in range(24)]
    for d in (0, 30):
        g.tx(parent, payco, 24 * 75_000, at(d, 8, 30), "NEFT")
        for i, st in enumerate(staff):
            g.tx(payco, st, 74_500, at(d, 8, 40 + i // 4), "NEFT")

    # ---- decoy: isolated near-threshold relay ---------------------------------
    nm_src = g.account("AC6100", old())
    nm = g.account(DECOYS["NEAR_MISS"], old())
    nm_dst = g.account("AC6102", old())
    g.tx(nm_src, nm, 200_000, at(18, 11, 0), "IMPS")
    g.tx(nm, nm_dst, 178_000, at(18, 11, 41), "IMPS")

    # ---- HERO network (day 24) ------------------------------------------------
    dev = "DV-7731AA"
    m1 = g.account(HERO["M1"], at(18, 0), device=dev)
    m2 = g.account(HERO["M2"], at(17, 0), device=dev)
    m3 = g.account(HERO["M3"], at(19, 0), device=dev, kyc="KYC-19C0FFEE")
    m4 = g.account(HERO["M4"], at(16, 0), device=dev)
    m5 = g.account(HERO["M5"], at(15, 0), kyc="KYC-19C0FFEE")
    c1 = g.account(HERO["C1"], at(10, 0))
    c2 = g.account(HERO["C2"], at(12, 0))
    c3 = g.account(HERO["C3"], at(11, 0))
    c4 = g.account(HERO["C4"], at(13, 0))
    g.tx(m1, v1, 1, at(24, 9, 55))                       # account verification ping
    g.tx(v2, m5, 120_000, at(24, 10, 1), "IMPS")
    g.tx(v1, m1, 480_000, at(24, 10, 2), "IMPS")
    g.tx(m1, m2, 478_000, at(24, 10, 5), "IMPS")
    g.tx(m5, m2, 119_000, at(24, 10, 8), "IMPS")
    g.tx(m2, m3, 295_000, at(24, 10, 11), "IMPS")
    g.tx(m2, m4, 300_000, at(24, 10, 12), "IMPS")
    g.tx(m3, c1, 140_000, at(24, 10, 15), "IMPS")
    g.tx(m4, c2, 150_000, at(24, 10, 16), "IMPS")
    g.tx(m3, c2, 152_000, at(24, 10, 18), "IMPS")
    g.tx(m4, c3, 148_000, at(24, 10, 19), "IMPS")
    g.tx(c2, m2, 240_000, at(24, 13, 30), "IMPS")      # funds circle back to the hub
    g.tx(m2, c4, 238_000, at(24, 13, 34), "IMPS")
    g.tx(m1, v1, 499, at(24, 11, 30))                    # token "refund"
    for k in range(3):
        g.tx(m2, shops[k], 199 + 100 * k, at(23, 12 + k, 10))   # decoy everyday spending

    # ---- ring 2: fan-in hub feeding relays (day 27) -------------------------------
    hub = g.account("AC4400", at(20, 0))
    victims2 = [g.account(f"AC{3400 + i}", old()) for i in range(5)]
    relays2 = [g.account(f"AC{4410 + i}", at(21, 0)) for i in range(3)]
    outs2 = [g.account(f"AC{4420 + i}", at(19, 0)) for i in range(3)]
    for i, v in enumerate(victims2):
        g.tx(v, hub, rng.randint(60, 110) * 1000, at(27, 14, 3 + i * 4), "IMPS")
    hub_in = sum(float(r["amount"]) for r in g.rows if r["receiver_account"] == hub)
    for i, (r, o) in enumerate(zip(relays2, outs2)):
        part = round(hub_in * 0.97 / 3)
        g.tx(hub, r, part, at(27, 14, 26 + i * 3), "IMPS")
        g.tx(r, o, part - 300, at(27, 14, 34 + i * 3), "IMPS")

    # ---- ring 3: circular flow with value decay (day 21) -----------------------
    ring = [g.account(f"AC{3500 + i}", at(5 + i, 0)) for i in range(4)]
    amt = 260_000
    t = at(21, 11, 0)
    for i in range(4):
        g.tx(ring[i], ring[(i + 1) % 4], round(amt), t, "IMPS")
        amt *= 0.86
        t += timedelta(minutes=70 + 15 * i)

    # ---- pre-positioned accounts: new, one shared device, barely used ------------
    for i in range(5):
        a = g.account(f"AC{5600 + i}", at(22 + i % 3, 0), device="DV-4410EE")
        g.tx(a, shops[i % len(shops)], 100 + 25 * i, at(26, 10 + i, 5))

    # ---- weak evidence: new accounts sharing only an IP ----------------------------
    for i in range(4):
        a = g.account(f"AC{5700 + i}", at(20, 0), ip="103.77.12.9")
        g.tx(a, shops[(i + 3) % len(shops)], 300 + 10 * i, at(25, 15, i * 7))

    # ---- malformed rows for the ingestion report -------------------------------------
    rows = sorted(g.rows, key=lambda r: (r["timestamp"], r["txn_id"]))
    bad = [
        {**rows[10], "txn_id": "TX900001", "timestamp": "31-02-2024 25:61"},
        {**rows[11], "txn_id": "TX900002", "amount": "-4500"},
        {**rows[12], "txn_id": "TX900003", "receiver_account": rows[12]["sender_account"]},
        dict(rows[13]),                                                   # exact duplicate
        {**rows[14], "amount": "99999.00"},                              # conflicting duplicate
        {**rows[15], "txn_id": "TX900006", "sender_account": ""},
        {**rows[16], "txn_id": "TX900007", "amount": "twelve hundred"},
    ]
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=FIELDS, lineterminator="\n")
    w.writeheader()
    for r in rows + bad:
        w.writerow(r)
    return buf.getvalue().encode()
