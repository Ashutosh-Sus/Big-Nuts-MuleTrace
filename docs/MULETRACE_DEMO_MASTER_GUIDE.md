# MuleTrace — Operator & Demo Master Guide

**Final release: v1.0.0** · presenter reference · built from the implemented code, the running console, the bundled demo dataset and the test suite.

## How to use this guide

This is the presenter's operating manual. It explains what every screen shows, what every button does, how the analysis works, which numbers are safe to quote and which claims must never be made.

Every number in this guide was read from the running analysis of the bundled demo dataset (`data/demo.csv`) with the default configuration (configuration hash `b652e4bf70db`, engine `flow`), or from the configuration itself. Where the older presentation notes (`DEMO.md`) or the architecture document disagree with the implementation, the implementation wins and the difference is listed in **Implementation Verification** at the end.

The guide uses five kinds of boxes:

> **Presenter explanation:** What you can say out loud. Conversational, and only claims the product actually supports.

> **Technical reference:** Where the behaviour lives in the code: file paths, function names, API endpoints, configuration keys.

> **Warning:** Something you must not claim, or a limitation you must not hide.

> **Verified numbers:** Figures checked against the running demo. Safe to quote.

> **Judge may ask:** A question this part of the product invites, with the short answer.

All times are IST (the analysis uses a fixed +05:30 offset). Amounts are in rupees; the engine stores them as integer paise.

# Part 1 — Product Map

MuleTrace is a local, deterministic, rule-based investigation console for money-mule networks. It reads a transaction CSV, links each outgoing payment to the incoming money that funded it, finds the structures that layering leaves behind, scores the evidence, groups connected activity into cases and lets an analyst record a decision with an audit trail.

```
MuleTrace
 ├─ Data ingestion ............ Data page (/data): upload CSV, load / reset demo, ingestion report
 ├─ Analysis .................. runs automatically on every load (12 fixed stages, in memory)
 ├─ Overview .................. / : counts, risk distribution, patterns, top priorities, "not flagged"
 ├─ Investigation queue ....... /queue : every flagged account, filters, CSV export
 ├─ Suspicious cases .......... /cases : connected flows that contain a flagged account
 ├─ Account investigation ..... /account/{id} : score, evidence, graph, trace, timeline, decision
 ├─ Case investigation ........ /case/{id} : money-flow summary, case graph, members, timeline
 ├─ Graph investigation ....... inside the account and case pages (network / trace views)
 ├─ Evidence and explanations . evidence cards, score card, "Why not flagged", Not flagged page (/reviewed)
 ├─ Analyst decision .......... Confirm / Clear / Reopen with note, on the account page
 ├─ Audit trail ............... append-only log per account, shown under the decision panel
 └─ Methodology / config ...... "Method" panel (read-only view of /api/config)
```

## 1.1 Screens at a glance

| Screen | Route | Question it answers |
|---|---|---|
| Data | `/data` | What did we load, and what was rejected or missing? |
| Overview | `/` | What suspicious activity exists, and how much? |
| Investigation queue | `/queue` | Which accounts deserve attention first? |
| Not flagged | `/reviewed` | What did the system consider and deliberately set aside? |
| Suspicious cases | `/cases` | Which connected flows contain flagged accounts? |
| Account investigation | `/account/{id}` | Why was this account flagged, and how did money move through it? |
| Case investigation | `/case/{id}` | How did money enter, move through and leave this group of accounts? |
| Method panel | dialog | Which rules, points and thresholds produced these results? |

## 1.2 Screen details

| Screen | Important UI elements | Main actions | API endpoints |
|---|---|---|---|
| Data | Drop zone, Load demo dataset, Reset demo, Analysis coverage, Ingestion report | Upload CSV, Load demo, Reset demo, Continue to Overview | `POST /api/datasets`, `POST /api/datasets/demo`, `POST /api/reset`, `GET /api/datasets/current` |
| Overview | Six tiles, Risk distribution, Patterns detected, Highest priority, Reviewed and not flagged | Open queue, open cases, filter queue by severity / status / pattern, View all not-flagged | `GET /api/summary` |
| Queue | Filter chips (severity, pattern, status), account filter, table | Open account, expand group row, Export CSV | `GET /api/queue`, `GET /api/export/queue.csv` |
| Not flagged | Scope chips, reason chips with counts, grouped rows | Filter, expand grouped row, open account | `GET /api/observations` |
| Cases | One row per case with severity, progress, value from likely origins, window, median dwell, families | Open case | `GET /api/cases` |
| Account | Header, score card, decision panel, profile, graph (3 views), timeline, transactions, evidence cards, connected case card, "Why not flagged" | Select evidence, switch graph view, expand node, Confirm / Clear / Reopen, open case | `GET /api/accounts/{id}`, `.../network`, `.../trace`, `.../transactions`, `POST .../disposition`, `GET /api/cases/{id}` |
| Case | Header facts, Money-flow summary, case graph, members table, case timeline | Select member, double-click to open account, Method | `GET /api/cases/{id}`, `.../network`, `.../summary` |
| Method | Read-only rows grouped by topic, engine and configuration hash | Open, close (Escape / backdrop / X) | `GET /api/config` |

## 1.3 Header and footer (every page)

- **Navigation:** Overview, Queue, Not flagged, Data. The Cases list is *not* in the header; it opens from the Overview tile **Suspicious cases** (or the URL `/cases`).
- **Find any account…** searches every account in the dataset (case-insensitive substring, up to 20 results, exact match first, then prefix matches). Enter opens the best match; "No account matches" appears when nothing fits.
- **Analyst name** (top right) is free text stored in the browser. It is recorded with every decision. It is not a login.
- **Theme toggle** switches light / dark. The first visit follows the operating-system preference; the choice is then remembered in the browser.
- **Footer:** "Deterministic rule-based analysis · scores are evidence-strength indices, not probabilities of fraud · config `<hash>` · engine `<flow|window>`".

> **Technical reference:** `frontend/src/App.tsx` (routes, header, footer), `frontend/src/lib/search.ts`, `GET /api/search?q=` in `backend/muletrace/api.py`. If no dataset is loaded, every page except Data redirects to `/data`.

# Part 2 — Page-by-page Operator Guide

## 2.1 Data page (`/data`)

**A. What is this page?** The front door. It loads transactions and shows exactly what was accepted, rejected and available for analysis.

**B. Question it answers:** "What did we analyse, and can I trust the input?"

**C. What am I looking at?**

- **Load transactions** card: a drop zone (click or drag a CSV), **Load demo dataset**, **Reset demo**. The hint lists required columns (timestamp, sender, receiver, amount) and optional ones (device, IP, KYC, account dates, balances).
- **Analysis coverage**: one line per optional capability with a tick or a dash. A missing capability says what is reduced, for example "Not in file — balance-covered origin check unavailable or reduced". Two extra lines: whether account establishment can be judged, and whether relationship history (≥ 7 days) is available.
- **Ingestion report**: rows in file, accepted, rejected, duplicates dropped; time column mode; currency; whether transaction IDs came from the file; column mapping (file header → canonical field) and ignored columns; the rejected rows with row number, reason and an excerpt; the analysed date range.

What it does **not** mean: an accepted row is only well-formed. Acceptance says nothing about whether the transaction is suspicious.

> **Verified numbers:** Demo file: **2,125** rows · **2,118** accepted · **6** rejected · **1** duplicate dropped. Time column "date/time text", currency INR (₹), transaction IDs from the file, range 01 Mar 2024 – 31 Mar 2024. Coverage: currency, device, IP, KYC and account opening dates present; balances and label absent; establishment can be judged; relationship history available.

The six rejected demo rows and their reasons:

| Row | Reason shown |
|---|---|
| 2120 | unparseable timestamp '31-02-2024 25:61' |
| 2121 | amount must be positive |
| 2122 | self-transfer |
| 2124 | conflicting duplicate txn_id TX102037 |
| 2125 | empty account |
| 2126 | unparseable amount 'twelve hundred' |

Row 2123 is an exact duplicate: it is silently dropped and counted under "Duplicates dropped", not listed as an error.

**D. What happens when I click?**

- **Drop / choose a CSV** → browser posts the file → `POST /api/datasets` → server checks size (≤ 20 MB) and extension (.csv / .txt), parses and validates every row, stores the raw file in SQLite as the active dataset and runs the full analysis → returns the ingestion report → the report and coverage refresh; every other page reloads its data. A missing required column rejects the whole file (HTTP 422) and the page lists the detected headers.
- **Load demo dataset** → `POST /api/datasets/demo` → server re-reads `data/demo.csv`, stores it and re-runs the analysis → same report view. Existing decisions on the demo dataset are kept (decisions are stored per dataset fingerprint).
- **Reset demo** → `POST /api/reset` with the analyst name → server reloads the demo, returns every decision on the demo dataset to Open and writes a RESET entry into each affected account's audit trail (the audit log is never deleted) → report view refreshes.
- **Continue to Overview** → navigates to `/`.

**E. What should I say?**

> **Presenter explanation:** "This is the intake. Out of 2,125 rows, six were rejected — each with a row number and a reason — and one exact duplicate was dropped. Bad rows don't break the analysis; they're reported. The coverage panel tells the investigator which checks the file can support."

> **Technical reference:** `backend/muletrace/ingest.py` → `parse_csv()`, `map_columns()`, `TimeParser`; `frontend/src/pages/DataPage.tsx`; `backend/muletrace/store.py` → `Store.add_dataset()`, `Store.clear_dispositions()`.

## 2.2 Overview (`/`)

**A. What is this page?** A one-screen summary of the loaded dataset after analysis.

**B. Question it answers:** "What suspicious activity exists, how much, and what was deliberately not flagged?"

**C. What am I looking at?**

- **Six tiles:** Accounts · Transactions analysed (with the number of computed flow links) · Flagged accounts (with % of accounts) · High severity · **Suspicious cases** (clickable, opens `/cases`) · **Exposure**.
- **Exposure** = for each flagged account, the largest amount in its scored evidence, summed over the queue. The tile's subtitle also shows the total value of all transactions. Exposure is shown, never scored. It is **not** a loss figure, and because the same money passes through several flagged accounts it is counted more than once.
- **Risk distribution:** a bar and counts per severity (each links to the queue filtered by that severity) and the analyst decisions on flagged accounts (Open / Confirmed / Cleared, each links to the filtered queue). Decisions recorded on accounts that are *not* flagged are listed separately here ("not in the queue").
- **Patterns detected:** number of flagged accounts with each scored pattern (each opens the queue filtered by that pattern).
- **Highest priority:** the first six queue items with role, severity, score and the primary reason.
- **Reviewed and not flagged:** how many not-flagged accounts were considered and set aside for a stated reason, twelve examples interleaved by reason kind, and **View all** (opens `/reviewed`).

> **Verified numbers:** **270** accounts · **2,118** transactions · **429** computed flow links · **29** flagged (10.7 %) · **5** HIGH, **8** MEDIUM, **16** LOW · **3** suspicious cases · Exposure **₹51.67L** · **₹3.75Cr** moved in all · patterns: pass-through 12, fan-in → fan-out 2, layered receipt 7, circular flow 8, shared attributes 14 · **43** not-flagged accounts set aside with a stated reason.

**D. What happens when I click?** Every tile, badge and pattern bar is a link: the page itself loads once from `GET /api/summary` and the links navigate to the queue (`/queue?severity=…`, `?status=…`, `?pattern=…`), to `/cases`, to an account, or to `/reviewed`. Nothing on this page changes data.

**E. What should I say?**

> **Presenter explanation:** "Twenty-nine of 270 accounts are flagged, five of them high severity, in three connected cases. Just as important is this panel: forty-three accounts looked a bit like layering and were set aside — and each one says why. The system tells you what it chose not to flag."

> **Warning:** Do not call the Exposure tile "money lost" or "fraud value". It is a sum of per-account evidence amounts and double-counts money that passed through several accounts.

> **Technical reference:** `frontend/src/pages/Overview.tsx`; `api.py` → `summary()`, `queue_items()`, `REVIEW_KINDS`; exposure computed in `pipeline.py` → `_finalise()`.

## 2.3 Investigation queue (`/queue`)

**A. What is this page?** The work list: every flagged account, most severe first.

**B. Question it answers:** "Which accounts should I investigate first?"

**C. What am I looking at?** A table: Account · Severity · score · Primary reason (the highest-scoring piece of evidence in plain language) · Patterns · Role · Exposure · Status. Ordering is severity, then score, then exposure, then account ID. Filters: Severity (High / Medium / Low), Pattern (Pass-through, Fan-in → fan-out, Layered receipt, Circular flow, Shared attributes), Status (Open / Confirmed / Cleared) and a free-text account filter. Filters live in the URL, so a filtered view can be shared or refreshed.

A **group row** appears only for a large IP-only cluster (more than 15 accounts sharing one IP when the data has no establishment evidence). It is one row with an expandable member list instead of many identical rows. The demo has none.

> **Verified numbers:** 29 queue items. Top five: AC5530 HIGH 95 (Hub), AC5562 HIGH 95, AC5547 HIGH 92, AC5521 HIGH 75, AC5579 HIGH 75. AC5530 is first because it ties AC5562 on score and has the larger exposure (₹8,33,000 vs ₹3,00,000).

**D. What happens when I click?**

- **Row** → opens `/account/{id}`.
- **Filter chip / account filter** → URL changes → `GET /api/queue?severity=&pattern=&status=&q=` → table reloads.
- **Export CSV** → browser downloads `GET /api/export/queue.csv` with the same filters → server uses the same filter function as the queue, so rows and order are identical. Columns: rank, type, id, members, severity, score, patterns, families, role, cases, exposure, currency, exposure_display, primary_reason, decision, decision_analyst, decision_note, decision_at_utc. UTF-8 with BOM so ₹ survives in spreadsheet tools; text starting with `=`, `+`, `-`, `@` is prefixed with `'`; the file name carries the dataset fingerprint and configuration hash.

**E. What should I say?**

> **Presenter explanation:** "The queue is ordered by evidence strength, not by guesswork. Every row carries the reason in one sentence, and the export gives the same list — same filters, same order — with the analyst's decisions, ready for a case file."

> **Technical reference:** `frontend/src/pages/Queue.tsx`; `api.py` → `filtered_queue()`, `queue()`, `export_queue()`, `queue_csv()`, `csv_safe()`.

## 2.4 Not flagged (`/reviewed`)

**A. What is this page?** The list of accounts whose activity was considered and set aside, each with the reason.

**B. Question it answers:** "What looked suspicious but was deliberately not flagged — and why?"

**C. What am I looking at?** Filters for scope (Not flagged / All, including flagged) and reason (each chip shows a count). Rows: Account · Reason · Why it was set aside · Outcome. Identical statements collapse into one expandable row — for example the shared office IP appears once with "23 accounts". "No pattern" is available but switched off by default.

Reason labels and what they mean:

| Label | Meaning |
|---|---|
| Downgraded by history | A pass-through episode was moved down one tier per mitigation because funding and/or payees were established relationships |
| Likely origin of funds | The account sent money into a flagged case from its own balance or established relationships; its flow signals are not scored |
| Origin (contra-indicated) | Likely origin, but something argues against the possible-victim reading (reasons listed) |
| Shared infrastructure | A shared device / IP / KYC value used mostly by established accounts; not treated as evidence |
| Isolated pass-through | A single pass-through episode, not linked to other pass-through accounts |
| Pooled account | ≥ 50 counterparties over ≥ 7 days; traced money stops there |
| Uncorroborated | A moderate-strength pattern with nothing corroborating it |
| Near miss | Pattern found but only at the weak tier, which never scores |
| Two-party exchange | Money went A → B → A; recorded as refund / repayment behaviour, not scored |
| History unavailable | The dataset is shorter than 7 days, so relationship-based checks could not run |
| No pattern | Nothing notable found (off by default) |

> **Verified numbers:** 43 not-flagged accounts with a stated reason — the same figure as the Overview.

**D. What happens when I click?** Chips and the account filter change the URL → `GET /api/observations?kind=…&flagged=false&q=…` → list reloads. A grouped row expands to show its accounts; any account ID opens the account page.

**E. What should I say?**

> **Presenter explanation:** "This is the part most tools don't have: a page of what we chose *not* to flag. The payroll company, the busy merchant, the office network, the near-miss forwarder — every one is here with the rule that set it aside."

> **Technical reference:** `frontend/src/pages/Reviewed.tsx`; `api.py` → `observations()`; texts produced in `backend/muletrace/explain.py` → `observations()`.

## 2.5 Suspicious cases (`/cases`)

**A. What is this page?** One row per connected money flow that contains at least one flagged account.

**B. Question it answers:** "Which groups of accounts belong together, and which group needs attention first?"

**C. What am I looking at?** Per case: ID · severity (the highest severity among its flagged members — a case has no score of its own) · "flagged: 5 high · 4 low" · decision progress ("0 of 9 flagged confirmed") · Accounts (flagged) · Value from likely origins (or "no likely origin identified") · Window · Median dwell · Evidence families. Ordering: severity, then cases not yet fully confirmed, then case order. The footer says how many connected flows with no flagged account are not listed.

> **Verified numbers:** 3 cases listed; 2 connected flows without a flagged member are not listed.
>
> - **CASE-03** HIGH · 5 high, 4 low · 11 accounts (9 flagged) · ₹6L from 2 likely origins · 25 Mar 10:01–13:34 (3 h 33 min) · median dwell 7 min · Circularity · Money flow · Shared identity
> - **CASE-02** MEDIUM · 4 medium, 3 low · 12 accounts (7 flagged) · ₹4.39L from 5 likely origins · 28 Mar 14:03–14:40 (37 min) · median dwell 17 min · Money flow
> - **CASE-04** MEDIUM · 4 medium · 4 accounts (4 flagged) · no likely origin identified · 22 Mar 11:00–15:15 (4 h 15 min) · median dwell 1 h 25 min · Circularity · Money flow

**D. What happens when I click?** The whole row opens `/case/{id}`. Data comes from `GET /api/cases`, which only reads the existing analysis.

**E. What should I say?**

> **Presenter explanation:** "Instead of thousands of transactions, the investigator gets three cases. The top one is the ring we'll open — eleven accounts, nine flagged, everything inside three and a half hours."

> **Technical reference:** `frontend/src/pages/Cases.tsx`, `frontend/src/lib/cases.ts`; `api.py` → `case_list()`.

## 2.6 Account investigation (`/account/{id}`)

**A. What is this page?** The investigation workspace for one account. It is the heart of the demo.

**B. Questions it answers:** "Why was this account flagged?", "How did money move through it?", "Who else is involved?", "What did the analyst decide?"

**C. What am I looking at?** Three columns on a wide screen (stacked on a phone).

**Header:** account ID, severity and score badge, role badge (for example "Hub", "Relay", "Likely origin", "Pooled"), decision status, and the primary reason. A not-flagged account says so and points to "Why this account is not flagged". For a likely origin in a flagged case, a coloured note appears: "Observed role: Likely origin — possible-victim indicator present" followed by *"Indicators consistent with a possible victim. This is not a determination."*

**Left column**

- **Why this account · score** — the score out of 100, severity, number of independent evidence families, exposure, then each family (Money flow /60, Circularity /20, Shared identity /20) with every scoring component: points, rule name, tier and the one-sentence detail. A negative "Family cap" line shows where a family hit its cap. A "not a probability" hint and the **Method** button sit in this card.
- **Analyst decision** — note box, reason shortcuts, Confirm / Clear (and Reopen once decided), "Recorded as <name>", and the audit trail. See Part 12.
- **Account profile** — establishment (new / established / unknown, with the basis), active period, received and sent totals and counts, counterparties, device / IP / KYC values seen.

**Centre column**

- **Graph** with three tabs: **Network**, **Where money came from**, **Where money went**. The Network tab has Hops (1–3, default 2), "Suspicious flows only" (on by default) and "Shared attributes" toggles. Toolbar: Find account in graph, Fit all, Full screen; legend underneath. If an account has no suspicious flows, the Network view automatically shows all of its activity and says so. Details in Parts 10 and 11.
- **What happened · <pattern>** — the timeline of the selected evidence (or the first scored evidence when none is selected): time, +gap since the previous row, sender → receiver, amount, "held N min at <account>", transaction ID.
- **Transactions** — "Show all transactions" loads the account's latest 500 transactions; rows that belong to a flagged flow are tinted and marked "in flagged flow".

**Right column**

- **Evidence** — one card per *scored* signal: label, tier, points, the reason sentence, metric chips (for example "99.5% conserved", "dwell 5 min", "linked to 4 relays"), the account path, the number of transactions. Below the cards, the traced relay path if one exists.
- **Connected case · CASE-xx** — the account's (first) case: accounts and flagged count, value from origins, window, median dwell, evidence families, confirmation progress, member list with roles and severities, **Open case** link.
- **Why this account is not flagged** (not-flagged accounts) or **Also considered (not scored)** (flagged accounts) — every observation with its label and sentence.

**D. What happens when I click?**

- **Evidence card** → the card is selected (click again to deselect) → no API call → the graph fades everything outside that evidence (its transactions, path and, for shared attributes, the accounts sharing the value) and a banner says "Highlighting the … evidence — other accounts and links are faded" with **Show all**; the timeline switches to that evidence.
- **Graph tab** → URL gets `?view=back` or `?view=fwd` → `GET /api/accounts/{id}/network?hops=&suspicious_only=` or `GET /api/accounts/{id}/trace?dir=back|fwd` → new graph.
- **Hops / filters** → network refetched with the new parameters.
- **Click a node** → selects it (halo) and shows its details plus a link: "Investigate" (network) or "Trace from this account" (trace views).
- **Double-click a node** → Network view: `GET /api/accounts/{node}/network?hops=1` and the neighbourhood is merged into the drawing. Trace views: opens that account's own trace (traces are never merged, so one trace's exact accounting is never mixed with another).
- **Confirm / Clear / Reopen** → `POST /api/accounts/{id}/disposition` → see Part 12.
- **Open case** → `/case/{id}`.
- **Show all transactions** → `GET /api/accounts/{id}/transactions`.

**E. What should I say?**

> **Presenter explanation:** "Every point in this score is a rule plus transactions. Pass-through: 8.37 lakh in, 8.33 lakh out, average five minutes. It's a hub — three senders, three receivers. It sits on a traced path of three fast relays. Money came back to it in a circle. And it shares a device with three other new accounts. Ninety-five out of a hundred — that's evidence strength, not a probability."

> **Technical reference:** `frontend/src/pages/Investigate.tsx`, `frontend/src/components/Investigation.tsx` (ScoreCard, SignalCard, Timeline, WhyNot, DispositionPanel, CaseCard, IndicatorNote); `api.py` → `account_detail()`, `signal_view()`; reasons from `explain.py` → `signal_reason()`, `component_detail()`.

## 2.7 Case investigation (`/case/{id}`)

**A. What is this page?** The whole connected flow on one screen.

**B. Questions it answers:** "How did money enter, move through and leave this group?", "Who is in it and in which role?"

**C. What am I looking at?**

- **Header facts:** accounts, flagged, "N of M flagged confirmed", value entered from likely origins (only when there is one), window and duration, median dwell.
- **Money-flow summary** (Entry · Movement · Exit · Period) — fixed-template sentences built from the case data, labelled "from the case's computed data", with a **Method** button. See Part 9.
- **Case network** — every member and the case transactions between them, with roles and severities; "Shared attributes" toggle; Find, Fit all, Full screen, legend. Over 80 members, a connected subset built from the most valuable money paths is drawn and the note says "Showing N of M accounts".
- **Members and observed roles** — flagged members first; Account · Role · Severity · Status. Clicking a row selects that member.
- **Case timeline** — case transactions in time order (first 200 if there are more; the header says so). With a member selected, it shows only that member's case transactions.

**D. What happens when I click?**

- **Member row or node** → selected → `GET /api/cases/{id}?member=<account>` → its transactions light up on the graph and the timeline narrows to that member.
- **Double-click a node** or **Investigate** → opens the account page.
- **Method** → opens the read-only method panel.

**E. What should I say?**

> **Presenter explanation:** "Here's the whole ring. Two likely origins sent six lakh in at 10:01 and 10:02. It moved through one hub and five relays, and came to rest in three sink accounts by 13:34. The summary is built only from the case data — and notice it calls the twenty-eight lakh total 'transaction volume, not an amount lost'."

> **Technical reference:** `frontend/src/pages/CasePage.tsx`; `api.py` → `case_detail()`, `case_network()`, `case_summary_view()`; `backend/muletrace/summary.py`; `backend/muletrace/network.py` → `case_network()`, `_case_story()`.

## 2.8 Method panel (dialog)

Opened from the **Method** button in the account score card and in the case summary header. A read-only modal titled "How MuleTrace scores", with rows for Severity, Score, Pass-through strength, Patterns, Money tracing and False-positive defences, and a footer "Engine flow · configuration b652e4bf70db · read-only". Escape, the backdrop or the X button close it and focus returns to the button. Details in Part 13.

> **Technical reference:** `frontend/src/components/MethodPanel.tsx`, `frontend/src/lib/method.ts`, `GET /api/config`.

## 2.9 Responsive and theme behaviour

- Light and dark themes come from colour tokens; severity and decisions are never shown by colour alone (words, icons, ring styles and line styles carry the same meaning).
- At phone width (375 px) pages fit without horizontal scrolling; the header is not sticky below the small breakpoint; the inline graph becomes a still preview with **Open graph to explore** (full screen) so the page scrolls normally.

# Part 3 — Internal Pipeline

## 3.1 The intuitive version

```
CSV
 → ingestion ............ read, validate, de-duplicate, normalise (time, money, currency)
 → profiles ............. one profile per account; new vs established; relationship history
 → pooled check ......... very busy accounts are marked "pooled"
 → FIFO flow links ...... each outgoing payment is linked to the incoming money that funded it
 → episodes ............. linked inflows + outflows of one account grouped into "episodes", graded by tier
 → raw signals .......... pass-through, fan-in → fan-out hub, layered receipt, circular flow, shared attributes
 → cases ................ connected suspicious movement becomes a case
 → roles + indicator .... origin / hub / relay / collector / distributor / sink / pooled; possible-victim indicator
 → mitigations .......... established relationships can lower an episode's tier
 → qualification ........ which signals are allowed to score
 → scoring + severity ... points per evidence family, family caps, HIGH / MEDIUM / LOW
 → explanations ......... reason sentences, observations, "why not flagged"
 → UI ................... Overview, queue, cases, account and case pages
```

The order is fixed and no stage reads the output of a later stage. The whole analysis is a pure function of (transactions, configuration): it runs on every upload and at every server start, and is held in memory. Only the raw CSV, analyst decisions and the audit log are stored.

> **Presenter explanation:** "Think of it as an assembly line with twelve fixed stations. The file goes in, every payment is linked to the money that paid for it, patterns are found on those links, we check for innocent explanations, and only then do we score. Same file, same settings — same answer, every time."

> **Technical reference:** `backend/muletrace/pipeline.py` → `analyze()` runs the stages; `_finalise()` writes reasons and exposure. Stage modules: `ingest.py`, `profiles.py`, `flow.py`, `signals.py`, `identity.py`, `cases.py`, `scoring.py`, `explain.py`.

## 3.2 Stage by stage

### Stage 1 — Ingestion (`ingest.py`)

1. **Receives:** raw CSV bytes.
2. **Produces:** a list of normalised transactions sorted by (time, transaction ID) and an ingestion report.
3. **Why:** real files are messy; the analysis needs one clean, typed form.
4. **Invariant:** money is stored as integer paise (no floating point); time as integer epoch seconds; every rejected row is counted and the first 200 are listed with row number and reason.
5. **Presenter needs to know:** headers are matched through an alias table (for example `from`/`to`, `nameOrig`/`nameDest`, `step`), so common public layouts load without editing. Naive timestamps are read as IST. If every time value is an integer below 1,000,000 the column is treated as an hour-step index. The dominant currency becomes the dataset currency; rows in other currencies are rejected (no conversion). Limits: 20 MB and 200,000 rows. A `label` / `isFraud` column is recognised but **never used by detection**.
6. **Judge might ask:** "What if the file has errors?" → rows are rejected individually with reasons; a missing required column rejects the whole file with the list of detected headers. "What about duplicates?" → an exact duplicate (same ID and content) is dropped and counted; the same ID with different content keeps the first and rejects the later one.

### Stages 2–3 — Profiles, establishment, relationships, pooled (`profiles.py`)

1. **Receives:** clean transactions.
2. **Produces:** per account: first / last seen, in / out counts and totals, counterparties, device / IP / KYC values, opening date, establishment, pooled flag. Per counterparty pair: a running money history.
3. **Why:** later stages need to know who is new, who is long-standing, and which payments travel over a genuine, established relationship.
4. **Invariant:** age and history are measured relative to the dataset, never against the computer's clock.
5. **Presenter needs to know:**
   - **Establishment:** with an opening date, an account is NEW if it was ≤ 30 days old at its first activity, otherwise ESTABLISHED. Without opening dates but with ≥ 14 days of data, it is ESTABLISHED if it was active over ≥ 14 days. Otherwise UNKNOWN.
   - **Relationship** for one payment: ESTABLISHED when the pair's money exchanged more than 7 days earlier is at least **50 %** of what they exchanged in the last 7 days (that payment included). NOVEL otherwise, after the first 7 days of the dataset. During the first 7 days it is UNKNOWN, which never suppresses anything.
   - **Pooled:** ≥ 50 distinct counterparties **and** active over ≥ 7 days.
6. **Judge might ask:** "Can a fraudster fake a relationship with a small early payment?" → no: a ₹1,000 payment two weeks earlier does not establish a ₹3 L relationship; history must be at least half of the recent volume. This rule is covered by `test_relationship.py`.

### Stages 4–5 — FIFO flow links and episodes (`flow.py`)

1. **Receives:** transactions and profiles.
2. **Produces:** flow links ("₹X of incoming transaction A left as outgoing transaction B after N minutes"), the untraceable "own funds" part of each outgoing payment, and episodes graded STRONG / MODERATE / WEAK.
3. **Why:** a transfer graph shows who paid whom; flow links show *which* money moved on and how fast. That is what separates a pass-through mule from an account spending its own salary.
4. **Invariant:** for every outgoing payment, linked amounts + own funds = the payment amount; no incoming payment is used for more than its value; dwell is never negative; results do not depend on CSV row order.
5. **Presenter needs to know:** see Part 4. Episodes need ≥ ₹10,000 of inflow to be graded; links below ₹1,000 count for accounting only.
6. **Judge might ask:** "Why FIFO?" → it is a transparent, reproducible convention; it is documented as a convention, not as ground truth.

### Stage 6 — Raw signals (`signals.py`, `identity.py`)

1. **Receives:** episodes, links, profiles.
2. **Produces:** raw RELAY, HUB, LAYERED_RECEIPT, ROUND_TRIP and IDENTITY signals with a raw tier, metrics and transaction IDs.
3. **Why:** each signal is one recognisable layering structure.
4. **Invariant:** every signal points at concrete transactions or attribute values.
5. **Presenter needs to know:** raw signals are candidates. They do not score until mitigations and qualification have run.
6. **Judge might ask:** "Is a single fast forward enough to flag someone?" → no (see qualification).

### Stages 7–8 — Cases, roles and the possible-victim indicator (`cases.py`)

1. **Receives:** raw signals and links.
2. **Produces:** cases (connected components of suspicious movement), structural roles per case, likely origins and the possible-victim indicator, plus the "corroborated path" list used to block mitigations.
3. **Why:** investigators work on networks, not on single accounts; and the origin of the money — often a victim — must be told apart from the accounts that pass it on.
4. **Invariant:** roles are structural and independent of score; a case is built only from the transactions that made accounts suspicious, never from every payment they ever made.
5. **Presenter needs to know:** see Parts 6 and 8.
6. **Judge might ask:** "How do you avoid flagging the victim?" → origin accounts' flow signals are not scored unless something contradicts the victim reading (Part 6).

### Stage 9 — Mitigations (`scoring.py` → `apply_mitigations()`)

1. **Receives:** episodes, cases, relationship history.
2. **Produces:** a final tier per episode: one tier lower for each of ESTABLISHED_FUNDING and ESTABLISHED_PAYEES (≥ 80 % of the money from / to established relationships with accounts that are not themselves moving suspicious money).
3. **Why:** payroll, settlement and other routine pass-through patterns look like relays.
4. **Invariant:** no mitigation on an episode that sits on a corroborated rapid-layering path, or whose counterparties are new on both sides. Account age and history are never mitigations on their own.
5. **Presenter needs to know:** a mitigation lowers a tier; it never deletes evidence silently — it produces a "Downgraded by history" observation.
6. **Judge might ask:** "Couldn't a mule build history to escape?" → only by moving at least half the attack value through the same pair more than 7 days in advance, and never if the episode is on a corroborated rapid path.

### Stage 10 — Qualification (`scoring.py` → `score()`)

1. **Receives:** final tiers, cases, identity results.
2. **Produces:** for each signal, whether it may score; non-qualifying signals become observations ("Isolated pass-through", "Uncorroborated").
3. **Why:** one fast forward is ordinary life (salary → rent). Structure needs corroboration.
4. **Invariant:** WEAK never scores.
5. **Presenter needs to know:** a pass-through scores only if it is linked to another relay, repeats (≥ 3 episodes) or comes with another evidence family. Hub, layered receipt and circular flow score at STRONG alone; at MODERATE they need corroboration.
6. **Judge might ask:** "Why didn't AC6101 get flagged? It forwarded 89 % in 41 minutes." → single, isolated episode; not linked to any other relay.

### Stage 11 — Scoring and severity (`scoring.py` → `_score_account()`)

1. **Receives:** qualifying signals.
2. **Produces:** score components (rule, points, tier, detail), score, severity, evidence families.
3. **Why:** a transparent ranking of evidence strength.
4. **Invariant:** score = sum of components; 0 ≤ score ≤ 100; flagged ⇔ score > 0.
5. **Presenter needs to know:** Part 7.
6. **Judge might ask:** "Is 95 a 95 % probability?" → no; it is an evidence-strength index.

### Stage 12 — Explanations (`explain.py`, `pipeline.py` → `_finalise()`)

1. **Receives:** everything above.
2. **Produces:** the reason sentence for every signal and component, the primary reason, observations (why not flagged), exposure.
3. **Why:** every conclusion must be readable by an investigator.
4. **Invariant:** sentences are generated only from computed metrics.
5. **Presenter needs to know:** the wording on screen is generated, not hand-written per account.
6. **Judge might ask:** "Who wrote these explanations?" → fixed sentence templates filled with the computed numbers.

# Part 4 — FIFO Money Flow

This is the core technical idea. "Following the money" in MuleTrace means one precise thing: **every outgoing payment of an account is matched to the earliest still-available incoming payments of that account, first in, first out, to the paisa.** Each match is a *flow link*.

## 4.1 Funding lots and FIFO consumption

For every account that is not pooled, MuleTrace replays its payments in time order:

- each **incoming** payment becomes a *lot* in a queue: (transaction, time, remaining amount);
- each **outgoing** payment consumes lots from the front of the queue (oldest first) until it is covered; every consumption creates a **flow link** (incoming transaction, outgoing transaction, amount, dwell = time between them);
- whatever part of an outgoing payment is not covered by a live lot is the account's **own funds** (money that was already there before the data, or that arrived more than 72 hours earlier);
- a lot older than **72 hours** at the moment of a payment expires: it becomes untraceable balance and is never linked;
- at the same timestamp, incoming payments are processed before outgoing ones, then in input order;
- each account is processed independently, so a timestamp collision between two different accounts cannot drop a link.

## 4.2 Example 1 — one lot, two payments

A receives ₹1,00,000 from X at 10:00. A sends ₹60,000 to B at 10:05 and ₹40,000 to C at 10:20.

| Step | Lot queue before | Outgoing | Flow links created | Own funds |
|---|---|---|---|---|
| 10:00 in | — | — | lot X→A ₹1,00,000 added | — |
| 10:05 out | X→A ₹1,00,000 | A→B ₹60,000 | X→A ⇒ A→B ₹60,000, dwell 5 min | ₹0 |
| 10:20 out | X→A ₹40,000 left | A→C ₹40,000 | X→A ⇒ A→C ₹40,000, dwell 20 min | ₹0 |

MuleTrace attributes ₹60,000 of X's money to B and ₹40,000 to C. A's episode: inflow ₹1,00,000, outflow ₹1,00,000, forwarded ₹1,00,000 (100 % conserved), amount-weighted dwell (60,000×5 + 40,000×20) / 1,00,000 = 11 min → **STRONG** (≤ 30 min and ≥ 90 %).

## 4.3 Example 2 — two lots, partial coverage

A receives ₹50,000 from X at 09:00 and ₹30,000 from Y at 09:30. A sends ₹70,000 to B at 09:40 and ₹20,000 to C at 10:00.

| Step | Lot queue before | Outgoing | Flow links created | Own funds |
|---|---|---|---|---|
| 09:40 out | X ₹50,000 · Y ₹30,000 | A→B ₹70,000 | X ⇒ B ₹50,000 (40 min) · Y ⇒ B ₹20,000 (10 min) | ₹0 |
| 10:00 out | Y ₹10,000 | A→C ₹20,000 | Y ⇒ C ₹10,000 (30 min) | **₹10,000** |

All four transactions are connected through links, so they form one episode: inflow ₹80,000, outflow ₹90,000, forwarded ₹80,000. Traced conservation = forwarded ÷ max(inflow, outflow) = 80,000 ÷ 90,000 = 88.9 %. Amount-weighted dwell = (50,000×40 + 20,000×10 + 10,000×30) ÷ 80,000 = 31.25 min. Dwell is just over the 30-minute STRONG bound and conservation is under 90 %, so the episode is **MODERATE**.

Why divide by the larger of inflow and outflow? Because an account that receives ₹10,000 and sends ₹1,00,000 is mostly spending its own money — it is not a relay. Conservation must hold in both directions.

## 4.4 Tiers

| Tier | Dwell (amount-weighted) | Conservation | Scores? |
|---|---|---|---|
| STRONG | ≤ 30 min | ≥ 90 % | yes |
| MODERATE | ≤ 6 h | ≥ 80 % | yes |
| WEAK | ≤ 72 h | ≥ 70 % | never — "Near miss" observation |

The traced tier is the weaker of the dwell tier and the conservation tier. A second test, the **window test**, protects against reservoir tricks (keeping an old balance at the front of the FIFO queue so new money looks like it "stays"): for each incoming lot of at least ₹10,000 and each tier bound B, it compares the total of the account's outgoing payments within B of the lot with the lot amount (match = smaller ÷ larger). The episode's tier is the better of the traced tier and the window tier. Keeping 11 % instead of 10 % moves an account down one tier; it does not make it invisible.

## 4.5 Thresholds and bounds

| Rule | Value | Effect |
|---|---|---|
| Linking horizon | 72 h | lots older than this expire; slower flows are not linked |
| Smallest structural link | ₹1,000 | smaller links are kept for accounting, excluded from episodes, chains, cases, round trips |
| Smallest episode | ₹10,000 inflow | smaller episodes are not graded |
| Pooled boundary | ≥ 50 counterparties over ≥ 7 days | the account emits no links; traces stop there |
| Trace hop limit | 8 hops | money beyond is reported as "beyond hop limit" |
| Trace start set | up to 25 transactions (evidence or case transactions), else the 10 largest | keeps the trace focused on the suspicious movement |
| Trace drawing | 50 nodes | the smallest traced accounts are grouped into one "+N accounts" node |
| Round-trip search | ≤ 6 accounts, ≤ 72 h, the 10 largest links per step | bounded search, pooled accounts never traversed |

## 4.6 Multi-hop tracing with exact fractions

A trace follows links hop by hop. When money that is being traced enters a transaction that mixes several sources, the trace follows each source **in proportion**:

> traced amount continuing = traced amount in this transaction × (link amount ÷ transaction amount)

Example: X's ₹50,000 reached B inside A→B (₹70,000). If B later forwards ₹35,000 to D, funded by that ₹70,000 lot, the trace carries 50,000 × 35,000 ÷ 70,000 = ₹25,000 of X's money to D, and ₹25,000 stays at B.

The arithmetic uses exact fractions (Python `fractions.Fraction`); amounts are rounded only for display. For every trace:

> start amount = retained along the way + stopped at pooled accounts + beyond the hop limit — **exactly**.

The console prints "· exact" under a trace when this check passes.

## 4.7 Pooled-account boundary

A pooled account (≥ 50 counterparties over ≥ 7 days — a merchant, an aggregator, a utility) mixes money beyond reliable attribution. MuleTrace therefore creates **no** flow links for it: all its outgoing payments count as own funds, traces stop there ("stopped at pooled"), round-trip search never passes through it and relay chains end at it. Detection on the pooled account itself stays on (Part 15).

## 4.8 What this buys the investigator

- "₹4,78,000 of TX102080 left as TX102081 after 3 minutes" is a statement about specific transactions, not about a graph edge.
- Pass-through, hub, layered receipt, round trip and chains are all defined on links, so they describe the movement of the *same money*, not just a sequence of transfers.
- Conservation can be checked: a trace always adds up to the paisa.

> **Presenter explanation:** "Following the money here is literal. Every outgoing payment is matched to the oldest incoming money still in the account, first in, first out. So when we say four lakh seventy-eight thousand of the victim's transfer left as the next transfer three minutes later, that's a specific link between two transaction IDs — and when we trace further, the numbers always add up exactly."

> **Warning:** FIFO attribution is a **convention**, not ground truth. Money is fungible; the bank does not label rupees. Say "attributed by FIFO" or "traced", never "this exact money was proven to go there".

> **Judge may ask:** "Why not LIFO or proportional?" — FIFO is simple, standard in fund-tracing practice, reproducible and easy to audit; the window test covers the reservoir case where FIFO alone could be gamed. Other conventions are not implemented.

> **Technical reference:** `backend/muletrace/flow.py` → `build_links()` (lots, links, own funds, expiry), `build_episodes()`, `_window_tier()`, `_pooled_episodes()`, `trace()`; tests in `backend/tests/test_flow_engine.py` (conservation, determinism, row-order independence, same-timestamp chain, lot expiry, fragmented inflows, pooled boundary, exact trace with awkward splits, reservoir decoy).

# Part 5 — Detection Signals

## 5.1 Families, signals and bonuses

MuleTrace has **five signals** grouped into **three independent evidence families**, plus **bonus components** that only add to the money-flow family. FLOW, CIRCULARITY and IDENTITY are families, not signals. DEVICE, KYC and IP are the three attribute types inside the IDENTITY signal.

| Family (cap) | Signal or component | On screen |
|---|---|---|
| FLOW — Money flow (60) | RELAY | Pass-through |
| | HUB | Fan-in → fan-out (hub) |
| | LAYERED_RECEIPT | Layered receipt / Received layered funds |
| | bonus: REPEATED | Repeated pass-through |
| | bonus: CHAIN | Part of a relay chain |
| | bonus: CORROBORATED_LAYERING | Corroborated rapid layering |
| | bonus: CONSOLIDATION | Consolidates several chains |
| CIRCULARITY — Circularity (20) | ROUND_TRIP | Circular flow / Circular money flow |
| IDENTITY — Shared identity (20) | IDENTITY (device, KYC, IP) | Shared attributes / Shared device / KYC / IP |
| | bonus: ADDITIONAL_LINK_TYPE | Additional shared attribute |

> **Warning:** No signal proves a crime. Each is a structure that layering commonly produces — and that some legitimate activity can also produce. That is why there are mitigations, qualification rules and a "Not flagged" page.

## 5.2 RELAY — Pass-through

- **Detects:** an account that receives money and sends most of it on quickly.
- **Exact logic:** the account's best episode tier (Part 4): traced tier = weaker of dwell tier and conservation tier, improved by the window test; inflow ≥ ₹10,000. Raw tier then goes through mitigations (Stage 9).
- **Qualifies (may score) when** final tier is STRONG or MODERATE, the account is not a zeroed origin, **and** at least one of: it exchanges suspicious-flow transactions directly with another relay (≥ MODERATE); it has ≥ 3 episodes at ≥ MODERATE; it has evidence in another family (circularity or shared identity).
- **Evidence used:** flow links, dwell, conservation, window match, episode transactions.
- **Does not prove:** that the account holder knew, or that the money was criminal. Payroll accounts, settlement accounts and someone paying rent from a salary also pass money through.
- **Demo example:** AC5521 — "Received ₹4,80,000 and forwarded ₹4,78,000 (99.6% conserved) after an average of 3 min (25 Mar 10:02–10:05)." STRONG. A MODERATE example: AC3501 — 86 % conserved after 1 h 10 min.
- **In the UI:** evidence card "Pass-through" with chips "% conserved", "dwell", "linked to N relays", and "downgraded: …" when mitigated; the traced relay path under the cards.
- **Judge may ask:** "Lots of people forward their salary." → A single isolated pass-through is never scored; it becomes an "Isolated pass-through" observation (demo AC6101).
- **Presenter-safe:** "This account received money and passed almost all of it on within minutes, and it's connected to other accounts doing the same."

## 5.3 HUB — Fan-in → fan-out

- **Detects:** money arriving from several senders and leaving to several receivers in one burst.
- **Exact logic:** take the account's episodes at ≥ MODERATE; group them into bursts that start within 6 h of the burst's first episode; a burst needs **≥ 3 distinct senders and ≥ 3 distinct receivers** (counted across episodes, so A→X, B→Y, C→Z through one account is a hub). The hub's tier is the weaker of its burst dwell tier and burst conservation tier; it must be at least MODERATE. Recomputed after mitigations.
- **Evidence used:** the burst's incoming and outgoing transactions, matched amount, dwell, conservation.
- **Does not prove:** coordination. Payroll fan-out and marketplaces also fan out; those are handled by mitigations and the pooled rule.
- **Demo example:** AC5530 — "Funds from 3 senders (₹8,37,000) were passed to 3 receivers (₹8,33,000) between 25 Mar 10:05 and 13:34; 99.5% of the money moved on." AC4400 — 5 senders (₹4,39,000) to 3 receivers, 97 % moved on.
- **In the UI:** card "Fan-in → fan-out" with chips "N senders", "N receivers", "% moved on"; role badge "Hub".
- **Judge may ask:** "Why only +5 for the hub on AC5530?" → Only the strongest money-flow signal earns its full points; each additional base signal adds +5.
- **Presenter-safe:** "Money from three different accounts came in, and went out to three others, almost all of it, within the same burst."

## 5.4 LAYERED_RECEIPT — Layered funds received (and CONSOLIDATION)

- **Detects:** the end of a layering chain — an account that receives money which has already passed through relays, and keeps it.
- **Exact logic:** for each incoming payment ≥ ₹1,000 of which at most 20 % is forwarded, walk the FIFO links backwards while the sender is a relay; count consecutive relays. **≥ 2 relays** required. Span = receipt time − the earliest transaction on that path. STRONG if span ≤ 6 h, MODERATE if ≤ 72 h. At qualification the relays are re-checked against final relay tiers, so a likely origin never counts as a relay. **CONSOLIDATION** (+10) applies when the qualifying receipts come from ≥ 2 distinct upstream relay senders.
- **Does not prove:** that the receiver is a cash-out mule. It is the edge of the visible data; withdrawals and other banks are not in the file.
- **Demo example:** AC6610 — "Received ₹1,40,000 that had passed through 3 relay accounts in 13 min (AC2207 → AC5521 → AC5530 → AC5547 → AC6610) and kept it." AC6651 — 2 relays in 3 h 33 min (still STRONG, ≤ 6 h). Consolidation does not occur in the demo.
- **In the UI:** card "Layered receipt" with chips "N relays upstream", span, and "N chains converge" when consolidating; role usually "Sink".
- **Judge may ask:** "Why only LOW 20 for the cash-out accounts?" → They have one signal in one family; severity follows evidence strength, and the case keeps them together with the HIGH relays.
- **Presenter-safe:** "This account received money that had already been passed through several fast relays — and it kept it."

> **Note:** the path text starts with the account that first sent the money (for AC6610, the likely origin AC2207). The relay count excludes that first sender.

## 5.5 CHAIN — Part of a relay chain (bonus +10)

- **Detects:** a traced path through **≥ 3 consecutive relays** (each ≥ MODERATE), following FIFO links (10 largest per step, up to the trace hop limit).
- **Applies to:** an account with a qualifying RELAY that lies on such a path, and only if it does not already get CORROBORATED_LAYERING.
- **Demo example:** AC3501, AC3502, AC3503 — "Part of a traced path through 3 relay accounts (AC3501 → AC3502 → AC3503) spanning 4 h 15 min." +10 each.
- **Presenter-safe:** "The same money went through three pass-through accounts in a row."

## 5.6 CORROBORATED_LAYERING — Corroborated rapid layering (bonus +25)

- **Detects:** a traced path through **≥ 3 STRONG relays** whose end-to-end span is **≤ 60 minutes**.
- **Two uses:** (1) a +25 bonus for each qualifying relay on the path; (2) at the raw stage, episodes on such a path can **never be mitigated** by relationship history.
- **Demo example:** AC5521 → AC5530 → AC5547, 16 min; AC5579 → AC5530 → AC5562, 18 min; AC5521 → AC5530 → AC5562, 17 min.
- **In the UI:** score line "Corroborated rapid layering"; "Traced relay path: AC5521 → AC5530 → AC5547" under the evidence cards; the path is highlighted when the Pass-through card is selected.
- **Judge may ask:** "Why such a big bonus?" → Three independent accounts each passing on ≥ 90 % within 30 minutes, linked by the same money inside an hour, is the clearest layering structure in the data; it is also what blocks history-based downgrades.
- **Presenter-safe:** "Three accounts, each forwarding almost everything within minutes, and the same money went through all three inside a quarter of an hour."

## 5.7 REPEATED (bonus +5)

A qualifying relay with **≥ 3 pass-through episodes** at ≥ MODERATE gets +5 ("N pass-through episodes"). Not present in the demo.

## 5.8 ROUND_TRIP — Circular flow

- **Detects:** money that actually comes back — not just a loop in the graph.
- **Exact logic:** from each outgoing payment ≥ ₹10,000 of a non-pooled account, follow FIFO links forward (largest 10 per step, structural links only) with exact fractions; if traced funds return to the starting account through **≥ 2 other accounts** within **≤ 6 accounts** in the cycle: STRONG when the return happens within **24 h** and **≥ 50 %** of the original payment comes back; MODERATE within **72 h** and **≥ 30 %**. Pooled accounts are never traversed. A two-party back-and-forth (A → B → A) is only a "Two-party exchange" observation (refunds, repayments).
- **Qualifies:** STRONG alone; MODERATE with another family or a case with ≥ 3 relays.
- **Evidence used:** the cycle's transactions, returned amount, ratio, span.
- **Does not prove:** wash trading or criminal intent; it proves that by FIFO attribution, a share of the money returned to where it started.
- **Demo examples:** AC5530 — "₹1,50,000 of ₹3,00,000 (50%) returned to its starting account in 3 h 18 min: AC5530 → AC5562 → AC6624 → AC5530." (STRONG, exactly at the 50 % bound). AC5547 — ₹90,000 of ₹2,95,000 (30.5 %) in 3 h 19 min (MODERATE). Ring AC3500 → AC3501 → AC3502 → AC3503 → AC3500 — ₹1,65,375 of ₹2,60,000 (63.6 %) in 4 h 15 min (STRONG).
- **In the UI:** card "Circular flow" with chips "% returned", span, "N accounts"; on the graph, money flowing back is drawn as an arc.
- **Judge may ask:** "AC6624 sent ₹2,40,000 back — why do you say ₹1,50,000 returned?" → The ₹2,40,000 payment is funded by two FIFO lots; only the ₹1,50,000 that traces back to AC5530's own ₹3,00,000 payment counts as returned for that cycle.
- **Presenter-safe:** "Half of a three-lakh payment came back to the same account three hours later, through two other accounts."

## 5.9 IDENTITY — Shared attributes (DEVICE, KYC, IP)

- **Detects:** new (or age-unknown) accounts that share a device ID, KYC identifier or IP address.
- **Exact logic:**
  - Accounts sharing one value are a group. Only NEW or UNKNOWN accounts are eligible members.
  - **Minimum eligible members:** device **3**, IP **4**, KYC **2**.
  - **Infrastructure:** if the data allows establishment to be judged, a value shared by **≥ 5 established accounts that are ≥ 60 % of its sharers** is treated as shared infrastructure (office, campus, shared network) — not evidence. A large raw count alone never suppresses.
  - Qualifying groups are merged into clusters (union of overlapping groups).
  - **Points:** device or KYC link **15** (STRONG); IP-only link **8** ("weak evidence"); **+5 per additional link type** (ADDITIONAL_LINK_TYPE); family cap 20.
  - **Restoration:** accounts that themselves move suspicious money in the same flow case are linked by an infrastructure value anyway (precedence: a shared office network cannot hide two relays of one case).
  - Without establishment evidence, an IP-only cluster of more than 15 accounts is shown in the queue as one group row.
- **Does not prove:** common ownership. Families share devices; offices share IPs; KYC fields may be hashed phone numbers or documents of unknown quality.
- **Demo examples:**
  - **DEVICE** DV-7731AA: AC5521, AC5530, AC5547, AC5562 (4 new accounts) → +15 each.
  - **KYC** KYC-19C0FFEE: AC5547, AC5579 → AC5579 +15; AC5547 shares device *and* KYC → 15 + 5 = **20** (cap).
  - DEVICE DV-4410EE: AC5600–AC5604, five new barely used accounts → LOW 15 each, no money-flow evidence.
  - **IP** 103.77.12.9: AC5700–AC5703 → LOW **8** each, "Weak evidence: IP only."
  - **Infrastructure** 10.20.0.15: 23 accounts, 100 % established → "treated as shared infrastructure, not as evidence".
- **In the UI:** card "Shared attributes" with chips "shared device / KYC / IP", "weak evidence", "linked inside flow case" (restoration); dashed links without arrows on the graph labelled with the attribute type.
- **Judge may ask:** "Doesn't everyone in an office share an IP?" → Yes — that is exactly the infrastructure rule; the demo office IP with 23 established accounts is ignored as evidence.
- **Presenter-safe:** "These new accounts were used from the same device — that's an identity overlap worth checking, not proof they belong to one person."

> **Technical reference:** `backend/muletrace/signals.py` → `relay_signals()`, `hub_signals()`, `receipt_signals()`, `round_trip_signals()`, `classify_round_trip()`; `backend/muletrace/identity.py` → `build()`; `backend/muletrace/cases.py` → `relay_paths()` (chain and corroborated paths); `backend/muletrace/scoring.py` → `score()` (qualification), `_restore_identity()`. Tests: `test_scenarios.py` S1–S4, A1–A15, G1–G13.

# Part 6 — Account Roles

## 6.1 How roles are assigned

Roles are **structural**: they describe where an account sits in a case's money flow. They are computed per case from the case transactions, independently of the score, in this order (the first rule that fits wins):

| Role (on screen) | Rule |
|---|---|
| **POOLED** (Pooled) | the account is pooled (≥ 50 counterparties over ≥ 7 days) |
| **ORIGIN** (Likely origin) | no case transaction comes *into* it, it sends case transactions, and what it sent is funded ≥ 50 % by its own funds, **or** ≥ 80 % by established relationships with accounts not moving suspicious money, **or** covered by `balance_before` on every payment |
| **HUB** (Hub) | it has a raw HUB signal at ≥ MODERATE |
| **COLLECTOR** | a relay (≥ MODERATE) with ≥ 3 case senders and ≤ 2 case receivers |
| **DISTRIBUTOR** | a relay (≥ MODERATE) with ≤ 2 case senders and ≥ 3 case receivers |
| **RELAY** (Relay) | any other relay (≥ MODERATE); or an account that receives case money and forwards ≥ 20 % of it |
| **SINK** (Sink) | receives case money and forwards less than 20 % of it |
| **COUNTERPARTY** | anything else inside a case |
| **CLUSTER_MEMBER** | not in a case, but in a shared-attribute cluster |

**Display rule:** roles and the possible-victim indicator are shown only for cases that contain a flagged account (pooled accounts always show "Pooled"). A flow nobody was flagged for does not label its participants. In the demo, the payroll company AC7100 and the near-miss AC6101 have no role on screen for this reason.

**What a role does not mean:** "Hub" or "Relay" describes money movement, not a person's intent. "Sink" means the money stopped there *in the data* — cash withdrawals and transfers to other banks are invisible.

## 6.2 ORIGIN ≠ VICTIM

An ORIGIN is the account the money came *from*. In a mule network that is often a fraud victim — but MuleTrace never says so. It runs a separate check, the **possible-victim indicator**, only for ORIGIN accounts:

| Status | When | On screen |
|---|---|---|
| **INDICATED** | an ORIGIN with none of the contra-indicators below | "Indicators consistent with a possible victim. This is not a determination." |
| **CONTRA_INDICATED** | an ORIGIN that shares a **device or KYC** value with another member of its case; or received a payment **above ₹1,000** from a member of the case that moves suspicious money; or is itself in a shared-attribute cluster; or has a circular-flow signal; or originates money into **≥ 2 separate cases** | "Not consistent with a possible victim." plus the reasons |
| **NOT_ASSESSED** | every other account, and any account not in a flagged case | nothing shown |

**Effect on the score:** an ORIGIN's money-flow signals (pass-through, hub, layered receipt) score **0** unless the indicator is CONTRA_INDICATED. The account gets a "Likely origin of funds" observation instead.

**Why the ₹1,000 threshold?** Mule operators commonly send a ₹1 "verification ping" or a token "refund". Small amounts must not turn a victim into a suspect. In the demo, AC5521 sent AC2207 ₹1 at 09:55 and ₹499 at 11:30 — both at or below ₹1,000 — and AC2207 stays INDICATED.

**The relationship amendment (v1.2.1).** "Established relationship" is weighted by money, not by contact: history older than 7 days must be at least 50 % of what the pair moved in the last 7 days. Consequences for roles:

- A fraudster cannot make the first mule look like an origin by sending the victim a token payment weeks earlier: the relationship stays NOVEL, the mule stays a relay, the victim stays the origin.
- A genuine salary still counts: AC3318's employer paid ₹82,000 on 1 Mar and ₹1,25,000 on 25 Mar; ₹82,000 ≥ 50 % × ₹1,25,000, so the salary relationship is ESTABLISHED. AC3318 forwarded its fresh salary to a mule 21 minutes after receiving it — a raw STRONG pass-through — yet it is correctly an ORIGIN because ≥ 80 % of what it sent was funded by that established relationship.
- Known limitation: if a victim genuinely sent the first mule at least half of the fraud value at least 7 days earlier, that mule reads as an origin; the rest of the chain and the cash-out are still flagged.

**Why the wording is cautious.** MuleTrace sees transactions, not people, intent or consent. A transaction pattern can be *consistent with* a victim; deciding that someone *is* a victim requires contact, statements and records outside the data. No screen ever states that an account is a victim or a criminal.

> **Presenter explanation (exact, safe):** "AC2207 is the likely origin of these funds. MuleTrace shows indicators consistent with a possible victim — and it says explicitly that this is not a determination. Its own money-flow signals aren't scored."

> **Warning:** Never say "this is the victim" or "the victim lost ₹4.8 lakh". Say "likely origin" and "possible-victim indicator".

> **Technical reference:** `backend/muletrace/cases.py` → `_assign_roles()`, `_origin_funded()`, indicator block in `_assign_roles()`; `scoring.py` → ORIGIN zeroing in `score()`; `explain.py` → `VICTIM_TEXT`, `indicator_view()`; `pipeline.py` → `Analysis.role()`; tests `test_scenarios.py` → `test_a8_victim_contamination`, `test_g14_…`; `test_relationship.py` R1–R6.

## 6.3 Roles in the demo

| Case | Role | Accounts |
|---|---|---|
| CASE-03 (hero) | Likely origin | AC2207, AC3318 (both INDICATED) |
| | Hub | AC5530 |
| | Relay | AC5521, AC5579, AC5547, AC5562, AC6624 |
| | Sink | AC6610, AC6637, AC6651 |
| CASE-02 | Likely origin | AC3400, AC3401, AC3402, AC3403, AC3404 (all INDICATED) |
| | Hub | AC4400 |
| | Relay | AC4410, AC4411, AC4412 |
| | Sink | AC4420, AC4421, AC4422 |
| CASE-04 (circular ring) | Relay | AC3500, AC3501, AC3502, AC3503 — no origin, no sink |
| — | Cluster member | AC5600–AC5604, AC5700–AC5703 |
| — | Pooled | AC8800 (merchant) and AC9200–AC9209 (shops) |

# Part 7 — Scoring

## 7.1 The scoring table

| Family (cap) | Component | STRONG | MODERATE |
|---|---|---|---|
| **Money flow (60)** | Pass-through (RELAY) | 35 | 20 |
| | Fan-in → fan-out (HUB) | 25 | 15 |
| | Layered receipt (LAYERED_RECEIPT) | 20 | 10 |
| | each additional qualifying base signal | +5 | +5 |
| | REPEATED (≥ 3 pass-through episodes) | +5 | |
| | CHAIN (≥ 3 relays on one traced path) | +10 | |
| | CORROBORATED_LAYERING (≥ 3 STRONG relays, ≤ 60 min) — replaces CHAIN | +25 | |
| | CONSOLIDATION (layered funds from ≥ 2 chains) | +10 | |
| **Circularity (20)** | Circular flow (ROUND_TRIP) | 20 | 12 |
| **Shared identity (20)** | device or KYC link | 15 | |
| | IP-only link ("weak evidence") | 8 | |
| | each additional link type | +5 | |

## 7.2 How a score is built

1. Only **qualifying** signals take part (Part 3, Stage 10). WEAK never scores; an origin's money-flow signals are zeroed unless contra-indicated.
2. **Money flow:** the strongest qualifying base signal (pass-through, hub, layered receipt) earns its full points; every other qualifying base signal adds **+5**. If pass-through qualifies, REPEATED and then either CORROBORATED_LAYERING or CHAIN are added. CONSOLIDATION is added for a consolidating layered receipt.
3. **Circularity:** the round-trip points for its tier.
4. **Shared identity:** 15 for device/KYC (8 if IP only), +5 per further link type.
5. **Caps:** if a family's components exceed its cap, a negative "Family cap" line brings it back to the cap (60 / 20 / 20). The cap is visible on the score card.
6. **Score** = sum of all components (0–100). **Flagged** ⇔ score > 0.
7. **Severity:** HIGH ≥ 60 · MEDIUM 35–59 · LOW 1–34.

Each family is independent, so the score rises when *different kinds* of evidence agree, not when one kind repeats. Correlated identity evidence cannot stack beyond 20 (test A7: four accounts sharing device, IP and KYC score exactly 20, LOW).

> **Warning:** The score is an **evidence-strength index, not a probability of fraud**. Exposure (₹) is shown but never scored.

## 7.3 Hero: AC5530 — 95, HIGH

```
AC5530
 Money flow
  → Pass-through, STRONG ...................... +35   (strongest flow signal)
      Received ₹8,37,000, forwarded ₹8,33,000 (99.5% conserved), average 5 min
  → Fan-in → fan-out hub, STRONG .............. +5    (additional flow signal; its own 25 is not used)
      3 senders → 3 receivers, 25 Mar 10:05–13:34
  → Corroborated rapid layering ............... +25
      AC5521 → AC5530 → AC5547, 16 min
  → Family cap ................................ −5    (65 → 60)
                                         Money flow = 60 / 60
 Circularity
  → Circular money flow, STRONG ............... +20
      ₹1,50,000 of ₹3,00,000 (50%) back in 3 h 18 min: AC5530 → AC5562 → AC6624 → AC5530
                                         Circularity = 20 / 20
 Shared identity
  → Shared device DV-7731AA, STRONG ........... +15
      with AC5521, AC5547, AC5562; new account (opened 7 days before first activity)
                                         Shared identity = 15 / 20
 ─────────────────────────────────────────────────────
 Final score = 60 + 20 + 15 = 95  →  HIGH (≥ 60)
```

Why not 100? AC5530 shares only a device (no KYC or IP link), so shared identity is 15 of 20. REPEATED does not apply (one pass-through episode). CHAIN is not added because corroborated layering replaces it.

> **Verified numbers:** AC5530 — score **95**, **HIGH**, role **Hub**, 3 evidence families, exposure **₹8,33,000**, case **CASE-03**, primary reason "Received ₹8,37,000 and forwarded ₹8,33,000 (99.5% conserved) after an average of 5 min (25 Mar 10:05–13:34)."

## 7.4 Other demo scores, built the same way

| Account | Components | Score |
|---|---|---|
| AC5562 | pass-through 35 + corroborated 25 = 60 · circular STRONG 20 · device 15 | **95** HIGH |
| AC5547 | pass-through 35 + corroborated 25 = 60 · circular MODERATE 12 · device 15 + KYC 5 = 20 | **92** HIGH |
| AC5521 | pass-through 35 + corroborated 25 = 60 · device 15 | **75** HIGH |
| AC5579 | pass-through 35 + corroborated 25 = 60 · KYC 15 | **75** HIGH |
| AC3501 / AC3502 / AC3503 | pass-through MODERATE 20 + chain 10 = 30 · circular STRONG 20 | **50** MEDIUM |
| AC4400 | pass-through 35 + hub 5 = 40 | **40** MEDIUM |
| AC3500 | layered receipt 20 · circular STRONG 20 | **40** MEDIUM |
| AC4410 / AC4411 / AC4412 | pass-through 35 | **35** MEDIUM |
| AC6610, AC6637, AC6651, AC4420–AC4422 | layered receipt 20 | **20** LOW |
| AC6624 | circular STRONG 20 (its pass-through is WEAK — near miss) | **20** LOW |
| AC5600–AC5604 | device 15 | **15** LOW |
| AC5700–AC5703 | IP only 8 | **8** LOW |

> **Presenter explanation:** "Three independent families — how the money moved, whether it came back, and whether the accounts share identity. Each has a cap, so piling up one kind of evidence can't push the score up forever. And every line here links to a rule, the numbers and the transaction IDs."

> **Technical reference:** `backend/muletrace/config.py` (`pts_*`, `cap_*`, `severity_*`); `backend/muletrace/scoring.py` → `_score_account()`, `_capped()`; invariants in `test_scenarios.py` → `test_score_invariants_everywhere`.

# Part 8 — Cases

## 8.1 What a case is

A case is a **connected group of accounts linked by the suspicious movement itself**. It is the unit an investigator works on.

## 8.2 How cases are created

1. **Flow-active accounts:** accounts with a raw pass-through, hub, layered-receipt or circular-flow signal at ≥ MODERATE.
2. **Case transactions:** only the transactions that made those accounts suspicious — the transactions of their ≥ MODERATE episodes (outgoing payments only inside the episode's tier window), plus the transactions of layered receipts and round trips — and only those touching a flow-active account.
3. **Exclusion:** a transaction over an ESTABLISHED relationship whose other end is not flow-active is left out (for example an employer's salary into a relay's account). Historical payments outside the suspicious movement never join a case.
4. **Connected components** of those transactions are the cases. Members that are not flow-active are *boundary* accounts (for example likely origins and sinks).
5. Cases are numbered by size, largest first (CASE-01 is the largest). Numbering depends on the whole dataset and the engine, so do not memorise case IDs across engines.

**Accounts vs cases:** an account can be in zero, one or several cases. A flagged account need not be in a case (shared-attribute clusters without money flow are not cases). A case can contain unflagged accounts (likely origins). Only cases with **at least one flagged member** are listed on `/cases` and counted on the Overview.

## 8.3 What the case shows

| Field | Meaning |
|---|---|
| Severity | the highest severity among its flagged members — a case has no score of its own |
| Accounts / flagged | all members / flagged members |
| Evidence families | union of the families scored by its members |
| Window | first to last case transaction |
| Value from likely origins | sum of case transactions sent by ORIGIN members ("no likely origin identified" when there is none; "—" for a case without a flagged member) |
| Median dwell | median dwell of the FIFO links inside the case at its flow-active members |
| Confirmation progress | "N of M flagged confirmed"; a cleared member is not a confirmation; decisions on unflagged members are counted separately |
| Members | with case role, score, severity, decision status |

Decisions and audit trails belong to **accounts**, not to cases. The case view aggregates them.

## 8.4 `value_moved` is not a loss

The case's total ("Together they total ₹28,60,000" for CASE-03) is the **sum of all case transactions**. The same money is counted again at every hop: ₹4,80,000 from AC2207 is counted when it enters AC5521, again when it moves to AC5530, again when it moves on. It is **transaction volume across traced hops**. It is not money lost, not victim loss, not exposure. The product itself says: "the same money is counted again at every hop, so this is transaction volume, not an amount lost."

The number closest to "what entered the network" is **value from likely origins** (₹6,00,000 for CASE-03) — and even that is the amount the likely origins *sent into the case*, not a confirmed loss.

> **Verified numbers:** CASE-03 — 11 accounts, 9 flagged (5 HIGH, 4 LOW), 2 likely origins, 12 case transactions, 25 Mar 10:01–13:34 (3 h 33 min), median dwell **7 min**, value from likely origins **₹6,00,000**, total case transaction volume **₹28,60,000**.

> **Warning:** Never say "this ring laundered ₹28.6 lakh" or "victims lost ₹28.6 lakh".

> **Technical reference:** `backend/muletrace/cases.py` → `build()`, `flow_txns()`, `_case_metrics()`; `api.py` → `case_list()`, `case_detail()`; tests `test_cases_list.py`, `test_console_fixes.py`.

# Part 9 — Case Money-Flow Summary

## 9.1 What it shows

Four fixed-template lines on the Case page, built only from the case's computed data (roles, case transactions, scored signals, metrics). Nothing is recomputed and nothing new is inferred. CASE-03, verbatim:

- **Entry:** "Funds entered the case from 2 likely origin accounts (AC2207, AC3318): ₹6,00,000 in 2 transactions, 25 Mar 10:01–10:02."
- **Movement:** "Funds moved through 1 hub and 5 relay accounts. Scored patterns, by number of flagged members: pass-through (5), fan-in → fan-out (1), layered receipt (3), circular flow (4), shared attributes (5). Circular flow: money sent out by an account later came back to it through other accounts. Median time funds stayed in an account before moving on: 7 min."
- **Exit:** "3 sink accounts (AC6610, AC6637, AC6651) received ₹5,26,000 in 3 case transactions; a sink forwards less than 20% of what it receives."
- **Period:** "12 case transactions, 25 Mar 10:01–13:34 (3 h 33 min). Together they total ₹28,60,000 — the same money is counted again at every hop, so this is transaction volume, not an amount lost."

## 9.2 How each value is calculated

| Line | Source |
|---|---|
| Entry amount | sum of case transactions whose sender is a likely origin; time span of those transactions |
| Movement roles | count of members per role: hub, collector, distributor, relay |
| Scored patterns | number of *flagged* members whose signal of that kind qualified |
| Median time | the case's median dwell metric |
| Exit | sink members and the case transactions they received |
| Period | all case transactions (not the 200-row timeline), window, total value |

## 9.3 What it deliberately does not claim

- No account is called a victim — "likely origin" only.
- No causality: it states sequence ("entered", "moved through", "received"), not intent or cause.
- The total is described as transaction volume, never as a loss.

## 9.4 Edge cases

- **No likely origin (CASE-04, the circular ring):** "No likely origin account identified, so where these funds entered is not visible in this case. The first case transaction was sent by AC3500 on 22 Mar 11:00." The case header then omits "entered from likely origins" instead of showing ₹0, and the Cases list shows "no likely origin identified".
- **No sink:** "No sink account identified: within the data, case funds were not seen coming to rest in one account."
- **Pooled members:** "N pooled account(s) (…): traced money stops there."
- **Case without a flagged member:** only the Period line plus "No member is flagged, so roles are not assigned and entry and exit are not described." (Such cases are not on the Cases list but can be opened from an account's case card.)
- **Large cases:** counts and totals always use every case transaction, even when the case timeline is capped at 200 rows.
- **Fallback engine:** "Holding times are not traced by the fallback engine." replaces the median-time sentence.

> **Presenter explanation:** "The summary is four sentences generated from the case data — entry, movement, exit, period. It's careful by design: it says 'likely origin', it doesn't claim cause, and it tells you the twenty-eight lakh is volume counted at each hop, not a loss."

> **Technical reference:** `backend/muletrace/summary.py` → `case_summary()`; `GET /api/cases/{id}/summary`; tests `backend/tests/test_case_summary.py` (includes a banned-wording check).

# Part 10 — Graph Investigation

## 10.1 What is drawn

| Element | Meaning |
|---|---|
| Node | an account |
| Node colour + words | severity (High / Medium / Low / not flagged); the label repeats score and severity in words |
| Node shape | role: ◆ likely origin · ● relay, hub, collector, distributor · ■ sink · ⬢ pooled |
| Thick accent ring | the account under investigation |
| Double ring / green ring | analyst decision confirmed / cleared |
| Halo | the selected account |
| Solid line, filled arrow | suspicious transactions (part of a flagged case or of scored evidence) |
| Dotted line, hollow arrow | other transactions |
| Dashed line, no arrow | shared device / IP / KYC — not a payment |
| Blue line, back-curved arrow | **computed flow link** (FIFO attribution) — trace views only |
| Arc | money flowing back (circular flow) |
| Edge label | total amount (and ×count when several transactions are aggregated); in trace views, the traced amount. Shown on small graphs (≤ 14 links) and on highlighted or selected links; hover shows it always |
| Faded | not part of the highlighted evidence |

In the **Network** view, an edge aggregates all transactions from one sender to one receiver; hovering shows the total, the count, the time range and the first transaction IDs. In **trace** views an edge is the traced amount attributed by FIFO, not a transaction total. Direction is always the direction money moved.

## 10.2 Account graph

- Built from the account outward, 1–3 hops (default 2), optionally only suspicious transactions (default on).
- **Bound:** at most **80** accounts. Over the cap, each hop level gets a share, every drawn account stays attached to one hop closer, and the note says "Showing N of M accounts — the closest and most suspicious at each hop are drawn".
- **Expansion:** double-click adds that account's 1-hop neighbourhood to the drawing.
- Layout: left-to-right in the direction money moves; shared-attribute links never move nodes.

## 10.3 Case graph

- Every member of the case and every case transaction between them; roles of the case.
- Over 80 members: a connected subset built from the case's most valuable money paths (likely origin → relays → collector → cash-out), then the highest-scoring flagged neighbours. The demo cases are all under the cap (CASE-03: 11 nodes, 12 edges).

## 10.4 How to use it

1. Open AC5530 → Network. The ring appears: two diamonds on the left (AC2207, AC3318), relays, the hub in the middle, square sinks on the right.
2. Click the **Pass-through** evidence card: only the pass-through transactions and the traced relay path stay bright.
3. Click **Circular flow**: the arc from AC6624 back to AC5530 lights up.
4. Click **Shared attributes**: the accounts sharing the device (AC5521, AC5547, AC5562) stay bright with AC5530; with the "Shared attributes" toggle on, dashed links mark the shared value.
5. Double-click AC5547 to pull in its neighbourhood, or open the case graph from the case card.

## 10.5 What the graph does not prove

- An edge proves that a transaction happened, not why.
- Proximity is not guilt: unflagged neighbours drawn next to a flagged account are not accused of anything.
- A dashed attribute link is not a payment and not proof of common ownership.
- A capped graph is a view, not the whole network; the member table and the note say what is not drawn.

> **Presenter explanation:** "Shapes tell you the role, colour and words tell you severity, and the line style tells you what kind of link it is — a suspicious payment, an ordinary one, a shared device, or money we traced with FIFO. Nothing depends on colour alone."

> **Technical reference:** `frontend/src/components/GraphView.tsx` (styles, `GraphLegend`, `nodeLabel`), `frontend/src/lib/layout.ts`, `frontend/src/lib/graphState.ts`; `backend/muletrace/network.py` → `network()`, `_select_by_level()`, `case_network()`, `_case_story()`, `suspicious_txns()`.

# Part 11 — Trace / Follow-the-Money

## 11.1 How it works

- **Where money went** (`dir=fwd`) / **Where money came from** (`dir=back`) on the account page.
- **Starting point:** up to 25 of the account's outgoing (fwd) or incoming (back) transactions that belong to its scored evidence or its case, largest first; if there are none, its 10 largest transactions in that direction. The start transaction IDs are returned with the trace.
- **Propagation:** FIFO links, hop by hop, with exact fractions (Part 4.6). Forward: what the start transactions' money funded next. Backward: which incoming money funded the start transactions.
- **Hop limit:** 8. Money still moving at hop 8 is reported as "beyond hop limit".
- **Pooled accounts:** the trace stops there and the node gets a dashed ring.
- **Drawing bound:** 50 nodes. The accounts with the smallest traced amounts are grouped into one "+N accounts" node.
- **Accounting line under the graph:** "₹X traced · kept along the way ₹Y · exact" (forward) or "originated from account balances" (backward), plus "stopped at pooled" when relevant.
- **Expansion:** double-click on a node opens *that* account's own trace; traces are never merged.
- **Fallback engine:** no FIFO tracing — see Part 14.

## 11.2 Computed vs raw

Everything in a trace view is **computed**: the blue lines are flow links attributed by FIFO; the amounts are traced shares. The raw transactions are in the Network view, the timeline and the transactions table. The trace label says so: "computed flow links (FIFO attribution)".

> **Verified numbers:** AC5530 forward trace — start ₹8,33,000 (TX102083, TX102084, TX102090), all of it accounted for, "exact". Backward trace — start ₹8,37,000 (TX102081, TX102082, TX102089), "exact"; the likely origins AC2207 and AC3318 appear as diamonds.

## 11.3 Two things that surprise people — read before the demo

**1. Traced amounts can exceed a single transaction when money circulates.** In the hero ring, part of the money AC5530 sent at 10:11–10:12 came back at 13:30 and left again at 13:34 (TX102090, ₹2,38,000). The forward trace starts from TX102090 *and* follows the returned money into TX102090 again, so the edge AC5530 → AC6651 shows **₹4,74,000** traced over a ₹2,38,000 transaction. Likewise the backward trace shows ₹6,59,500 attributed to AC2207's ₹4,80,000 payment. Nothing is created: the start total is still accounted for exactly; the same rupees are counted once per pass through the loop.

> **Judge may ask:** "How can ₹4.74 lakh go through a ₹2.38 lakh payment?" — "Because this ring is circular. The trace starts from three payments, and money from the first two came back and left again in the third, so that payment carries both its own start amount and returned money. The total of the trace still balances to the rupee — the exact check is on the start amount."

**2. A backward trace can reach an employer.** AC3318's ₹1,20,000 transfer was funded by the salary it received 21 minutes earlier, so the backward trace from AC5530 reaches **AC9002** (AC3318's employer, not flagged, no role) and shows money "originated from account balances" there. FIFO is answering "which incoming money funded this payment", not "who is responsible".

> **Warning:** A trace shows where money is *attributed* to have gone or come from. It does not show who is responsible, who lost money, or where funds went after leaving the data (cash, other banks).

## 11.4 What the investigator can and cannot conclude

| Can conclude | Cannot conclude |
|---|---|
| Under FIFO attribution, ₹X of these payments reached account Y within N hops | That those specific rupees physically went there |
| How long money stayed at each hop (median dwell per node) | The intent or knowledge of any account holder |
| Where the visible trail stops (sinks, pooled accounts, hop limit) | Where money went outside the dataset |
| The trace balances exactly | That the amount was stolen or lost |

> **Presenter explanation:** "Where money went: the blue lines are computed flow links — FIFO attribution, not raw transfers — with the traced rupees on each line. Underneath, the accounting: eight lakh thirty-three thousand traced, all of it accounted for, exact."

> **Technical reference:** `backend/muletrace/network.py` → `trace_view()`, `_start_txns()`, `TRACE_LABEL`; `flow.py` → `trace()`, `TraceResult.accounted()`; `GET /api/accounts/{id}/trace?dir=fwd|back`; tests `test_flow_engine.py` (exact trace), `test_api.py` (G10 trace cap), `test_console_fixes.py` (trace merge guard).

# Part 12 — Analyst Decision

## 12.1 Controls

On the account page, **Analyst decision** card:

- **Note** (up to 1,000 characters), recommended for the audit trail.
- **Reason shortcuts** fill the note: *Confirm:* "Rapid layering confirmed", "Linked to confirmed case", "Customer unable to explain flows". *Clear:* "Known business activity", "Customer verified", "Possible victim — referred to support". Each set is offered only for the action that is still available.
- **Confirm** · **Clear** · **Reopen** (Reopen appears once a decision exists; Confirm is disabled when already confirmed, Clear when already cleared).
- "Recorded as <analyst name>" — the name from the header field.
- **Audit trail** — newest first: time (IST), analyst, from → to, note; reset entries read "demo reset: confirmed → open".

## 12.2 What happens when I click Confirm

UI → `POST /api/accounts/{id}/disposition` with `{status: "CONFIRMED", note, analyst}` → the server writes the decision for (dataset fingerprint, account) into SQLite and appends an audit entry (from-status, to-status, note, analyst, time) → returns the decision and the account's audit trail → the card shows the new status and trail, the note box clears, the graph node gets a double ring (green ring for Cleared) without redrawing, and the Overview, queue, case card and Cases list reflect the new status when they next load.

**Errors:** unknown status → HTTP 400; unknown account → 404; no dataset → 409. On any failure the card shows "**The decision was not saved.** … Your note is kept — try again." and keeps the note.

## 12.3 What changes and what does not

| Changes | Does not change |
|---|---|
| Account status badge and audit trail | Score, severity, signals, evidence |
| Queue status column, Status filter, CSV export columns | Queue membership and order |
| Overview decision counts (and "decisions on not-flagged accounts") | Detection of any other account |
| Case confirmation progress; Cases list ordering (fully confirmed cases move below others of the same severity) | Case membership, roles, metrics |
| Graph node ring | Traces and flow links |

Decisions are **analyst dispositions**. They do not feed back into scoring. A decision may be recorded on any account, including one that is not flagged (it then appears on the Overview, not in the queue).

## 12.4 Persistence

- Stored in `backend/muletrace.db` (SQLite), keyed by the SHA-256 fingerprint of the dataset file, so decisions survive a server restart and reloading the same file.
- The audit log is append-only. **Reset demo** returns every decision on the demo dataset to Open and writes one RESET entry per affected account plus a dataset-wide entry; it never deletes history.
- The analyst name is free text kept in the browser; there is no login and no authentication.

> **Warning:** "Confirmed" means an analyst recorded that disposition in this tool. It is not a legal finding, a SAR filing or proof that a crime occurred.

> **Note for the presenter's machine:** the database on this computer already contains earlier test decisions for AC5530 (five audit lines, all on 02 Oct 2026, some written before the current per-account reset entry existed, so the trail ends in "confirmed → cleared" while the status reads Open). Reset demo will not remove them because the log is append-only. If you want an empty audit trail on stage, start the server with a fresh database file (stop the server and move `backend/muletrace.db` aside; the demo loads automatically on start). Decide this yourself — it discards local history.

> **Presenter explanation:** "The analyst writes a note, confirms, and it's on the audit trail with their name and time. The decision doesn't change the score — the evidence stays the evidence — and nothing is ever deleted: even a reset is written into the log."

> **Technical reference:** `frontend/src/components/Investigation.tsx` → `DispositionPanel`; `frontend/src/lib/decision.ts` → `reasonsFor()`, `submitDecision()`; `api.py` → `disposition()`; `store.py` → `set_disposition()`, `audit()`, `clear_dispositions()`.

# Part 13 — Methodology / Configuration Panel

## 13.1 What it displays

Opened by **Method** (account score card footer; Case page summary header). Title "How MuleTrace scores": "Fixed rules: the same data and configuration always give the same result. Scores are evidence-strength indices, not probabilities of fraud." Every figure is read from `GET /api/config`; nothing is typed into the page.

| Section | Rows (default configuration) |
|---|---|
| Severity | High score ≥ 60 · Medium score 35–59 · Low flagged, score below 35 |
| Score — max 100 | Money flow (cap 60): pass-through 35 / 20 · fan-in → fan-out 25 / 15 · layered receipt 20 / 10 · Bonuses: +5 each further pattern, +5 repeated (≥ 3 episodes), +10 relay chain (≥ 3 relays), +25 corroborated layering (≥ 3 strong relays within 1 h), +10 consolidation · Circularity (cap 20): 20 / 12 · Shared identity (cap 20): device or KYC 15, IP only 8, +5 each further attribute type |
| Pass-through strength | Strong: held ≤ 30 min, ≥ 90 % passed on · Moderate: ≤ 6 h, ≥ 80 % · Weak: ≤ 3 d, ≥ 70 % — recorded, not scored |
| Patterns | Fan-in → fan-out ≥ 3 senders and ≥ 3 receivers within 6 h · Layered receipt through ≥ 2 relays, strong ≤ 6 h, moderate ≤ 3 d · Circular flow ≤ 6 hops, strong ≤ 1 d and ≥ 50 % returned, moderate ≤ 3 d and ≥ 30 % · Shared attributes: new or age-unknown accounts sharing a device (≥ 3), IP (≥ 4) or KYC (≥ 2) |
| Money tracing | first in, first out; funds held longer than 3 d are not linked · structure ignores links below ₹1,000 and episodes below ₹10,000 · traces up to 8 hops |
| False-positive defences | Pooled ≥ 50 counterparties over ≥ 7 d · Established relationship: payments older than 7 days worth ≥ 50 % of the pair's last 7 days · History downgrade: ≥ 80 % of funding or payees established → one tier lower · Shared infrastructure: ≥ 5 established sharers and ≥ 60 % of them → not evidence · New account ≤ 30 days old · Likely origin ≥ 50 % own funds or ≥ 80 % established · Sink forwards < 20 % |
| Footer | "Engine flow · configuration b652e4bf70db · read-only" |

(The panel prints 72 hours as "3 d" and 24 hours as "1 d".)

## 13.2 Engine, hash and reproducibility

- **Engine:** `flow` (default, FIFO) or `window` (fallback).
- **Configuration hash:** the first 12 hex characters of a SHA-256 over the complete configuration (every threshold, weight, cap and the engine). The same hash appears in the page footer and in the queue export file name. Demo values: `b652e4bf70db` (flow), `428bd575eef2` (window).
- **Why it matters:** with the dataset fingerprint and the configuration hash, anyone can reproduce a result exactly — the analysis has no randomness and reads no clock.

## 13.3 Why it is read-only

Thresholds are part of the method, not user preferences. Changing them from the console would make two analysts' results incomparable and silently change every score. `/api/config` accepts **GET only** (POST, PUT, PATCH, DELETE return 405, covered by `test_method_config.py`). Values can be changed only in `backend/muletrace/config.py`, which changes the hash.

> **Judge may ask:** "How do I know these thresholds are what actually ran?" — "Open Method: every figure comes from the running configuration, and its hash is in the footer and in every exported file name."

> **Technical reference:** `backend/muletrace/config.py` → `Config`, `Config.hash()`; `api.py` → `config()`; `frontend/src/lib/method.ts` → `methodSections()`.

# Part 14 — Fallback Mode

## 14.1 When it occurs

Fallback mode runs **only when the server is started with** `python run.py --engine window`. It is **not** an automatic switch: MuleTrace does not fall back on its own when something fails. The footer then shows "engine window" and a different configuration hash.

## 14.2 What it computes

- **No FIFO links** (the Overview shows 0 computed flow links). Every incoming payment of ≥ ₹10,000 is judged by the **window test** only: outgoing payments within 30 min / 6 h / 72 h compared with the incoming amount.
- **Pass-through** and **hub** from window episodes; **no layered receipt**, **no chain**, **no corroborated layering** (they need links).
- **Circular flow** by a greedy walk forward in time over transactions, with the returned amount taken as the smallest transfer along the cycle.
- **Shared attributes**, pooled detection, cases, roles, the possible-victim indicator, mitigations, qualification, scoring, explanations, decisions and the API contract are the same.
- **Traces:** "Where money came from / went" become transaction views labelled "suspicious transactions into / out of this account, up to 2 hops back / on (not traced) — flow tracing unavailable in fallback mode". No traced amounts, no accounting line.
- **Median dwell** is not available; the case summary says "Holding times are not traced by the fallback engine."

## 14.3 Demo results under fallback (verified)

| | Flow engine (default) | Fallback (`--engine window`) |
|---|---|---|
| Flagged / HIGH | 29 / 5 | 19 / 3 |
| Suspicious cases | 3 | 2 |
| Computed flow links | 429 | 0 |
| AC5530 | HIGH 95, Hub | HIGH 70 (pass-through 35 + circular 20 + device 15), Relay |
| Hero case ID | CASE-03 | CASE-02 (same 11 accounts, ₹6,00,000 from likely origins) |
| Ring 2 (AC4400) | MEDIUM, CASE-02 | not flagged |
| Configuration hash | `b652e4bf70db` | `428bd575eef2` |

## 14.4 What claims remain valid

Valid in fallback: deterministic results, transparent rules, the same false-positive defences, the same wording rules, decisions and audit. **Not** valid: anything about traced amounts, FIFO attribution, conservation of a trace, dwell times or corroborated layering.

> **Presenter explanation:** "There's a simpler window engine behind the same interface. It doesn't attribute money, so it finds less — the hero still comes out HIGH, the fan-in ring doesn't — and the screens say plainly that flow tracing is unavailable. It's a fallback, not the method we present."

> **Warning:** Do not say fallback "kicks in automatically" — it is chosen at server start.

> **Technical reference:** `backend/muletrace/fallback.py` → `build_window_engine()`, `_greedy_cycles()`; `network.py` → `directional_view()`; `run.py --engine window`; test `test_api.py` → `test_g12_fallback_engine_same_contract`.

# Part 15 — False-Positive Defences

| Situation | What the system sees | What applies | Why it prevents naive flagging | What remains uncertain |
|---|---|---|---|---|
| **Payroll** (AC7100) | ₹18,00,000 in, 24 × ₹74,500 out within 15 min, twice | 1 Mar: single isolated episode → not scored. 31 Mar: funding and payees are established relationships → STRONG lowered two tiers to WEAK | Routine fan-out is pass-through in shape only | A payroll account that is itself abused within an established pattern |
| **Merchant / aggregator** (AC8800; shops AC9200–AC9209) | 151 counterparties over 30 days, daily settlement | Pooled: no flow links, traces stop, not traversed by circular search | Mixed funds are not falsely attributed | A pooled account can still be flagged on its own evidence (window pass-through, hub, layered receipt, identity) |
| **Shared office IP** (10.20.0.15) | 23 accounts on one IP, all established | Infrastructure (≥ 5 established and ≥ 60 %) → not evidence | Offices, campuses and shared networks | Without opening dates or ≥ 14 days of data, infrastructure cannot be judged; IP stays weak evidence |
| **Salary then spending** (AC3318; test G5) | Salary forwarded within minutes | ORIGIN via ≥ 80 % established funding; isolated single pass-through not scored | "Day-one" and ordinary salary → rent patterns | — |
| **Refunds / repayments** | A → B → A | Two-party exchange is an observation only; round trips need ≥ 2 intermediaries; refunds through a pooled aggregator are not cycles (test G6) | Ordinary reciprocal payments | Genuine three-party circular business flows can still match |
| **Established relationships** | ≥ 80 % of an episode's money over established pairs | −1 tier per mitigation | Settlement and treasury patterns | Blocked for corroborated rapid paths and all-new counterparties, by design |
| **Decoy activity** (AC5530's ₹199–₹399 shop payments on 24 Mar; test A5) | Small everyday payments around a mule | Links below ₹1,000 excluded from structure; window test against reservoir tricks | Camouflage does not dilute the signal | — |
| **Victim contamination** (AC2207 received ₹1 and ₹499 from a mule) | Origin receives money back from the ring | Contra-indication only above ₹1,000 | Verification pings and token refunds do not turn a victim into a suspect | A larger payment back would contra-indicate the indicator |
| **Isolated near threshold** (AC6101) | 89 % forwarded after 41 min, once | MODERATE pass-through but isolated → observation | Single coincidences | A lone mule with no linked relay and no other evidence is not flagged |
| **Weak patterns** (AC1105) | 75 % forwarded over 2 days | WEAK never scores → "Near miss" | Slow ordinary movement | Very slow layering (> 6 h per hop) is observation-level |
| **Threshold evasion** (test A1) | Each relay keeps 11 % | Drops one tier, still MODERATE, chain bonus applies | Small tweaks don't make layering invisible | — |
| **Correlated identity** (test A7) | Same device, IP and KYC | Family cap 20 | One shared phone cannot stack to HIGH | — |

None of these can erase corroborated rapid layering: no mitigation applies on a corroborated path, pooled status and infrastructure never remove flow evidence, and accounts that move money in the same case are linked by a shared attribute even if it is infrastructure.

> **Presenter explanation:** "Most of the engineering went into not flagging people. Payroll, a busy merchant, an office network, a victim who received a one-rupee ping — each is a test case and each is on the Not flagged page with its reason."

> **Warning:** MuleTrace reduces false positives; it does not eliminate them. Say "designed to avoid", never "no false positives".

# Part 16 — Demo Data Story

The bundled dataset is synthetic and deterministic (generated from seed 20240301 by `scripts/make_demo.py`; 1–31 March 2024). Account IDs are fictitious.

## 16.1 Hero

> **Verified numbers:** **AC5530** · score **95** · **HIGH** · role **Hub** · evidence: pass-through STRONG, fan-in → fan-out STRONG, corroborated rapid layering, circular flow STRONG, shared device · case **CASE-03** · new account, opened 7 days before first activity.

## 16.2 The hero network (25 March, IST)

| Time | From → To | Amount | What it is |
|---|---|---|---|
| 09:40 | AC9002 → AC3318 | ₹1,25,000 | salary (established employer) |
| 09:55 | AC5521 → AC2207 | ₹1 | verification ping |
| 10:01 | AC3318 → AC5579 | ₹1,20,000 | likely origin 2 into the ring |
| 10:02 | AC2207 → AC5521 | ₹4,80,000 | likely origin 1 into the ring |
| 10:05 | AC5521 → AC5530 | ₹4,78,000 | relay → hub (held 3 min) |
| 10:08 | AC5579 → AC5530 | ₹1,19,000 | relay → hub (held 7 min) |
| 10:11 | AC5530 → AC5547 | ₹2,95,000 | hub fans out |
| 10:12 | AC5530 → AC5562 | ₹3,00,000 | hub fans out |
| 10:15 | AC5547 → AC6610 | ₹1,40,000 | to sink |
| 10:16 | AC5562 → AC6624 | ₹1,50,000 | to AC6624 |
| 10:18 | AC5547 → AC6624 | ₹1,52,000 | to AC6624 |
| 10:19 | AC5562 → AC6637 | ₹1,48,000 | to sink |
| 11:30 | AC5521 → AC2207 | ₹499 | token "refund" |
| 13:30 | AC6624 → AC5530 | ₹2,40,000 | money circles back to the hub |
| 13:34 | AC5530 → AC6651 | ₹2,38,000 | out again to a sink |

Twelve of these (10:01 to 13:34, excluding the ping, the refund and the salary) are the case transactions of CASE-03. Shared identity: device DV-7731AA on AC5521, AC5530, AC5547, AC5562; KYC-19C0FFEE on AC5547 and AC5579. On 24 March AC5530 also made three small shop payments (₹199, ₹299, ₹399) — decoy everyday spending.

**Intended investigation path:** queue → AC5530 → why flagged (score card) → where money came from (diamonds AC2207, AC3318) → where money went (sinks AC6610, AC6637, AC6651; ₹8,33,000 traced, exact) → case CASE-03 → decision.

## 16.3 The other patterns

| Story | Accounts | Outcome |
|---|---|---|
| **Pass-through** | AC5521: ₹4,80,000 in, ₹4,78,000 out after 3 min | HIGH 75 |
| **Circular / round trip** | AC3500 → AC3501 → AC3502 → AC3503 → AC3500 on 22 Mar, value shrinking 14 % per hop; ₹1,65,375 of ₹2,60,000 back in 4 h 15 min | CASE-04, all four MEDIUM; no likely origin identified |
| **Fan-in ring** | five accounts AC3400–AC3404 → hub AC4400 → relays AC4410–AC4412 → AC4420–AC4422, 28 Mar 14:03–14:40 | CASE-02, MEDIUM; five likely origins, ₹4,39,000 |
| **Identity — device** | AC5600–AC5604: five new accounts, one device DV-4410EE, almost no activity | LOW 15 each, no case |
| **Identity — IP only** | AC5700–AC5703 share 103.77.12.9 | LOW 8 each, "weak evidence" |
| **Identity — infrastructure** | 10.20.0.15 shared by 23 established accounts (including AC2207) | ignored as evidence |

## 16.4 Contrasting (legitimate) activity

| Account | Story | Outcome |
|---|---|---|
| AC2207 | 4-year-old account; sent ₹4,80,000 at 10:02; received ₹1 and ₹499 from a mule | Likely origin, possible-victim indicator present, not flagged |
| AC3318 | salary at 09:40, transfer to a mule at 10:01 | Likely origin, possible-victim indicator present, not flagged |
| AC8800 | merchant: 279 incoming payments, 31 daily settlements to AC8801, 151 counterparties | Pooled, not flagged |
| AC7100 | payroll: ₹18,00,000 from AC7000, 24 salaries of ₹74,500 on 1 and 31 March | Isolated pass-through + downgraded by history, not flagged (CASE-01, not listed) |
| AC1000–AC1021 | office network 10.20.0.15 (with AC2207, 23 accounts) | Shared infrastructure |

## 16.5 Near misses

- **AC6101** — ₹2,00,000 from AC6100 at 19 Mar 11:00, ₹1,78,000 to AC6102 at 11:41 (89 %, 41 min). MODERATE pass-through, isolated → "Isolated pass-through", not flagged (CASE-05, not listed).
- **AC1105** — 75 % forwarded over 2 d 10 h → WEAK → "Near miss".
- **AC6624** (inside the hero case) — its own pass-through is only WEAK (79.5 % in 3 h 13 min); it is flagged LOW 20 for the circular flow only.

## 16.6 Data-quality rows

Seven malformed rows at the end of the file: six rejected (timestamp, negative amount, self-transfer, conflicting duplicate, empty account, text amount) and one exact duplicate dropped. They are visible on the Data page.

# Part 17 — Five-Minute Demo Candidate Paths

These are options, not a recommendation. Times are approximate.

## Path A — Case-first

Overview → Cases → CASE-03 → AC5530 → evidence → graph → trace → decision → Method

- **Story:** "Here are three cases out of 2,118 transactions; here's why the top one is a mule ring."
- **Shows:** case aggregation, money-flow summary, score card, trace with exact accounting, decision, reproducibility.
- **Skips:** Data page, Not flagged page.
- **Time:** about 4½–5 min.
- **Risks:** the Cases list is not in the header (go through the Overview tile); the Case page has no link back to the list; little time left for the false-positive story.
- **Invites:** "What is value moved?", "How are cases formed?", "How do you avoid flagging the victim?"

## Path B — Transaction-first

Data → Overview → Queue → AC5530 → graph → case → decision

- **Story:** "Messy CSV in, ranked and explained investigations out."
- **Shows:** ingestion report, rejected rows, coverage, Overview counts, queue ordering, account evidence, decision.
- **Skips:** Method panel, trace detail, Not flagged.
- **Time:** about 5 min.
- **Risks:** the Data page takes time without showing detection; the trace may be squeezed.
- **Invites:** "What columns do you need?", "How does it scale?", "What if data is missing?"

## Path C — Investigation-first

Queue → AC5530 → why flagged → graph → where money came from / went → case → decision → Not flagged (AC2207, AC7100, AC8800)

- **Story:** "Follow one account from alert to decision — and show what the system refused to flag." (Closest to the existing `DEMO.md` script.)
- **Shows:** score breakdown, FIFO trace, possible-victim indicator, false-positive defences.
- **Skips:** Data page details, Method, Cases list.
- **Time:** about 5 min.
- **Risks:** the backward trace shows AC9002 and amounts above a single transaction (Part 11.3) — be ready; switching between many accounts costs time.
- **Invites:** "How do you know the money came from that account?", "Is the origin the victim?", "Why isn't the payroll account flagged?"

## Path D — Defence-first (short variant)

Overview ("Reviewed and not flagged") → Not flagged page → AC7100 → back to Queue → AC5530 → trace → decision

- **Story:** "The hard part is knowing when not to flag."
- **Shows:** the not-flagged reasoning first, then one strong positive.
- **Skips:** cases, Method.
- **Time:** about 4 min.
- **Risks:** opens on a negative; judges may want to see detection first.
- **Invites:** "How do you handle legitimate hubs?", "Do you have false positives?"

> **Before any path:** start the server, open http://127.0.0.1:8000, Data → Reset demo, set the analyst name, check the theme. If the graph is busy: tick "Suspicious flows only", set Hops to 1, use Fit all or Full screen.

# Part 18 — Judge Question Bank

Each question has a **10-second** answer, a **30-second** answer and a **deeper** technical answer. Every claim is checked against the current code.

## 18.1 Product

### Q: What does MuleTrace do?

- **10 s:** It reads a bank transaction file, follows the money through accounts and flags the patterns money mules leave — with a reason for every point of score.
- **30 s:** It links every outgoing payment to the incoming money that funded it, finds pass-through accounts, fan-in/fan-out hubs, layered cash-out and circular flows, adds shared-device and KYC evidence, groups connected accounts into cases and lets an analyst confirm or clear with an audit trail. It also lists what it deliberately did not flag.
- **Deep:** A fixed 12-stage pipeline (ingest → profiles → pooled → FIFO links → episodes → signals → cases/roles → mitigations → qualification → scoring → explanations), deterministic over (transactions, configuration). FastAPI serves the API and a React console from one local process.

### Q: Who is it for?

- **10 s:** Fraud and AML investigators who need to work a mule network quickly.
- **30 s:** The analyst gets a ranked queue, cases instead of raw transactions, a graph and a money trace, and a decision trail — all explainable to a colleague or a reviewer.
- **Deep:** Every scored component carries rule, metrics, transaction IDs and a sentence; the queue exports to CSV with decisions; the Method panel and configuration hash document the exact method.

### Q: What makes it different from rule alerts on single transactions?

- **10 s:** It reasons about *the same money* moving across accounts, not about single transfers.
- **30 s:** Each transfer in a mule chain looks normal on its own. FIFO links connect them, so "₹4.78 lakh of that payment left three minutes later" becomes a measurable fact; patterns are built on those links and corroborated across independent evidence families.
- **Deep:** Pass-through tiers combine dwell and two-way conservation; corroborated layering requires ≥ 3 STRONG relays on one traced path within 60 minutes; mitigations and qualification suppress single coincidences and routine business flows.

## 18.2 Detection

### Q: How do you detect suspicious flow?

- **10 s:** By measuring how much of the money an account receives leaves again, and how fast.
- **30 s:** Incoming payments become FIFO lots; outgoing payments consume them. Linked inflows and outflows form episodes graded STRONG (≤ 30 min, ≥ 90 % passed on), MODERATE (≤ 6 h, ≥ 80 %) or WEAK. Hubs, layered receipts and chains are built on top.
- **Deep:** Traced conservation = forwarded ÷ max(inflow, outflow); dwell is amount-weighted; a window test (outflows within the tier bound vs the lot amount) counters reservoir gaming; episodes need ≥ ₹10,000 inflow; links under ₹1,000 are not structural.

### Q: How do you detect circular flows?

- **10 s:** We trace money forward and check whether a real share of it comes back.
- **30 s:** From each payment of ₹10,000 or more, the trace follows FIFO links; if at least 50 % returns within 24 hours through two or more other accounts it's STRONG, 30 % within 72 hours is MODERATE. A two-party back-and-forth is only recorded, because refunds look like that.
- **Deep:** Exact fractions, ≤ 6 accounts per cycle, 10 largest links per step, pooled accounts not traversed, cycles de-duplicated by rotation.

### Q: How do you use device, IP and KYC data?

- **10 s:** As a separate, capped family of evidence — shared device or KYC 15 points, IP only 8.
- **30 s:** Only new or age-unknown accounts count; you need 3 on a device, 4 on an IP or 2 on a KYC value; values used mostly by established accounts are treated as infrastructure. Identity alone reaches at most 20 — LOW.
- **Deep:** Union of qualifying groups into clusters; infrastructure = ≥ 5 established and ≥ 60 % of sharers, judged only when establishment evidence exists; flow-active members of the same case are linked even through infrastructure values (precedence rule).

### Q: Why was this account flagged? (any account)

- **10 s:** The score card lists every point with its rule and transactions.
- **30 s:** Each line is a rule, its tier, the computed numbers and a sentence; select the evidence card to see the exact transactions on the graph and timeline.
- **Deep:** `components` in `GET /api/accounts/{id}`: family, rule, points, tier, detail, reference; signals carry metrics, transaction timeline and path.

## 18.3 Technical

### Q: Why NetworkX?

- **10 s:** We don't use NetworkX.
- **30 s:** The graph work is a few specific algorithms — FIFO queues, union-find for cases and clusters, bounded searches for chains and cycles — written in plain Python with exact integer and fraction arithmetic. That keeps every step deterministic and auditable without a graph library.
- **Deep:** Dependencies are FastAPI, Uvicorn, python-multipart and Pydantic at runtime (pytest and httpx for tests). Graph structures are dictionaries of transaction indices; cases and identity clusters use union-find; round trips and relay paths use bounded depth-first search with a branch cap of 10.

### Q: Why SQLite?

- **10 s:** It's a single local file — no server, works offline.
- **30 s:** We only persist what can't be recomputed: the raw CSV, analyst decisions and the audit log. The analysis itself is derived and recomputed deterministically on load.
- **Deep:** Tables `datasets` (raw CSV blob, SHA-256, active flag), `dispositions` (per dataset fingerprint and account), `audit_log` (append-only). Writes are serialised with a lock.

### Q: Why FastAPI?

- **10 s:** A small, typed Python web layer that serves the API and the console from one process.
- **30 s:** The engine is Python; FastAPI exposes it as JSON endpoints with request validation, and the same process serves the built React app, so `python run.py` is the whole product.
- **Deep:** Uvicorn on 127.0.0.1:8000; Pydantic bodies for decisions and reset; account routes accept URL-encoded free-text IDs.

### Q: Why Cytoscape?

- **10 s:** A mature graph-drawing library that runs fully in the browser.
- **30 s:** It handles node shapes, line styles, arrows, zoom and a left-to-right layered layout (dagre), which lets us show role, severity, decision and link type without relying on colour alone.
- **Deep:** Cytoscape.js with cytoscape-dagre; layout on money links only; large columns wrapped into a grid; labels never rendered below 8 px.

### Q: How does FIFO attribution work?

- **10 s:** Each payment out is paid from the oldest money still in the account.
- **30 s:** Incoming payments queue as lots; an outgoing payment consumes them oldest first; each piece is a link with an amount and a dwell time. Lots older than 72 hours expire; whatever isn't covered is the account's own funds.
- **Deep:** Per account, events sorted by (time, inflow before outflow, input order); invariants tested: links out of a lot ≤ lot; links into a payment + own funds = payment; dwell ≥ 0; order-independent. Multi-hop traces use `fractions.Fraction`.

### Q: Are the rules and thresholds fixed?

- **10 s:** Yes. Every decision is a fixed, documented rule.
- **30 s:** Thresholds and points live in one configuration file, shown in the Method panel and fingerprinted by a hash. A label column in the data is never read by detection.
- **Deep:** `config.py` holds every threshold; `scripts/evaluate.py` can compare results with a ground-truth label column, but detection never reads it.

## 18.4 Accuracy

### Q: How do you avoid false positives?

- **10 s:** Qualification, mitigations, pooled and infrastructure rules — and we show what we set aside.
- **30 s:** A single pass-through never scores; established relationships lower a tier; busy accounts stop attribution; shared office networks aren't evidence; origins aren't scored. In the demo, 43 accounts were considered and set aside, each with a reason.
- **Deep:** See Part 15; adversarial tests cover payroll and merchant camouflage, shared infrastructure, victim contamination, decoys, threshold evasion, slow and split layering, fragmentation, attribute laundering and missing data.

### Q: How do you handle shared IPs?

- **10 s:** An IP alone is weak evidence (8 points), and an IP used mostly by established accounts is ignored.
- **30 s:** Four new accounts on one IP give 8 points each — LOW. The demo office IP with 23 established accounts is treated as infrastructure. Without establishment evidence, large IP-only groups appear as one queue row.
- **Deep:** IP minimum group size 4; infrastructure ≥ 5 established and ≥ 60 %; collapse above 15 accounts when establishment cannot be judged.

### Q: How do you handle legitimate hubs?

- **10 s:** Relationship history and the pooled rule.
- **30 s:** A payroll account's funding and payees are established relationships, so its pass-through drops a tier per mitigation; a merchant with 50+ counterparties over a week is pooled and not traced through.
- **Deep:** Mitigation needs ≥ 80 % of the episode's in- or outflow over established relationships with non-suspicious counterparties, and is blocked on corroborated rapid paths or when all counterparties are new.

### Q: How do you handle pooled accounts?

- **10 s:** We stop attributing money through them, but still watch them.
- **30 s:** ≥ 50 counterparties over ≥ 7 days. No FIFO links, traces stop, circular search doesn't pass through. They can still be flagged on their own window pass-through, hub, layered receipt or identity evidence.
- **Deep:** Pooled window episodes use amount-matched new-to-new counterparties; chain counts stop at pooled accounts; pooled accounts are never ORIGIN.

## 18.5 Financial investigation

### Q: How do you know this money came from that account?

- **10 s:** By FIFO attribution — a documented convention, not a certainty.
- **30 s:** Each outgoing payment is matched to the oldest incoming money still available. That gives a precise, reproducible link — "₹4,78,000 of TX102080 left as TX102081 after 3 minutes" — but money is fungible, so it's attribution, not proof of the physical rupee.
- **Deep:** The window test and two-way conservation guard against FIFO artefacts; traces balance exactly.

### Q: Does this mean the victim lost this amount?

- **10 s:** No. We never state losses.
- **30 s:** "Value from likely origins" is what the likely origins sent into the case; the case total is transaction volume counted at every hop. Whether anyone lost money is established outside the data.
- **Deep:** CASE-03: ₹6,00,000 from likely origins; ₹28,60,000 total case volume, labelled "transaction volume, not an amount lost".

### Q: What does origin mean?

- **10 s:** The account the money in a case came from.
- **30 s:** A case member that receives no case money and funded what it sent mostly from its own balance or established relationships. Often a victim — but MuleTrace only shows a possible-victim indicator, explicitly "not a determination".
- **Deep:** ≥ 50 % own funds, or ≥ 80 % established funding, or balance-covered; contra-indicated by shared device/KYC with the case, money back above ₹1,000, cluster membership, circular flow, or originating into ≥ 2 cases.

### Q: What does relay mean?

- **10 s:** An account that passes money on.
- **30 s:** A structural role: it received case money and forwarded it — a pass-through at ≥ MODERATE, or forwarding at least 20 % of case money received. Collector and distributor are relays with many senders or many receivers.
- **Deep:** Role assignment order: pooled, origin, hub, collector / distributor / relay, sink, counterparty.

## 18.6 Performance

### Q: How does this scale?

- **10 s:** It's linear-ish per account and bounded everywhere else.
- **30 s:** FIFO runs per account; searches have hop and branch caps; graphs are capped at 80 nodes and traces at 50 with an aggregate node. The demo's 2,118 transactions ingest and analyse in well under a second on this machine.
- **Deep:** Measured here: ingestion ≈ 58 ms, analysis ≈ 29 ms for the demo. The project's status notes record 50,000 rows / 4,000 accounts at ingestion 0.6–0.9 s and analysis 1.8–2.4 s (recorded by the team, not re-measured for this guide).

### Q: What happens with 50k rows?

- **10 s:** It works; recorded analysis time is about two seconds.
- **30 s:** STATUS.md records upload-to-result about 3.4 s, summary 0.35 s, network ≈ 45 ms, trace ≈ 8 ms on a 50k benchmark. Hard limits are 20 MB and 200,000 rows per file.
- **Deep:** The benchmark file is not part of the repository; those figures come from the project's recorded measurements.

### Q: What happens with very large graphs?

- **10 s:** We never draw everything — views are bounded and say so.
- **30 s:** Account network ≤ 80 accounts with a share per hop level; case graph ≤ 80 built from the most valuable money paths; trace ≤ 50 nodes with "+N accounts". The note under the graph states what is not drawn.
- **Deep:** `_select_by_level()`, `_case_story()`, trace aggregation in `trace_view()`; case timeline capped at 200 rows with the true total shown.

## 18.7 Reliability

### Q: Is the result deterministic?

- **10 s:** Yes. Same file and configuration, same output.
- **30 s:** No randomness, no wall clock, sorted iteration everywhere. The configuration hash and the dataset fingerprint identify a result.
- **Deep:** Tested in `test_flow_engine.py` (determinism, order independence) and `test_demo.py` (generator determinism, whole-dataset conservation); age and history are measured from the data, not today's date.

### Q: Does CSV row order matter?

- **10 s:** No.
- **30 s:** Transactions are sorted by time and ID before analysis; a shuffled copy of the demo gives identical scores. One exception by design: if two rows share a transaction ID with different content, the first one in the file is kept.
- **Deep:** Order-independence test in `test_flow_engine.py`; re-checked for this guide on the demo (29 flagged, AC5530 = 95 after shuffling).

### Q: How do you guarantee amount conservation?

- **10 s:** Integer paise and exact fractions — and we check it.
- **30 s:** Every outgoing payment = its links + own funds, to the paisa. Every trace's start amount = kept + stopped at pooled + beyond hop limit, exactly; the console prints "exact" when that holds.
- **Deep:** No floating point in conservation; `Fraction` propagation; dataset-wide conservation tests over every link and every account's forward and backward trace.

## 18.8 Limitations

### Q: What can the system not determine?

- **10 s:** Intent, identity of people, losses, and anything outside the data.
- **30 s:** It sees transactions, not people. It can't see cash withdrawals or other banks, can't prove who controls an account, and FIFO is a convention.
- **Deep:** Flows slower than 72 h aren't linked; the first 7 days are relationship warm-up; one currency per dataset; a victim who genuinely paid the first mule ≥ half the fraud value a week earlier makes that mule read as an origin.

### Q: What happens when data is incomplete?

- **10 s:** It degrades openly — the coverage panel says what's missing.
- **30 s:** Without device/IP/KYC there's no identity family; without opening dates and less than 14 days of data, establishment is unknown, infrastructure can't be judged and IP stays weak; under 7 days, history-based mitigations are unavailable and every account says so.
- **Deep:** Test A15: flow detection works without optional columns; G1b: IP without establishment evidence stays weak and large groups collapse.

### Q: What does fallback mean?

- **10 s:** A simpler window engine you can start instead of FIFO.
- **30 s:** `python run.py --engine window`. No flow links, so no tracing, no layered receipt, no chains; screens say "flow tracing unavailable in fallback mode". It is not automatic.
- **Deep:** Demo: 19 flagged vs 29; hero 70 vs 95; hash `428bd575eef2` vs `b652e4bf70db`.

## 18.9 Product and security

### Q: Where is data stored?

- **10 s:** In one SQLite file on the local machine.
- **30 s:** `backend/muletrace.db` holds the uploaded CSV, decisions and the audit log. Analysis results stay in memory and are recomputed on start.
- **Deep:** Decisions are keyed by the dataset's SHA-256, so re-uploading the same file keeps them.

### Q: Does it leave the machine?

- **10 s:** No. It runs offline on 127.0.0.1.
- **30 s:** The backend makes no outbound calls, the console is served from local files, and nothing is sent to external services.
- **Deep:** Default bind `127.0.0.1:8000`; runtime dependencies are local Python packages and a pre-built frontend bundle.

### Q: Is authentication included?

- **10 s:** No.
- **30 s:** The analyst name is a free-text field recorded with each decision; there is no login, roles or permissions. That would be needed before multi-user deployment.
- **Deep:** The name is stored in browser local storage and sent with each decision; it is truncated to 80 characters server-side.

### Q: Why local-first?

- **10 s:** Transaction data is sensitive; local means no data leaves the analyst's machine.
- **30 s:** It also means it works offline, starts with one command and gives reproducible results anyone can check with the same file and configuration.
- **Deep:** One process, one SQLite file, deterministic recomputation; no external dependency at runtime.

# Part 19 — Presenter Glossary

| Term | Plain English | In MuleTrace | Avoid saying |
|---|---|---|---|
| Transaction | one payment | one valid CSV row: time, sender, receiver, amount (paise), optional attributes | "a suspicious transaction" for every row on the graph |
| Account | a bank account | an ID seen as sender or receiver, with a profile | "a person" or "a suspect" |
| Graph | a picture of connections | accounts as nodes, payments / traced flows / shared attributes as edges | "the graph proves…" |
| Node | a dot | one account | — |
| Edge | a line | aggregated payments sender → receiver, or a traced flow, or a shared attribute | "a transfer" for a dashed attribute link |
| Flow | money moving | money attributed through FIFO links | "the actual rupees" |
| FIFO | first in, first out | outgoing payments consume the oldest live incoming money | "ground truth" |
| Funding lot | a pile of incoming money | one incoming payment's remaining amount in the FIFO queue | — |
| Dwell time | how long money stayed | time between a lot arriving and the payment that used it | — |
| Episode | one burst of in-and-out | connected inflows and outflows of one account linked by FIFO, graded by tier | "a crime" |
| Signal | a detected pattern | pass-through, hub, layered receipt, circular flow, shared attributes | "an alert" that scores automatically |
| Evidence family | a kind of evidence | money flow (cap 60), circularity (20), shared identity (20) | — |
| Qualification | does it count? | the rule deciding whether a signal may score | — |
| Mitigation | an innocent explanation | established-relationship downgrade of an episode by one tier | "whitelisting" |
| Score | a number | sum of rule points, 0–100, an evidence-strength index | "probability", "risk %" |
| Severity | priority band | HIGH ≥ 60, MEDIUM 35–59, LOW 1–34 | "guilty / innocent" |
| Origin | where money came from | ORIGIN role: no case money in, funded mostly by own or established money | "victim" |
| Relay | a pass-through | role: passes case money on (≥ 20 %) | "mule" as a fact |
| Hub | a junction | role: fan-in → fan-out at ≥ MODERATE | "ringleader" |
| Exit / sink | where money stops | SINK role: forwards < 20 % of case money received | "cash-out confirmed" |
| Pooled account | a very busy account | ≥ 50 counterparties over ≥ 7 days; attribution stops there | "whitelisted" |
| Possible-victim indicator | a hint, not a verdict | INDICATED / CONTRA_INDICATED / NOT_ASSESSED, only for origins in flagged cases | "the victim" |
| Case | an investigation unit | connected component of suspicious movement with ≥ 1 flagged member (for listing) | "a crime ring" as a fact |
| Fallback | a backup engine | `--engine window`, no FIFO tracing | "automatic failover" |
| Trace | following money | exact proportional propagation over FIFO links, ≤ 8 hops, ≤ 50 nodes drawn | "where the money really went" |
| value_moved | case total | sum of case transactions, counted at every hop | "money lost", "laundered amount" |
| Exposure | an evidence amount | largest amount in an account's scored evidence; shown, never scored | "loss", "fraud value" |
| Audit trail | history of decisions | append-only log of decisions and resets per account | "deleted" / "overwritten" |

# Part 20 — "Never Say This"

| Do NOT say | Why it is wrong | Say instead |
|---|---|---|
| "This account is definitely a mule." | Scores are evidence strength, not a determination | "This account has strong, corroborated evidence of rapid pass-through." |
| "This is definitely money laundering." | The product detects structures, not offences | "This pattern is consistent with layering." |
| "This amount is the victim's loss." | No screen computes losses | "₹6 lakh entered the case from likely origin accounts." |
| "This person is the victim." | Only an indicator, explicitly not a determination | "Likely origin; indicators consistent with a possible victim — not a determination." |
| "The graph proves criminal activity." | An edge proves a payment, not intent | "The graph shows how the flagged accounts are connected by payments." |
| "Shared IP proves the accounts belong to the same person." | IP is weak evidence; offices share IPs | "They share an IP — weak evidence on its own, 8 points." |
| "The system knows who committed the crime." | It sees accounts, not people | "It shows which accounts moved the money and how." |
| "95 % likely to be fraud." | The score is not a probability | "Ninety-five on a 100-point evidence scale." |
| "The ring laundered ₹28.6 lakh." | value_moved counts the same money at every hop | "₹28.6 lakh of transaction volume across the hops." |
| "We traced exactly where the money physically went." | FIFO is a convention | "Under FIFO attribution, ₹8.33 lakh was traced to these accounts, exactly accounted for." |
| "No false positives." | Defences reduce, not eliminate | "It's designed to avoid common false positives, and it shows what it set aside." |
| "It falls back automatically." | The engine is chosen at start | "There's a window engine you can start instead." |
| "Confirmed means it's proven." | A disposition, not a legal finding | "The analyst recorded a confirmation with a note." |
| "The employer funded the fraud." (backward trace) | FIFO follows the salary that funded the transfer | "The trace follows which incoming money funded the payment — here, a salary." |

# Part 21 — One-Page Cheat Sheet

**What MuleTrace does:** It follows money through accounts using FIFO attribution, flags mule-network structures with a deterministic, explained score, groups them into cases, and records analyst decisions — offline.

**Core pipeline:** CSV → ingest → profiles → FIFO links → episodes → signals → cases & roles → mitigations → qualification → score → explanations.

**Hero case — CASE-03:** 11 accounts, 9 flagged (5 HIGH, 4 LOW); 2 likely origins (AC2207, AC3318) sent ₹6,00,000; 1 hub, 5 relays, 3 sinks; 25 Mar 10:01–13:34 (3 h 33 min); median dwell 7 min; ₹28,60,000 total volume — *not a loss*.

**Hero account — AC5530:** HIGH **95**, Hub, new account (7 days), exposure ₹8,33,000.

**Why flagged:** pass-through STRONG +35 (₹8,37,000 in, ₹8,33,000 out, 99.5 %, avg 5 min) · hub +5 (3 → 3) · corroborated rapid layering +25 (AC5521 → AC5530 → AC5547, 16 min) · cap −5 → **60** · circular flow +20 (₹1,50,000 of ₹3,00,000 back in 3 h 18 min) · shared device +15 → **95**.

**Key differentiator:** every outgoing payment is linked to the money that funded it (FIFO, exact to the paisa), so patterns describe the movement of the *same money* — and the trace always balances ("exact").

**Three numbers to remember:** 29 of 270 accounts flagged (5 HIGH) · 3 cases · 43 set aside with a stated reason.

**Three limitations:** FIFO is a convention · invisible beyond the data (cash, other banks; > 72 h flows) · no authentication; fallback is manual.

**Five likely questions:**

1. *Is 95 a probability?* — No, an evidence-strength index from three capped families.
2. *Is the origin the victim?* — Likely origin; possible-victim indicator, explicitly not a determination.
3. *How do you know the money came from there?* — FIFO attribution: documented convention, exact accounting.
4. *False positives?* — Single pass-throughs never score; history, pooled and infrastructure rules; 43 set aside with reasons.
5. *Deterministic?* — Yes; no randomness, no clock; config hash `b652e4bf70db` in the footer.

**Never claim:** a victim or a loss · proof of crime or of who did it · that the score is a probability.

**Demo navigation:** Data → Reset demo → Overview → Queue → AC5530 → score card → Where money came from / went → Pass-through card (timeline) → Open case CASE-03 → Confirm with note → Not flagged (AC2207, AC7100, AC8800) → Method.

# Implementation Verification

**Git:** branch `feat/cases-list`, commit `b240ee0` ("Update status for the final build"), tagged `v1.0.0`. `main` = `v1.0.0-finalized` (`168094a`). Working tree clean before this guide was written. No product file was changed.

**Run checks:** backend tests `138 passed`; frontend tests `12 passed`; demo analysed with the flow and the window engine against a scratch database; the running console checked read-only for Overview, account AC5530 (network and forward trace) and the Cases list.

**Pages inspected:** Data, Overview, Queue, Not flagged, Cases, Account investigation, Case investigation, Method panel; header search, analyst name, theme, footer.

**Backend modules inspected:** `api.py`, `cases.py`, `config.py`, `demo_data.py`, `explain.py`, `fallback.py`, `flow.py`, `identity.py`, `ingest.py`, `network.py`, `pipeline.py`, `profiles.py`, `scoring.py`, `signals.py`, `store.py`, `summary.py`; `run.py`.

**Frontend modules inspected:** `App.tsx`, `api.ts`, `state.tsx`, `format.ts`, `main.tsx`, pages (`DataPage`, `Overview`, `Queue`, `Reviewed`, `Cases`, `Investigate`, `CasePage`), components (`Investigation`, `GraphView`, `MethodPanel`, `Badges`), `lib/` (`cases`, `decision`, `evidence`, `graphState`, `layout`, `members`, `method`, `paths`, `search`), `index.html`.

**Tests inspected:** `test_api.py`, `test_case_summary.py`, `test_cases_list.py`, `test_console_fixes.py`, `test_demo.py`, `test_flow_engine.py`, `test_ingest.py`, `test_method_config.py`, `test_relationship.py`, `test_scenarios.py`, `frontend/tests/console.test.ts`.

**Demo data inspected:** `data/demo.csv` via `backend/muletrace/demo_data.py` and the full API output (ingestion report, summary, queue, all listed cases with summaries and graphs, 28 accounts, AC5530 traces and network, observations, configuration).

**Discrepancies between documentation and implementation:**

1. **NetworkX** is not used anywhere; graph logic is plain Python (relevant to the judge question "Why NetworkX?").
2. **Fallback is manual** (`--engine window`); nothing switches to it automatically.
3. **DEMO.md, payroll quote:** the script quotes "downgraded because funds came from a 30-day relationship…"; the product now says "downgraded STRONG → WEAK because the money came from and went to counterparties with an established history (payments older than 7 days worth at least 50% of their recent volume)". AC7100's 1 March episode is not mitigated (first 7 days are warm-up); it is set aside as an isolated pass-through.
4. **DEMO.md, merchant:** "280 payments" — the data has 279 incoming payments and 31 settlements (151 counterparties).
5. **Hero case ID** is CASE-03 (cases are numbered by size; the unflagged payroll flow is CASE-01). Under the fallback engine the same ring is CASE-02.
6. **Case list navigation:** `/cases` is reachable from the Overview tile, not from the header; the Case page has no link back to the list (listed as deferred in `STATUS.md`).
7. **Trace amounts in circular flows** can exceed a single transaction's amount (AC5530 → AC6651 shows ₹4,74,000 over a ₹2,38,000 payment); conservation holds on the start total. Not a defect in the accounting, but easy to misread.
8. **Backward trace reaches the employer** AC9002 (unflagged, no role) through AC3318's salary.
9. **Signal reason across days:** a pass-through sentence prints the end time without a date, so AC3318's raw (unscored) episode reads "25 Mar 09:40–09:27" (it ends on 27 Mar). This sentence is only in the API response, not shown on screen, because the signal does not score.
10. **Local database history:** the database on this machine holds earlier test decisions for AC5530 whose last entry reads "confirmed → cleared" while the status is Open (written before the per-account reset entry existed). Current code writes a per-account reset entry (re-checked on a scratch database).
11. **Architecture wording:** "receives funds from a case member above ₹1 000" — the implementation counts payments from case members that are themselves moving suspicious money, at any time in the dataset.
12. **Performance figures for 50,000 rows** come from `STATUS.md` and were not re-measured; the demo timings in this guide were measured on this machine.
