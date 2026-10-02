# MuleTrace — Architecture (frozen v1.2, amendment v1.2.1: relationship strength §4)

MuleTrace ingests a transaction CSV, builds an account graph, traces how money moves
through it over time, and flags mule-network structures:

- fan-in then fan-out within a short window
- circular transfers
- chains of pass-through accounts that keep near-zero balances
- clusters of new accounts sharing a device, IP or KYC attribute

Every flagged account receives a deterministic risk score and a plain-language reason.
An analyst can expand the network around it, follow the money, and mark it Confirmed or Cleared.

**Principles.** Deterministic first: the same CSV and configuration always produce the same
output. No model or external service is in the decision path. Money is integer minor units.
Every point of score traces to a rule, a metric, and concrete transactions.

---

## 1. Stack

| Layer | Choice |
|---|---|
| Backend | Python 3.11+ (developed on 3.14), FastAPI, Uvicorn, stdlib `csv`, `sqlite3`, `fractions` |
| Frontend | Vite + React 18 + TypeScript, Tailwind CSS 3.4, Cytoscape.js + cytoscape-dagre, react-router |
| Storage | SQLite file `backend/muletrace.db` (raw transactions, ingestion report, dispositions, audit log) |
| Tests | pytest (+ FastAPI TestClient) |
| Run | `python run.py` — one process on `127.0.0.1:8000` serves the API and the built frontend |

No graph database, no Docker, no cloud dependency, no runtime CDN. Works fully offline.

Analysis results (flow links, signals, cases, scores) are **derived data**: they are recomputed
deterministically from stored transactions + configuration at upload and at startup, and held in
memory. Only inputs and analyst actions are persisted.

---

## 2. Pipeline (fixed order — no stage reads a later stage's output)

```
 1 ingest              parse, validate, dedupe, normalise (ingest.py)
 2 graph / profiles    per-account aggregates, attributes, establishment, relationships (profiles.py)
 3 pooled              classify pooled accounts (profiles.py)
 4 FIFO flow links     lots, links, own-funds portions; pooled accounts do not propagate (flow.py)
 5 episodes            connected components of an account's links + pooled window episodes (flow.py)
 6 raw signals         RELAY, HUB, LAYERED_RECEIPT, ROUND_TRIP, IDENTITY with raw tiers (signals.py, identity.py)
 7 raw cases           components of flow edges among flow-active accounts; raw corroborated paths (cases.py)
 8 roles + indicator   structural roles, ORIGIN, possible-victim indicator (cases.py)
 9 mitigations         per-episode relationship-history downgrades with precedence rules (scoring.py)
10 qualification       which signals may flag an account (scoring.py)
11 scoring + severity  family points, caps, severity (scoring.py)
12 explanations        evidence chains, observations, "why not flagged" (explain.py)
```

---

## 3. Input data

### 3.1 Columns

Headers are matched case-insensitively after normalising spaces/hyphens to `_`, through an alias
table (`ingest.ALIASES`), so common public schemas load without editing.

| Canonical field | Class | Notes |
|---|---|---|
| `timestamp` | **required** | ISO 8601, `YYYY-MM-DD HH:MM[:SS]`, `DD-MM-YYYY HH:MM[:SS]`, `DD/MM/YYYY …`, `YYYY/MM/DD …`, epoch s/ms, or integer step index (§3.3) |
| `sender_account` | **required** | stripped string |
| `receiver_account` | **required** | stripped string |
| `amount` | **required** | currency symbols, commas, spaces stripped; `Decimal`; > 0; stored as integer minor units |
| `txn_id` | required* | if absent, derived as a hash of row content (reported) |
| `currency` | optional | §3.4 |
| `channel` | optional | display only |
| `sender_device_id`, `sender_ip`, `sender_kyc_id` | optional | identity attributes of the sender |
| `receiver_device_id`, `receiver_ip`, `receiver_kyc_id` | optional | identity attributes of the receiver |
| `sender_account_created`, `receiver_account_created` | optional | establishment evidence |
| `sender_balance_before/after`, `receiver_balance_before/after` | optional | used for ORIGIN funding (balance covers outflow) |
| `label` (`isFraud`, `is_laundering`, …) | optional | **never used by detection**; read only by `scripts/evaluate.py` |

Assumption: identity attributes are captured per transaction on the side they are listed for; an
account's attribute set is the union of all values seen for it. KYC is assumed to be an identity
document / phone hash.

### 3.2 Validation (ingestion report)

| Case | Handling |
|---|---|
| missing required column | whole file rejected (HTTP 422) listing missing and detected headers |
| unparseable timestamp / amount, amount ≤ 0, empty account | row rejected with row number and reason |
| sender == receiver | row rejected ("self-transfer") |
| exact duplicate `txn_id` + content | dropped, counted as duplicate |
| same `txn_id`, different content | first kept, later rejected ("conflicting duplicate") |
| minority-currency row | rejected ("minority currency") |
| BOM, CRLF, extra columns, quoted commas | handled |
| > 20 MB or > 200 000 rows | rejected with message |

The report lists counts, the first 200 errors, the detected column mapping, time mode, currency,
the coverage of optional capabilities, and the dataset time span.

### 3.3 Time

- Stored as integer seconds (UTC epoch). Naive timestamps are interpreted as IST (+05:30, fixed offset).
- **Step mode:** if every time value is an integer and the maximum is < 10⁶, the column is a step
  index, not epoch seconds. `ts = STEP_BASE + step × step_unit` (`step_unit` default 3600 s).
  The report states "step mode (1 step = 1 hour)".
- Integers ≥ 10¹² are epoch milliseconds; otherwise ≥ 10⁹ are epoch seconds.
- No stage reads the wall clock. Account age and relationship history are dataset-relative.

### 3.4 Currency

The dominant currency (most frequent; tie → alphabetical) is the dataset currency; when no
currency column exists it is `INR`. Rows in other currencies are rejected and reported. No
conversion. Thresholds are expressed in minor units of the dataset currency. The symbol comes
from the data (`INR ₹`, `USD $`, `EUR €`, `GBP £`, otherwise the code).

---

## 4. Profiles, establishment, relationships, pooled

- **Account profile:** first/last seen, in/out counts and totals, distinct counterparties,
  attribute sets, `created_at` (earliest seen), age at first activity.
- **Establishment (tri-state):**
  - creation date known → `NEW` if age at first activity ≤ 30 days, else `ESTABLISHED`;
  - creation unknown and dataset span ≥ 14 days → `ESTABLISHED` if observed history
    (last − first seen) ≥ 14 days, else `NEW` (proxy, labelled);
  - otherwise `UNKNOWN`.
  *Establishment evidence is available* when any creation date exists or span ≥ 14 days.
- **Relationship state** of an unordered counterparty pair for a payment *p* at time *t*
  (v1.2.1 — weighted by money, not by contact):
  - *matured* = total the pair exchanged (both directions) at or before `t − 7 d`;
  - *recent* = total the pair exchanged after `t − 7 d`, up to and including *p*;
  - `ESTABLISHED` if `matured > 0` and `matured ≥ RELATIONSHIP_HISTORY_SHARE (0.50) × recent`;
  - `NOVEL` otherwise, once `t ≥ dataset_start + 7 d`;
  - `UNKNOWN` during the 7-day warm-up. UNKNOWN never suppresses and never satisfies a novelty test.

  The question is "is this relationship genuinely established for this much money?", not "have these
  accounts ever transacted?". Consequences: a ₹1,000 payment two weeks before a ₹3 L transfer does not
  establish the relationship (relationship seeding); sixty ₹200 payments do not either (count is irrelevant);
  splitting the transfer into pieces does not help (each piece is judged against the pair's whole recent
  volume); padding sent inside the 7-day window raises *recent*, not *matured*. A salary that grew from
  ₹82,000 to ₹1,25,000 is still established (ratio 0.66). 0.50 lets ordinary variation (bonus, raise, a
  double payment) through and rejects order-of-magnitude jumps; an attacker must move at least half the
  attack value through the pair a week in advance. Used by case edges (§7.1), ORIGIN funding (§7.2) and
  mitigations (§7.4). The pooled window test (§5) keeps the contact-based state, as pooled logic is
  unchanged. Tests: `test_relationship.py` R1–R6, G14.
- **Pooled:** ≥ 50 distinct counterparties **and** active span ≥ 7 days. Descriptive only (§7.6).

---

## 5. Fund-Flow Engine (`flow.py`)

Per non-pooled account, events sorted by `(ts, inflow-before-outflow, txn sequence)`:

```
lots = FIFO queue of (in_txn, ts, remaining)
for event:
    expire lots with ts < event.ts − H_MAX (72 h)        # become untraceable own balance
    inflow  → append lot
    outflow → consume lots FIFO; each consumption emits FlowLink(in_txn, out_txn, amount, dwell)
              remainder not covered = own-funds portion of the outflow
```

- Same-timestamp events at one account: inflows first, then by input order. There is no global
  queue; accounts are processed independently, so cross-account timestamp collisions cannot drop links.
- Pooled accounts emit **no** links: traced money stops at them.
- Links are exact integers. Links below `MIN_LINK` (₹1 000) are kept for accounting but excluded
  from structure (episodes, chains, cases, round trips).
- **Invariants (tested):** Σ links out of a lot ≤ lot amount; Σ links into an outflow + own funds
  = outflow amount; dwell ≥ 0; output independent of row order.
- **Trace propagation** (multi-hop) uses `fractions.Fraction`:
  `amount_next = amount × link.amount / txn.amount`. Rounded only for display. For any trace,
  arrived + retained + stopped + truncated = start amount exactly.
- Displayed as **computed flow links (FIFO attribution)** — never as raw transactions.

### 5.1 Episodes

- **Non-pooled:** an episode is a connected component of the account's structural links
  (in-txns ↔ out-txns). Covers 1→N, N→1 (fragmented inflows) and N→M.
  - `inflow` = Σ in-txn amounts, `outflow` = Σ out-txn amounts, `forwarded` = Σ link amounts.
  - **Traced conservation** `c_t = forwarded / max(inflow, outflow)` (amount match in both directions:
    an account spending mostly its own money is not a relay).
  - **Dwell** = amount-weighted mean link dwell.
  - **Window conservation** (counters FIFO reservoir gaming): for each in-lot ≥ `MIN_EPISODE`
    and each tier bound *B*, `r = Σ outflows in (t, t+B] / lot amount`, `c_w = min(r, 1/r)`.
  - Evaluated only if `inflow ≥ MIN_EPISODE` (₹10 000).
- **Pooled:** each inflow lot ≥ `MIN_EPISODE` from a **NOVEL** counterparty is a window episode;
  outflows counted are those to NOVEL counterparties within *B*; `c = min(r, 1/r)`.

### 5.2 Tiers

| Tier | Dwell | Conservation |
|---|---|---|
| STRONG | ≤ 30 min | ≥ 0.90 |
| MODERATE | ≤ 6 h | ≥ 0.80 |
| WEAK | ≤ 72 h | ≥ 0.70 |

Traced tier = weaker of dwell tier and `c_t` tier. Window tier = best tier *B* whose `c_w` meets
that tier's conservation. **Episode tier = max(traced tier, window tier).** WEAK never scores.

---

## 6. Signals (raw, stage 6)

| Signal | Family | Definition |
|---|---|---|
| **RELAY** | FLOW | best episode tier of the account (pass-through) |
| **HUB** | FLOW | episodes (tier ≥ MODERATE) grouped into bursts starting within 6 h; a burst with ≥ 3 distinct funded senders **and** ≥ 3 distinct funded receivers, aggregated across episodes (so A→X, B→Y, C→Z through M is a hub). Tier from burst-aggregated conservation and dwell |
| **LAYERED_RECEIPT** | FLOW | account receives a transaction whose funds passed through ≥ 2 upstream relay accounts (raw RELAY ≥ MODERATE) — STRONG if the path spans ≤ 6 h, MODERATE ≤ 72 h. Consolidation when ≥ 2 distinct upstream relay senders |
| **ROUND_TRIP** | CIRCULARITY | traced funds leaving A return to A through ≥ 2 other accounts, ≤ 6 hops, pooled accounts not traversed. STRONG: ≤ 24 h and ≥ 50 % value returned; MODERATE: ≤ 72 h and ≥ 30 %. Two-party reciprocal flows are observations only |
| **IDENTITY** | IDENTITY | §6.1 |

### 6.1 Identity clusters

- For each `(type, value)`: sharers. *Eligible* members are `NEW` or `UNKNOWN` accounts.
- **Infrastructure** (only when establishment evidence is available): ≥ 60 % of sharers are
  `ESTABLISHED` **and** ≥ 5 are established. Raw count alone never suppresses. Without establishment
  evidence infrastructure suppression is unavailable.
- Qualifying group: non-infrastructure, eligible members ≥ min size (device 3, IP 4, KYC 2).
- Clusters: union-find across qualifying groups. Link strength: device / KYC = STRONG, IP-only = weak.
- Established sharers of a qualifying group are context members (role CLUSTER_MEMBER), scored only
  if they share a flow case with another member.
- **Restoration (precedence):** flow-active members of an infrastructure group (or established context
  members) who share a flow case are linked by that attribute anyway. Origins and boundary accounts are
  never linked this way.
- IP-only clusters larger than 15 accounts without establishment evidence appear in the queue as
  **one group item**, not one item per account.

---

## 7. Cases, roles, mitigations, qualification

### 7.1 Raw cases (stage 7)

Flow-active accounts: raw RELAY / HUB / LAYERED_RECEIPT / ROUND_TRIP ≥ MODERATE. Case edges are the
transactions of the episodes and paths that made an account flow-active (episodes ≥ MODERATE, limited to
outflows inside the episode's tier window; layered-receipt and round-trip transactions) and touch a
flow-active account, **except** edges over an `ESTABLISHED` relationship whose other end is not flow-active
(e.g. employer → salary). Historical linked payments outside the suspicious movement never join a case.
A case is a connected component; non-active members are boundary accounts.
**Raw corroborated paths:** traced paths through ≥ 3 raw-STRONG relays spanning ≤ 60 min.

### 7.2 Roles (structural, independent of score)

`ORIGIN` · `RELAY` · `HUB` · `COLLECTOR` (≥ 3 funded senders, ≤ 2 receivers) · `DISTRIBUTOR`
(≤ 2 senders, ≥ 3 receivers) · `SINK` (receives case funds, forwards < 20 %) · `POOLED` · `CLUSTER_MEMBER`.

**ORIGIN:** a case member with no case edge into it from another member, whose outflow into the case
is funded ≥ 50 % by own funds, or ≥ 80 % by ESTABLISHED relationships with non-flow-active accounts,
or covered by `balance_before`. Pooled accounts are never ORIGIN.

Roles and the possible-victim indicator are displayed only for cases that contain a flagged account
(pooled accounts always show POOLED); a flow nobody was flagged for does not label its participants.
LAYERED_RECEIPT is re-evaluated at qualification against final relays, so an ORIGIN never counts as a relay.

### 7.3 Possible-victim indicator (separate from role)

Assessed only for ORIGIN: `CONTRA_INDICATED` if it shares a device/KYC value with case members,
receives funds from a case member above ₹1 000, has an IDENTITY or ROUND_TRIP signal, or originates
funds into ≥ 2 cases; otherwise `INDICATED`. Others: `NOT_ASSESSED`.
UI text: *"Indicators consistent with a possible victim. This is not a determination."*
No screen ever states that an account is a victim or a criminal.
ORIGIN FLOW signals score 0 unless the indicator is `CONTRA_INDICATED`.

### 7.4 Mitigations (stage 9) — per episode, RELAY and HUB only

| Mitigation | Condition (episode) | Effect |
|---|---|---|
| `ESTABLISHED_FUNDING` | ≥ 80 % of inflow from ESTABLISHED relationships with non-flow-active counterparties | −1 tier |
| `ESTABLISHED_PAYEES` | ≥ 80 % of outflow to ESTABLISHED relationships with non-flow-active counterparties | −1 tier |

**Precedence (G13):** account age and history are never mitigations. No mitigation applies to an
episode on a raw corroborated path, or whose funding and payees are both NOVEL. Pooled status,
infrastructure classification and ORIGIN never erase corroborated flow evidence.

### 7.5 Qualification (stage 10) — only qualifying signals score or flag

| Signal | Qualifies when |
|---|---|
| RELAY (≥ MODERATE) | linked to/from another relay (≥ MODERATE, not ORIGIN-zeroed), **or** ≥ 3 episodes ≥ MODERATE, **or** another family present |
| HUB, LAYERED_RECEIPT, ROUND_TRIP | STRONG alone; MODERATE with corroboration (another family present, or a case with ≥ 3 relays ≥ MODERATE) |
| IDENTITY | device/KYC alone; IP-only alone, labelled weak evidence |
| WEAK tier | never — observation only |

An isolated single-episode relay is an observation ("not part of a chain"): this protects Day-1
users, salary → rent, payroll, and victims.

### 7.6 Pooled contract

Pooled accounts **can** be flagged and dispositioned, score IDENTITY, score HUB from their window
episodes, score RELAY through the amount-matched NOVEL→NOVEL window test, score LAYERED_RECEIPT,
appear in cases and graphs. They **cannot** pass traced amounts onward, be traversed by round-trip
search, join chain segments (chain counts stop at them), or be ORIGIN. Qualification adjacency for
a pooled relay uses direct transaction adjacency to other relays.

---

## 8. Scoring (stage 11)

| Family (cap) | Signal | STRONG | MODERATE |
|---|---|---|---|
| **FLOW (60)** | RELAY | 35 | 20 |
| | HUB | 25 | 15 |
| | LAYERED_RECEIPT | 20 | 10 |
| | bonuses | +5 per additional qualifying base signal · +5 REPEATED (≥ 3 episodes) · **CHAIN +10** (on a traced path of ≥ 3 relays ≥ MODERATE) **or CORROBORATED_LAYERING +25** (path of ≥ 3 STRONG relays, end-to-end ≤ 60 min) · +10 consolidation | |
| **CIRCULARITY (20)** | ROUND_TRIP | 20 | 12 |
| **IDENTITY (20)** | device / KYC link 15 · IP-only 8 · +5 per additional link type | | |

Total = Σ family scores (max 100). **Severity:** HIGH ≥ 60 · MEDIUM 35–59 · LOW < 35 (flagged).
The score is an evidence-strength index — **not a probability of fraud**. Exposure (₹ traced) is
shown, never scored. Queue order: severity, score, exposure, account id.

---

## 9. Explainability

Every scored signal carries: rule → metrics → transaction ids → timeline → graph path → points.
Every non-scored consideration is an **observation** (`NEAR_MISS`, `ISOLATED_RELAY`, `MITIGATED`,
`INFRA_ATTRIBUTE`, `ORIGIN_ZEROED`, `POOLED`, `RECIPROCAL`, `HISTORY_UNAVAILABLE`), which powers
"Why not flagged?" for any account. Explanations are generated only from computed metrics.

---

## 10. API

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/datasets` | upload CSV (multipart) |
| POST | `/api/datasets/demo` | load the bundled demo dataset |
| POST | `/api/reset` | reload demo, clear dispositions (the audit log stays append-only: each cleared decision gets a RESET entry) |
| GET | `/api/datasets/current` | ingestion report and coverage |
| GET | `/api/summary` | dashboard figures, reviewed-not-flagged list |
| GET | `/api/queue` | flagged accounts and group items (`severity`, `status`, `pattern`, `q`) |
| GET | `/api/export/queue.csv` | the same filtered queue, same order, as CSV (UTF-8 with BOM; score, severity, patterns, role, cases, exposure, primary reason, analyst decision; a group item is one row listing its members; cells starting `=` `+` `-` `@` are prefixed with `'`; file name carries the dataset fingerprint and configuration hash) |
| GET | `/api/search?q=` | any account |
| GET | `/api/accounts/{id}` | profile, role, indicator, signals, score breakdown, observations, disposition, audit |
| GET | `/api/accounts/{id}/transactions` | transactions |
| GET | `/api/accounts/{id}/network` | k-hop transaction graph (≤ 80 nodes) |
| GET | `/api/accounts/{id}/trace?dir=fwd\|back` | traced flow (≤ 50 nodes + aggregate node, ≤ 8 hops, pooled stops) |
| GET | `/api/cases/{id}` | case members, roles, metrics, timeline |
| GET | `/api/cases/{id}/network` | the whole case as one graph: members (case roles) and the case transactions between them, same contract as the account network; over 80 members, a connected part built from the case's most valuable money paths (likely origin → relays → cash-out), then the highest-scoring flagged neighbours |
| GET | `/api/observations` | suppressed / near-miss activity |
| POST | `/api/accounts/{id}/disposition` | Confirm / Clear with note and analyst name |
| GET | `/api/config` | thresholds and configuration hash |

**Fallback mode** (`engine=window`): window-based signals behind the same contract; the trace
endpoint returns transaction-level results labelled `"mode": "transactions"`: the suspicious transactions into
(`back`) or out of (`fwd`) the account, followed hop by hop in that direction.

---

## 11. Analyst UX

Start (upload / demo, ingestion report, coverage) → Overview (figures, risk distribution, patterns,
reviewed-not-flagged) → Queue → **Investigation**: score breakdown, role + indicator, findings with
evidence chains, timeline, graph (raw network or trace mode with role shapes), transactions,
"Why not flagged?", case card, Confirm / Clear with audit history. Light and dark themes from
semantic design tokens; status never conveyed by colour alone.

---

## 12. Known limitations (stated openly)

- FIFO attribution is a convention, not ground truth.
- Flows slower than the 72 h horizon are not linked; layering slower than 6 h per hop is observation-level.
- An account sustaining ≥ 50 counterparties over ≥ 7 days is pooled and is not traced through.
- History-based mitigations need ≥ 7 days of data; the first 7 days are warm-up.
- Cash withdrawals and other-bank legs are invisible; sinks are the edge of observable data.
- Single currency per dataset.
- **Prior relationship of substantial value.** Relationship seeding with small or many small payments is
  closed (§4, v1.2.1). If a victim genuinely sent the first mule at least half the fraud's value at least
  7 days earlier, the relationship is established and that mule reads as an origin, like a salary-funded
  victim (G4); the rest of the chain and the cash-out are still flagged (R5, R6 tests).
