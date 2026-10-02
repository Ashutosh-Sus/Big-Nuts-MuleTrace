# MuleTrace — Status

_Updated after: T22 case network graph (build phase after release; core untouched). Nothing pushed._

## Complete
- T0–T22 (see TASKS.md): engine, API, analyst console (light + dark), docs, demo, start scripts, evaluation script.
- Release audit: problem-statement parity through the UI, frozen v1.2 conformance, demo walk-through,
  conservation, performance, light/dark/mobile, prohibited-reference and secret scans, history cleanup.

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
- `backend\.venv\Scripts\python -m pytest -q backend\tests` → **101 passed**.
- Ingestion edge cases; flow gate (conservation, determinism, shuffle, same-timestamp, expiry, pooled boundary,
  exact trace); dataset-wide conservation (every link, every account's forward/back trace at 2 and 8 hops);
  S1–S4, A1–A15, G1–G14; R1–R6 relationship strength; demo; API + persistence; observations filters; queue CSV export; case network; fallback (G12); trace cap (G10).

## Performance (50 000 rows, 4 000 accounts)
- Ingestion 0.6–0.9 s · analysis 1.8–2.4 s · upload endpoint 3.4 s · summary 0.35 s (61 ms cached)
- network (3 hops, capped 80) ≈ 45 ms · trace (capped 50) ≈ 8 ms · queue CSV export ≈ 41 ms · case network (capped 80) ≈ 14 ms.

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

## Git
- Local `main`, history rewritten to remove machine-local ignore entries; nothing pushed.
- Machine-local exclusions live in `.git/info/exclude`, not in `.gitignore`.

## Do NOT change
- Pipeline order, scoring table, tiers, qualification rules, pooled contract (ARCHITECTURE §2, §5–§8).
- Integer minor units / Fraction tracing. No wall clock in analysis.
