# MuleTrace

**Follow the money through a mule network — and know when not to.**

A fraud reaches a victim's account once, then the money is layered through three to six accounts
within minutes, each transfer looking ordinary. MuleTrace ingests a transaction CSV, links every
outgoing payment to the incoming money that funded it, and flags the structures layering leaves
behind:

- **fan-in then fan-out** within a short window
- **circular transfers** — money that actually comes back, not just a loop in the graph
- **chains of pass-through accounts** that keep near-zero balances
- **clusters of new accounts** sharing a device, IP or KYC attribute

Every flagged account gets a deterministic evidence score and a plain-language reason. An analyst
can expand the network, trace where money came from and where it went, read the timeline, and
mark the account **Confirmed** or **Cleared** with an audit trail.

## Quick start

Requirements: Python 3.11+ and Node 18+ (only for the first build). Everything runs offline.

```powershell
.\start.ps1            # Windows
```
```sh
./start.sh             # macOS / Linux
```

The script creates the Python environment, builds the console once, and opens
<http://127.0.0.1:8000> with the bundled demo dataset loaded. Afterwards `python run.py` is enough
(`backend\.venv\Scripts\python run.py` on Windows). Options: `--port 8080`, `--engine window`
(fallback engine), `--open`.

Manual setup:

```sh
python -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements.txt      # Windows: backend\.venv\Scripts\pip
cd frontend && npm install && npm run build && cd ..
backend/.venv/bin/python run.py
```

## How it works

```
CSV ─► ingest ─► profiles ─► FIFO flow links ─► episodes ─► signals ─► cases & roles
                                                              │
     explanations ◄─ scoring ◄─ qualification ◄─ mitigations ◄┘
```

1. **Fund-flow engine.** Each account's inflows become *lots*; outflows consume them first-in
   first-out, producing *flow links* ("₹4,17,800 of TX104 left as TX107 after 4 min"). Multi-hop
   traces are computed with exact fractions, so the money in a trace always adds up.
2. **Episodes and tiers.** Linked inflows and outflows form episodes, graded STRONG / MODERATE / WEAK
   by dwell time and conservation — keeping 11 % instead of 10 % moves an account down a tier, it does
   not make it invisible.
3. **Signals.** Pass-through, fan-in → fan-out hub, layered receipt (cash-out), money-flow round trip,
   and shared-attribute clusters with infrastructure detection.
4. **Roles.** Each account in a case gets an observed role — likely origin, relay, hub, collector,
   distributor, sink, pooled. Origin accounts (often victims) are protected from flow scoring; the UI
   says *"Indicators consistent with a possible victim. This is not a determination."*
5. **False-positive defence.** Relationship history (≥ 7 days) downgrades payroll and settlement
   patterns; isolated single pass-throughs are not chains; shared office / campus networks are
   recognised; pooled accounts stop attribution. None of these can erase corroborated layering.
6. **Score.** Three independent evidence families — money flow (max 60), circularity (20), shared
   identity (20). HIGH ≥ 60, MEDIUM ≥ 35. The score is an evidence-strength index, **not a probability
   of fraud**, and every point links to a rule, metrics and transactions.

Full specification: [ARCHITECTURE.md](ARCHITECTURE.md).

## Input format

| Column | |
|---|---|
| `timestamp`, `sender_account`, `receiver_account`, `amount` | required |
| `txn_id` | recommended (derived from row content if absent) |
| `currency`, `channel` | optional |
| `sender_/receiver_device_id`, `_ip`, `_kyc_id` | optional — enable shared-attribute clustering |
| `sender_/receiver_account_created` | optional — new-account determination |
| `sender_/receiver_balance_before/after` | optional |

Common alternative headers (`from`/`to`, `nameOrig`/`nameDest`, `step`, `isFraud`, …) are recognised
automatically. Integer `step` columns are treated as hour indices, not epoch seconds. Bad rows are
rejected individually and listed in the ingestion report.

## Tests

```sh
backend/.venv/bin/python -m pytest -q backend/tests
```

Covers flow-engine invariants (conservation, determinism, row-order independence, same-timestamp
and pooled-boundary behaviour), baseline patterns, an adversarial suite (threshold evasion, slow and
split layering, converging paths, decoys, shared infrastructure, correlated evidence, victim
contamination, merchant and payroll camouflage, temporal-ordering traps, fragmentation, decaying
round trips, attribute laundering, missing data) and regression cases from design review.

If a dataset carries a ground-truth label column: `python scripts/evaluate.py data.csv`
(detection never reads the label).

## Demo

See [DEMO.md](DEMO.md) for the presentation script. `data/demo.csv` is regenerated
deterministically by `python scripts/make_demo.py`; **Data → Reset demo** restores the starting state.

## Known limitations

- FIFO attribution is a convention, not ground truth.
- Flows slower than 72 hours are not linked; the first 7 days of a dataset are relationship warm-up.
- Accounts with ≥ 50 counterparties over ≥ 7 days are treated as pooled and are not traced through.
- Cash withdrawals and other-bank legs are outside the data; sinks are the edge of what is visible.
- One currency per dataset; no conversion.
- If a victim paid the first mule at least 7 days before the fraud, that mule is read as the likely origin
  of the flow (like a victim spending their salary); the rest of the chain and the cash-out are still flagged.
