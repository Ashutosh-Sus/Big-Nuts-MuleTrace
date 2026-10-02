# MuleTrace — demo script (≈ 3½ minutes)

Before presenting: `python run.py`, open <http://127.0.0.1:8000>, **Data → Reset demo**.
Set the analyst name (top right). Have a second laptop / recording as backup.

## Cast (demo dataset, 25 March)

| Account | Who | What the judges should see |
|---|---|---|
| `AC2207` | victim 1 (4-year account) | sends ₹4,80,000 at 10:02 — **likely origin, not flagged** |
| `AC3318` | victim 2 | salary arrived at 09:40, scam transfer at 10:01 — still an origin, **not flagged** |
| `AC5521` | M1 (new, shared device) | relay, HIGH |
| `AC5579` | M5 (new, shares KYC with M3) | relay, HIGH |
| `AC5530` | **M2 — the hub** | HIGH 95: pass-through + hub + corroborated layering + circular flow + shared device |
| `AC5547`, `AC5562` | M3, M4 | relays fanning out to cash-out |
| `AC6610`, `AC6624`, `AC6637`, `AC6651` | cash-out accounts | layered receipt / circular flow |
| `AC8800` | busy merchant | 280 payments, daily settlement — **pooled, not flagged** |
| `AC7100` | payroll company | ₹18 L in, 24 salaries out in 15 min — **not flagged** |
| `AC6101` | near miss | forwarded 89 % after 41 min, isolated — **not flagged** |
| `10.20.0.15` | office network | 23 established accounts share it — **ignored as evidence** |
| `AC4400` | second ring | fan-in from 5 victims → 3 relays |
| `AC3500–AC3503` | third ring | circular flow losing value each hop |
| `AC5600–AC5604` | pre-positioned accounts | 5 new accounts, one device |

## Script

1. **Hook (0:00–0:20).** "One fraud payment, layered through five accounts in fifteen minutes.
   Each transfer looks normal on its own."
2. **Data (0:20–0:40).** *Data* page: 2,125 rows, 6 rejected with reasons, 1 duplicate. Coverage
   panel shows which optional fields exist. "Bad data doesn't break us."
3. **Overview (0:40–1:00).** 29 flagged of 270, 5 high, three connected cases. Point at
   **Reviewed and not flagged** — "the system tells you what it chose *not* to flag, and why."
   *View all* opens the full **Not flagged** list, filterable by reason.
4. **Queue → `AC5530` (1:00–1:15).** Top of the queue. Primary reason in plain language.
5. **Why this account (1:15–1:35).** Score card: money flow 60 (pass-through 35, hub 5, corroborated
   layering 25, family cap), circular flow 20, shared device 15. "Every point is a rule plus
   transactions. It is not a probability."
6. **Follow the money (1:35–2:15).** Click *Where money came from* → the victims appear as diamonds
   (likely origins). Click *Where money went* → blue computed flow links ending at the cash-out
   accounts, with traced rupees on each edge and the exact accounting under the graph. Open the
   **Pass-through** evidence card → the timeline shows money arriving at 10:05 and 10:08 and leaving at
   10:11 and 10:12 (held 3–4 min), then ₹2.4 L circling back at 13:30 and out again at 13:34.
7. **Who else (2:15–2:30).** Case card: 2 origins, relays, sinks, ₹6 L entered, median dwell. Double-click
   a node to expand the network. *Open case* draws the whole ring on one graph; click a member to light up
   its transactions.
8. **Decide (2:30–2:45).** Note "Rapid layering confirmed" → **Confirm**. Audit trail updates; the case
   card shows 1 confirmed.
9. **Knowing when not to flag (2:45–3:15).** Search `AC2207` → not flagged, *possible-victim indicator,
   not a determination*. Search `AC7100` → payroll: "downgraded because funds came from a 30-day
   relationship…". Search `AC8800` → pooled merchant.
10. **Close (3:15–3:30).** "Deterministic, offline, every conclusion explainable, tested against
    adversarial cases — including the ones designed to fool it."

## If something goes wrong

- Page blank → `python run.py` again; the database keeps decisions.
- Data looks changed → **Data → Reset demo**.
- Graph too busy → *Suspicious flows only*, hops 1, *Fit all*, or *Full screen*.
