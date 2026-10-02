# MuleTrace — Status

_Updated after: full build complete (backend, console, docs, demo). Next: team rehearsal / organiser data dry-run._

## Complete
- T0–T19: ingestion, profiles, Fund-Flow Engine, signals, identity, cases/roles/indicator, mitigations,
  qualification, scoring, explanations, store, API, bounded network/trace views, fallback engine,
  demo generator, analyst console (overview, queue, investigation, case, data pages; light + dark),
  README, DEMO script, `start.ps1` / `start.sh`, `scripts/evaluate.py`.

## In progress
- Nothing.

## Next (process, not code)
- At hand-out: run the organiser CSV through **Data** first; check the coverage panel and thresholds (`/api/config`).
- Rehearse DEMO.md three times; record a backup video.

## Blocked
- Nothing.

## Tests
- `backend\.venv\Scripts\python -m pytest -q backend\tests` → 62 passed.
- Ingestion edge cases (BOM, CRLF, ₹ formats, step/epoch modes, currency, duplicates, aliases); flow-engine gate (conservation, determinism, shuffle, same-timestamp, expiry, pooled boundary, exact trace),
  S1–S4, A1–A15, G1–G13, demo dataset, API flow, persistence across restart, fallback (G12), trace cap (G10).
- Performance: 50 000 rows → ingest 0.9 s + analysis 2.4 s.
- Frontend: `npm run build` (type-checked) passes; checked visually at 1536 px (light + dark) and 375 px (no horizontal scroll).

## V1 parity (problem statement)
| Capability | Where | Verified by |
|---|---|---|
| CSV ingestion + diagnostics | `ingest.py`, Data page | ingestion tests, demo report |
| Account graph | `profiles.py`, network view | API network test |
| Fan-in → fan-out | `signals.hub_signals` | S1, G3, demo ring 2 |
| Circular transfers | `signals.round_trip_signals` | S2, A13, demo ring 3 + hero |
| Pass-through chains, near-zero retention | `flow.py`, `signals.relay_signals`, chains | S3, A1, A2, G2, G8 |
| Device / IP / KYC clusters of new accounts | `identity.py` | S4, A6, A7, A14, G1 |
| Risk score + plain-language reason | `scoring.py`, `explain.py` | score invariants, demo |
| Expand network | network endpoint, graph double-click | G10, manual |
| Confirm / Clear | store + disposition panel | API persistence test |

## Active decisions (clarifications of the frozen spec, no redesign)
- Analysis results are derived and recomputed from the stored CSV (SQLite stores CSV, dispositions, audit).
- Episode conservation = `forwarded / max(inflow, outflow)` plus per-lot window test; unlinked lots still window-tested.
- Case edges = transactions of the episodes/paths that made an account flow-active, limited to outflows inside
  the episode's tier window. (Fixed victim-as-relay and stretched case windows; regressions in test_demo.)
- Identity restoration (G13c) links only flow-active accounts sharing a case.
- LAYERED_RECEIPT re-evaluated at qualification against final relays (origins are not relays).
- Roles and the possible-victim indicator are shown only for cases containing a flagged account (pooled always shown).

## Known limitations
- FIFO attribution is a convention; 72 h horizon; first 7 days are relationship warm-up.
- A mule with a ≥ 7-day prior relationship to its victim can be read as ORIGIN of that flow.
- Fallback engine has no chain/corroboration bonuses (no traced links).
- Single currency per dataset.

## Do NOT change
- Pipeline order, scoring table, tiers, qualification rules, pooled contract (ARCHITECTURE §2, §5–§8).
- Integer minor units / Fraction tracing. No wall clock in analysis.
