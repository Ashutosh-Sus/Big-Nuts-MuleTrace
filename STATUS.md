# MuleTrace — Status

_Updated after: console QA remediation (B1–B14, graph readability, mobile, accessibility; no detection change). Nothing pushed._

## Complete
- T0–T23 (see TASKS.md): engine, API, analyst console (light + dark), docs, demo, start scripts, evaluation script.
- Release audit: problem-statement parity through the UI, frozen v1.2 conformance, demo walk-through,
  conservation, performance, light/dark/mobile, prohibited-reference and secret scans, history cleanup.

## Console QA remediation (display, API views and state only — no detection change)
A full product QA pass (every surface, demo / fallback / empty / malformed / unusual-ID / 50k data, light + dark,
desktop + 375 px) found console defects; all fixed. Engine snapshot before/after — every account's score,
severity, components, role, cases, exposure, observations; every case; every forward/back trace — byte-identical
on demo, fallback engine and the 50k benchmark.
- **Search (B1):** results carry the query they answer; Enter uses only current results, else searches now;
  exact ID preferred; "No account matches" feedback. (`AC1` → `AC5530` + Enter used to open AC1000.)
- **Evidence (B2):** a real neutral state — the graph opens undimmed; a card selects, the same card deselects;
  a banner names the highlighted evidence with "Show all"; the timeline shows the first evidence when none is
  selected. Cleared accounts are no longer faded (green ring + "cleared" in the label), so faded means only
  "outside the highlighted evidence".
- **Decisions (B3, B12):** a failed request keeps the note and shows "The decision was not saved …" (no
  unhandled rejection); reason shortcuts grouped per action (Confirm / Clear) and only for available actions.
- **Overview ↔ Not flagged (B4):** the Overview count was preview rows after collapsing the 23 office-IP
  accounts and omitting four reason kinds (21 vs 43). Both now count the same scope — not-flagged accounts with
  a stated reason (all kinds but "no pattern", `REVIEW_KINDS`): demo 43 = 43; the preview says "12 examples".
- **Trace expansion (B5):** double-click in a trace opens that account's own trace (view in the URL); traces
  are never merged, so an exact total is never mixed with another start account's amounts.
- **Bounded timelines (B6):** case timeline returns `timeline_total`, `?member=` gives one member's case
  transactions; signal timelines carry `timeline_total`; headers say "first 200 of 2085" instead of "all".
- **Reset (B7):** the audit log stays append-only; each decision cleared by Reset gets its own RESET entry
  (confirmed → open), shown in the trail as "demo reset". Previously status read Open while the trail ended in
  "confirmed". Other datasets' decisions untouched.
- **Decisions on not-flagged accounts (B8, B11):** allowed by §10 and kept; Overview lists them separately
  ("not in the queue"), flagged decision counts equal the queue's, Not flagged rows show the decision, the case
  reports `confirmed_flagged` / `decided_not_flagged` ("0 of 0" / "1 of 0 flagged confirmed" gone).
- **URL-unsafe IDs (B9):** every link encodes IDs (`lib/paths.ts`); account routes take `{account:path}`
  with the detail route registered after its sub-routes (`ACC/7#9` returned the page HTML before).
- **Long notes (B10):** containment (`minmax(0,1fr)` track, `overflow-wrap:anywhere`) — 375 px stays 375 px.
- **Graph after a decision (B13):** the status is patched into the drawing; expanded neighbourhoods survive.
- **Fallback views (B14):** "came from" / "went" follow suspicious transactions into / out of the account hop by
  hop (both showed the same 2-hop network before); flow engine unchanged.
- **Graphs:** layered layout on money links only (shared attributes no longer move accounts), wide columns
  wrapped into a grid (payroll fan-out: 3.3 px → 12 px labels, all 26 in view), money flowing back drawn as an
  arc, labels never below 8 px (large graphs open at a readable zoom around the key account, "Fit all" shows
  everything), short edge labels shown on small graphs or highlighted / selected links (hero network: 0 edge-
  label collisions, was 4), selection halo distinct from severity / decision / evidence, severity and decision
  in words on each account, "Find account in graph" picker + selection panel (keyboard and touch), full-screen
  explorer, legend covering every encoding.
- **Capped graphs:** account network gives each hop level a share of the 80 nodes, attached to a drawn account
  one hop closer, mixing ordinary-only accounts in when the filter is off (Hops / filter visibly change a capped
  graph). Case network over 80 members is built from its most valuable money paths (50k case: 16 origins, 46
  relays, 7 collectors, 11 cash-out, connected; was 40 victims + 39 hubs, no cash-out).
- **Mobile / readability / a11y:** header not sticky below `sm`, analyst name visible at every width (decision
  panel says "Recorded as …"), inline graph is a still preview with "Open graph to explore" (no scroll trap);
  smallest text 11 → 12 px; members flagged first in a scrolling table; empty states on a zero-flag Overview;
  IST audit times and dated case windows; Exposure explained; priority reasons two lines; Data stays on the
  ingestion report after Load / Reset ("Continue to Overview"); keyboard drop zone, arrow-key graph tabs,
  `aria-pressed` evidence cards, focusable member rows, labelled filter, larger touch targets.
- Tests: `test_console_fixes.py` (15) + `frontend/tests/console.test.ts` (10, `npm test`, Node's built-in runner).
- Checked: DEMO.md end to end (2 125 / 6 rejected / 1 duplicate; 29 flagged of 270, 5 high, 3 cases; 43 = 43;
  AC5530 HIGH 95 = 60 + 20 + 15; diamonds for AC2207 / AC3318; ₹8,33,000 traced exact; timeline 10:05 10:08 10:11
  10:12 13:30 13:34; case card ₹6 L, 0 → 1 of 9 confirmed); every page light + dark ≥ 4.5:1; 375 px no overflow.

## Quality fixes — dark-theme filled controls, graph edges without colour alone (§11)
- Text on filled controls now comes from tokens: `--on-accent`, and `--high-fill` / `--on-high` for Confirm.
  Light values equal what was rendered before (white text, same red), so light theme is unchanged. Dark theme:
  near-black text on the accent fill (primary buttons, active graph-mode tab) 2.62 → 7.2:1; Confirm on a
  slightly lighter red with near-black text 4.30 → 5.66:1 (`--high` itself unchanged: badges, nodes untouched).
  No `text-white` left in the console.
- Graph: other (non-suspicious) transaction edges are dotted with hollow arrowheads; suspicious edges solid with
  filled arrows; shared-attribute links stay dashed without arrows; traced flow links unchanged. Legend names the
  line styles. Graph data and the "Suspicious flows only" filter are unchanged.
- Checked: every page, light + dark, desktop + 375 px — no text below 4.5:1, no overflow; filter on / off; Confirm
  then Clear through the buttons (header, graph node, audit trail).

## Targeted audit — T20–T23 + G15
- Released vs current backend on the demo data: 2 722 of 2 724 pre-existing API responses byte-identical; the
  two differences are the intended G15 corrections (CASE-01, CASE-05). No core, dependency or data file changed.
- §7.2 checked on every case of demo (flow + fallback engines), a pooled-member scenario and the 50k benchmark
  across case API, case graph, account header, indicator, observations, queue, search, network and trace views.
- T21 export = `/api/queue` on 108 filter combinations; T22 graphs = case members / transactions / identity links.
- One finding, fixed: `/reviewed` reason-chip counts used `opacity-70` (3.63:1 in light theme); removed, now
  ≥ 7.28:1 light and ≥ 7.83:1 dark, no text on the page below 4.5:1 in either theme.
- Noted, not changed (pre-existing in the released console, dark theme): white text on accent controls
  (primary buttons, active graph-mode tab) 2.62:1; Confirm button 4.30:1.

## T23 — light-theme muted text contrast (one token, no layout change)
- Muted text (subtitles, labels, table headers, footers, hints; ~65 uses) was 4.25:1 on the page background and
  4.02:1 on sunken panels in light theme — below 4.5:1 for small text. Every other text / background token pair
  in both themes already passed.
- Light `--muted` 118 116 110 → 108 106 100, the smallest step clearing 4.5:1 on page, surface, raised and
  sunken (now 4.91 / 5.27 / 5.41 / 4.66; on the accent tint 3.9 → 4.51). Dark theme unchanged (≥ 4.79).
- Running app, light theme: all 397 muted-text elements across Overview, Queue, Not flagged, Data, two account
  pages and two case pages measure ≥ 4.8:1 against their actual (composited) backgrounds.

## Fixed — G15 case roles for unflagged cases (§7.2, display only)
- Defect: `GET /api/cases/{id}` returned case roles, origins and value from origins for a case with no flagged
  member, so the "Connected case" card and the Case page labelled participants of flows nobody was flagged for
  (demo: payroll AC7100 "Distributor", its employees "Sink", AC7000 "Likely origin"; near miss AC6101 "Relay",
  AC6100 "Likely origin") while the account header correctly showed no role. Dated from T16; detection unaffected.
- Fix: for a case without a flagged member the endpoint uses the per-account rule (`Analysis.role`: pooled →
  POOLED, otherwise none inside such a case), `origins` = [] and `value_from_origins` = null; members are then
  ordered by score (the old role ordering would itself reveal origins). Flagged cases byte-identical (demo
  CASE-02/03/04 compared before/after); no other field of an unflagged case changed.
- UI: case card and Case page show "—" for value from origins and "No member flagged — roles are not assigned."
- Tests (4, `test_g15_*`): payroll and near-miss cases (no roles / origins / value, account page and case graph
  agree, no indicator), hero case keeps roles + origins + value and matches the graph, pooled member of an
  unflagged case still POOLED. Three fail on the pre-fix code.

## T22 — case network graph (no detection change)
- Gap: the Case page had members and a timeline but no picture of the whole case.
- `GET /api/cases/{id}/network`: same contract as the account network (mode `network`, no focus) with the case's
  members, its case transactions aggregated per sender → receiver, case roles (only for a case with a flagged
  member, §7.2), dispositions and shared-attribute links. Over 80 members the drawn part is grown along case
  transactions from the best-ranked member (origins, then flagged by score), so it stays connected; picking the
  top 80 by score alone left 80 unconnected nodes on the 50k-row benchmark's 2 739-member case.
- `network.py`: identity-link builder extracted into `_identity_edges` (shared; account network output unchanged).
- Case page: graph above the member table (existing `GraphView` + legend); clicking a node or a member row lights
  up its transactions and bolds it in the timeline; double-click opens the account. `GraphView` takes an optional
  tooltip hint (default unchanged).
- Tests (5): hero case (members, every case transaction once on the right edge, totals, roles, origins / hub),
  404, decisions shown, cap + connectivity (fan-out and a 120-relay chain with scrambled names), fallback engine.
- 50k rows, largest case (2 739 members): case network 14 ms, 80 nodes / 79 edges, connected.

## T21 — queue CSV export (no detection change)
- `GET /api/export/queue.csv` takes the `/api/queue` filters; both endpoints use one shared filter function, so
  membership and order are identical. `/api/queue` response unchanged.
- Columns: rank, type, id, members, severity, score, patterns, families, role, cases, exposure (major units),
  currency, exposure_display, primary_reason, decision, decision_analyst, decision_note, decision_at_utc.
  UTF-8 with BOM (₹ opens correctly in spreadsheet tools); text cells starting `=` `+` `-` `@` (also tab / CR)
  get a `'` prefix; numbers stay numeric. A group item is one row listing its members.
- File name `muletrace-queue-<dataset sha256, 12 chars>-<config hash>.csv`, sent as an attachment.
- Queue page: "Export CSV" next to the account filter; the link carries the current severity / pattern /
  status / account filters.
- Tests (14): export = queue for 9 filter combinations, headers + filename, ₹ round trip, decision after
  Confirm, formula prefix (helper + formula-like account IDs end to end), group row.
- 50k rows: export 41 ms vs `/api/queue` 56 ms (1 439 rows); 25 ms vs 44 ms for HIGH + MEDIUM.

## T20 — "Reviewed and not flagged" page (no detection change)
- Gap: `/api/observations` (§10) existed but no screen used it; Overview showed 12 of N set-aside accounts with
  no way to see the rest.
- API: `/api/observations` gains `flagged`, `q`, comma-list `kind`, `offset`; each item carries the account's
  flagged / severity / score / role; `counts` per kind (before the kind filter). Old parameters unchanged.
- UI: `/reviewed` ("Not flagged" in the nav; "View all" on the Overview card). Filters by reason (No pattern off
  by default), scope (not flagged / all), account; identical statements (e.g. office IP on 23 accounts) collapse
  into one expandable row. Nav padding tightened below `sm` and the nav may wrap: no horizontal scroll at 375 px
  ("Data" drops to a second row at exactly 375 px).
- Test: `test_observations_filters_and_counts`.

## Amendment v1.2.1 — relationship strength (closes relationship seeding)
- Problem: a ₹1,000 victim → mule payment 14 days earlier made the pair ESTABLISHED, so the ₹3 L transfer was
  dropped from the case, the first mule read as ORIGIN (score 0, possible-victim indicator), the victim left the
  case, and a 3-relay rapid chain fell HIGH 60 → MEDIUM 35.
- Rule (ARCHITECTURE §4): for a payment, ESTABLISHED needs history older than 7 days ≥
  `relationship_history_share` (config, 0.50) × the pair's volume in the last 7 days including that payment.
  Used by case edges, ORIGIN funding and mitigations; pooled window test unchanged.
- Result: seeded mule is a relay again (HIGH), victim back in the case as ORIGIN; demo output byte-identical
  (every score, role, case, mitigation, observation); hero AC5530 still HIGH 95; 50k-row timing unchanged.
- Tests: `test_relationship.py` R1–R6 (17 cases: seeding, genuine history, hero, established mule with
  seeded boundaries, ratio sweep, split transfers, in-window padding, many-tiny vs few-meaningful) and G14,
  which replaces the old known-limitation pin.
- Wording: the "downgraded by history" explanation now states the rule.

## Fixed during the release audit
- `/api/summary` took 12 s on 50k rows (per-account scan of all attribute groups) → index built once: 0.35 s.
- Data page overflowed at phone width (grid track) → fixed; all pages 375 px wide at 375 px.
- Backward-trace footer said "kept along the way" → "originated from account balances".
- DEMO.md timeline line corrected to the real hero timeline.
- ARCHITECTURE §6.1/§7.1/§7.2/§12 synced with implemented clarifications (no behaviour change).

## Tests
- `backend\.venv\Scripts\python -m pytest -q backend\tests` → **120 passed**.
- `cd frontend; npm test` → **10 passed** (search race, evidence toggle, decision failure / reasons, trace merge guard,
  status patch, link encoding, fan-out wrap, IST times).
- Ingestion edge cases; flow gate (conservation, determinism, shuffle, same-timestamp, expiry, pooled boundary,
  exact trace); dataset-wide conservation (every link, every account's forward/back trace at 2 and 8 hops);
  S1–S4, A1–A15, G1–G15; R1–R6 relationship strength; demo; API + persistence; observations filters; queue CSV export; case network; fallback (G12); trace cap (G10);
  console consistency (Overview = Not flagged scope, decisions on any account, reset audit, bounded timelines, URL-unsafe IDs,
  capped graph selection, directional fallback views).

## Performance (50 000 rows, 4 000 accounts)
- Ingestion 0.6–0.9 s · analysis 1.8–2.4 s · upload endpoint 3.4 s · summary 0.35 s (61 ms cached)
- network (3 hops, capped 80) ≈ 45 ms · trace (capped 50) ≈ 8 ms · queue CSV export ≈ 41 ms · case network (capped 80) ≈ 14 ms.
- After the console remediation (own 50k benchmark, 784-member case): case network 20 ms; case page to graph ≈ 0.8 s;
  member highlight 47 ms; filter toggle refetch ≈ 0.4 s.

## Known limitations
- FIFO attribution is a convention; 72 h horizon; first 7 days are relationship warm-up.
- **Prior relationship of substantial value** (ARCHITECTURE §12): if a victim genuinely sent the first mule
  ≥ 50 % of the fraud value ≥ 7 days earlier, that mule reads as an origin; rest of chain + cash-out still
  flagged (R5/R6). Token or split seeding no longer works.
- Fallback engine has no chain/corroboration bonuses. Single currency per dataset.

## Active decisions (clarifications, documented in ARCHITECTURE)
- Analysis is derived and recomputed from the stored CSV; SQLite keeps CSV, dispositions, audit.
- Case edges = transactions of the suspicious episodes/paths only (tier-window outflows).
- Identity restoration links only flow-active case members.
- Roles / possible-victim indicator shown only for cases with a flagged member.
- Relationship ESTABLISHED is money-weighted per payment (v1.2.1, §4).
- Decisions may be recorded on any account (§10); the queue / export list flagged accounts; decisions on
  not-flagged accounts are listed on the Overview. Reset writes per-account RESET audit entries (append-only).

## Git
- Local `main`, history rewritten to remove machine-local ignore entries; nothing pushed.
- Machine-local exclusions live in `.git/info/exclude`, not in `.gitignore`.

## Do NOT change
- Pipeline order, scoring table, tiers, qualification rules, pooled contract (ARCHITECTURE §2, §5–§8).
- Integer minor units / Fraction tracing. No wall clock in analysis.
