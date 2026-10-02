# MuleTrace

**TechForge 2026 · Team Big Nuts · Domain: Fintech**

*Follow the money through a mule network — and know when not to.*

## 1. Project Overview

MuleTrace is a local, deterministic investigation console for money-mule networks. It reads a transaction CSV,
links every outgoing payment to the incoming money that funded it, finds the structures that layering leaves
behind, scores the evidence, groups connected activity into cases and lets an analyst record a decision with an
audit trail. It runs offline on a single machine: one Python process serves both the API and the web console.

## 2. Problem Statement

**Domain:** Fintech · **Project:** MuleTrace

> A fraud reaches a victim’s account once, but the money is layered through 3–6 accounts within minutes, each
> transfer looking ordinary. Build MuleTrace, which ingests a transaction CSV, builds an account graph, and flags
> suspicious structures: fan-in then fan-out within a short window, circular transfers, chains of pass-through
> accounts that keep near-zero balances, and clusters of new accounts sharing a device, IP or KYC attribute. Each
> flagged account gets a risk score and a plain-language reason, and an analyst can expand the network around it
> and mark it confirmed or cleared.

## 3. Project Description

MuleTrace is a deterministic financial investigation platform that analyzes transaction data to uncover
suspicious money-mule networks and trace how funds move across connected accounts. It combines FIFO-based
money-flow attribution, structural pattern detection, identity-link analysis, explainable risk scoring, case
grouping, interactive investigation graphs, and analyst decision tracking. The platform helps investigators move
from thousands of raw transactions to explainable cases while also showing activity that was deliberately not
flagged to reduce false positives.

## 4. Key Features

All of the following are implemented in the current build.

**Data**
- CSV ingestion and validation: rows are checked individually; bad rows are rejected with a row number and reason,
  exact duplicates are dropped and counted.
- Data-quality reporting: an ingestion report (rows, accepted, rejected, duplicates, column mapping, currency,
  date range) and an *Analysis coverage* panel that says which optional checks the file can support.

**Analysis (deterministic, rule-based)**
- FIFO money-flow attribution: each outgoing payment is linked to the incoming money that funded it; traces
  are computed with exact fractions so the traced amounts always add up.
- Suspicious flow detection, graded STRONG / MODERATE / WEAK by holding time and share of money passed on.
- Pass-through (relay) detection.
- Fan-in → fan-out hub detection.
- Layered-receipt detection (funds received through several relays).
- Circular / round-trip detection (money that actually returns, not just a loop in the graph).
- Shared device / IP / KYC analysis, with shared infrastructure (for example an office network) recognised and
  not treated as evidence.
- Account roles (likely origin, relay, hub, collector, distributor, sink, pooled) and a possible-victim
  indicator for likely origins, always worded as *not a determination*.
- Explainable evidence scoring: three capped evidence families (money flow 60, circularity 20, shared identity 20);
  every point links to a rule, metrics and transactions. The score is an evidence-strength index, not a
  probability of fraud.
- Severity classification: HIGH ≥ 60, MEDIUM 35–59, LOW 1–34.
- False-positive mitigations: established-relationship downgrades, isolated single pass-throughs not scored,
  pooled accounts, shared infrastructure, and a corroboration requirement before weaker signals score.

**Investigation console**
- Suspicious case grouping and case investigation page (money-flow summary, case graph, members and roles,
  case timeline).
- Interactive account / network graph (Cytoscape.js) with hop depth, expansion and highlighting of selected evidence.
- *Where money came from* and *Where money went* tracing, with exact accounting of the traced amounts.
- *Not flagged* page: every set-aside account with the rule that set it aside.
- Analyst Confirm / Clear / Reopen workflow with notes, and an append-only audit trail.
- Methodology / configuration panel (read-only view of the thresholds, points and caps that actually ran).
- CSV export of the investigation queue, with the same filters and order as the screen.
- Light / dark mode and a responsive layout (usable at phone width).
- Fallback engine: a simpler window-based engine, started manually with `--engine window` (see
  [Limitations](#11-limitations--future-scope)). It is not an automatic failover.

## 5. Technology Stack

| Layer | Technology |
|---|---|
| Backend | Python, FastAPI, Uvicorn, Pydantic, python-multipart; analysis in plain Python (standard-library `csv`, `sqlite3`, `fractions`) |
| Storage | SQLite file `backend/muletrace.db` — raw uploaded CSV, analyst decisions, audit log. Analysis results are recomputed on load and held in memory |
| Frontend | React 18, TypeScript, Vite, Tailwind CSS, react-router, Cytoscape.js with cytoscape-dagre, lucide-react icons |
| Tests | pytest (+ httpx) for the backend; Node's built-in test runner for the console logic |

No graph library, graph database, container runtime, external service or runtime CDN is used.

## 6. Architecture / Workflow

The analysis is a fixed pipeline: no stage reads the output of a later stage, and the whole result is a pure
function of the transactions and the configuration (no randomness, no clock).

```
CSV
 → ingestion ............ read, validate, de-duplicate, normalise (time, money, currency)
 → profiles ............. one profile per account; new vs established; relationship history
 → pooled-account classification
 → FIFO flow links ...... each outgoing payment linked to the incoming money that funded it
 → episodes ............. linked inflows and outflows of one account, graded by tier
 → signals .............. pass-through, fan-in → fan-out hub, layered receipt, circular flow, shared attributes
 → cases ................ connected suspicious movement
 → roles / possible-victim indicator
 → mitigations .......... established relationships can lower an episode's tier
 → qualification ........ which signals are allowed to score
 → scoring / severity ... points per evidence family, family caps, HIGH / MEDIUM / LOW
 → explanations ......... reason sentences, observations, "why not flagged"
 → investigation console  Overview, queue, cases, account and case pages
```

Backend modules: `ingest.py`, `profiles.py`, `flow.py`, `signals.py`, `identity.py`, `cases.py`, `scoring.py`,
`explain.py`, `pipeline.py`, with `api.py` (REST API and static serving), `store.py` (SQLite), `network.py` and
`summary.py` (graph and case views) and `fallback.py` (window engine).

References: [ARCHITECTURE.md](ARCHITECTURE.md) (design specification) and the
[Operator & Demo Master Guide](docs/MULETRACE_DEMO_MASTER_GUIDE.md)
([PDF](docs/MULETRACE_DEMO_MASTER_GUIDE.pdf)), which documents every screen, rule and verified demo figure.

## 7. Dataset / API Information

**Bundled demo dataset** — `data/demo.csv`: a synthetic, deterministic dataset (1–31 March 2024, fictitious account
IDs, INR) containing one hero mule ring, two further ring patterns, shared-identity clusters, deliberately legitimate
activity (payroll, a busy merchant, an office network) and seven malformed rows. It is regenerated by
`python scripts/make_demo.py`.

**CSV structure**

| Columns | Status |
|---|---|
| `timestamp`, `sender_account`, `receiver_account`, `amount` | **Required.** A file missing any of these is rejected as a whole and the page lists the headers it found |
| `txn_id` | Recommended; derived from row content if absent |
| `currency`, `channel` | Optional |
| `sender_device_id`, `sender_ip`, `sender_kyc_id`, `receiver_device_id`, `receiver_ip`, `receiver_kyc_id` | Optional — enable shared-attribute analysis |
| `sender_account_created`, `receiver_account_created` | Optional — enable new-account / established-account judgement |
| `sender_balance_before/after`, `receiver_balance_before/after` | Optional |
| `label` / `isFraud` | Recognised but **never used by detection** |

Common alternative headers (`from`/`to`, `nameOrig`/`nameDest`, `step`, …) are mapped automatically. Limits: `.csv`
or `.txt`, up to 20 MB and 200,000 rows. One currency per dataset (rows in other currencies are rejected).

**Validation and data quality.** Rows are validated one by one. Rejected rows (bad timestamp, non-positive or
unparseable amount, self-transfer, empty account, conflicting duplicate transaction ID) are listed with row number,
reason and excerpt; exact duplicates are dropped and counted. The *Analysis coverage* panel shows which optional
capabilities are present and what is reduced when one is missing. For the demo file: 2,125 rows in the file, 2,118
accepted, 6 rejected, 1 duplicate dropped.

**External APIs and data location.** No external API is required at runtime and the backend makes no outbound
calls. All data is processed locally; the only files written are the SQLite database and, if you export it, the
queue CSV. The application exposes its own REST API under `/api/...` (served by the same process) for the console.

## 8. Setup & Installation

Verified on Windows 11 with Python 3.14.4, Node.js 24.15.0 and npm 11.12.1. The project targets Python 3.11+;
building the console needs a Node version supported by Vite 5 (18 or newer); the frontend test script uses
Node's TypeScript support and was run on Node 24. Internet access is needed once, to install dependencies.

```sh
git clone https://github.com/Ashutosh-Sus/Big-Nuts-MuleTrace.git
cd Big-Nuts-MuleTrace
git checkout feat/cases-list
```

**One command** (creates the Python environment, installs dependencies, builds the console once, starts the
server and opens the browser):

```powershell
.\start.ps1            # Windows (PowerShell)
```
```sh
./start.sh             # macOS / Linux
```

**Manual setup** (equivalent):

```powershell
# Windows (PowerShell)
python -m venv backend\.venv
backend\.venv\Scripts\pip install -r backend\requirements.txt
cd frontend; npm install; npm run build; cd ..
```
```sh
# macOS / Linux
python3 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements.txt
(cd frontend && npm install && npm run build)
```

## 9. Running the Application

```powershell
backend\.venv\Scripts\python run.py          # Windows
```
```sh
backend/.venv/bin/python run.py              # macOS / Linux
```

- **Where it runs:** one process serves the backend API and the built frontend at <http://127.0.0.1:8000>. There is
  no separate frontend server to start (the Vite dev server, `npm run dev`, is only for frontend development).
- **Demo dataset:** the bundled demo is loaded automatically on start. You can also open the **Data** page and press
  **Load demo dataset** (or **Reset demo** to return every demo decision to Open), or upload your own CSV there.
- **Options:** `--port 8080`, `--host`, `--open` (open the browser), `--engine window` (fallback engine).
- **Tests:**

```powershell
backend\.venv\Scripts\python -m pytest -q backend\tests      # 138 tests
cd frontend; npm test                                        # 12 tests
```

## 10. Screenshots / Demo Information

No screenshots are bundled in the repository; the demo runs live. The expected current figures for the bundled
dataset (also shown on the Overview page):

| Item | Value |
|---|---|
| Accounts | 270 |
| Transactions analysed | 2,118 |
| Flagged accounts | 29 — 5 HIGH, 8 MEDIUM, 16 LOW |
| Suspicious cases | 3 (CASE-03, CASE-02, CASE-04) |
| Not-flagged accounts set aside with a stated reason | 43 |
| Hero account | **AC5530** — HIGH, score 95 (role: Hub) |
| Hero case | **CASE-03** — 11 accounts, 9 flagged |

**Demo walkthrough:** Data → Overview → Suspicious Cases → Account Investigation → Graph / Trace → Case
Investigation → Analyst Decision.

1. **Data** — load the demo dataset; read the ingestion report and the analysis coverage.
2. **Overview** — counts, risk distribution, patterns detected, highest priority, and what was reviewed and not flagged.
3. **Suspicious Cases** — open the **Suspicious cases** tile; open CASE-03.
4. **Account Investigation** — open AC5530 from the case or the queue; read the score card and the evidence cards.
5. **Graph / Trace** — switch between *Network*, *Where money came from* and *Where money went*.
6. **Case Investigation** — the money-flow summary, case graph, members and observed roles.
7. **Analyst Decision** — add a note and Confirm, Clear or Reopen; the audit trail records it. The score does not change.

How to read the figures: the **score** is an evidence-strength index out of 100, not a probability of fraud.
**Exposure** is a sum of per-account evidence amounts that counts the same money at each account it passed through;
it is not an amount lost. A **likely origin** is where case money entered; the interface shows only a
*possible-victim indicator*, which is not a determination. The full presenter reference is the
[Master Guide](docs/MULETRACE_DEMO_MASTER_GUIDE.md).

## 11. Limitations & Future Scope

**Current limitations**

- Local-first, single-user deployment: no login, roles or permissions (the analyst name is a free-text field
  recorded with each decision).
- Deterministic, rule-based analysis with fixed, read-only thresholds; it detects structures, not intent, and
  makes no legal determination. A *Confirmed* decision is an analyst's recorded disposition, not a legal finding.
- It reduces false positives but does not guarantee to eliminate them; some legitimate activity can resemble
  layering.
- FIFO attribution is a convention, not ground truth. Flows slower than 72 hours are not linked; the first 7 days of
  a dataset are relationship warm-up.
- Accounts with 50 or more counterparties over 7 or more days are treated as pooled and are not traced through.
- Results depend on the transaction and account metadata supplied. Without device / IP / KYC columns there is no
  shared-identity evidence; without account-opening dates (and under 14 days of data) establishment cannot be
  judged. Cash withdrawals and other-bank legs are outside the data. One currency per dataset.
- Graph and trace exploration is bounded: traces follow at most 8 hops and draw at most 50 nodes; large case
  graphs show a connected subset of the most valuable money paths.
- The fallback (window) engine is chosen manually at start. It creates no flow links, so it has no traced amounts,
  layered-receipt or chain detection; on the demo it flags 19 accounts instead of 29.

**Future scope** *(not implemented)*

- Authentication, multiple analysts and role-based access.
- Link-back navigation from a case to the cases list, and a cases entry in the header navigation.
- Additional ingestion adapters and multi-currency support.
- Streaming or incremental analysis for larger datasets.

## 12. Team Members

**Team Big Nuts**

- Ashutosh Chaudhari
- Krishna Garje
