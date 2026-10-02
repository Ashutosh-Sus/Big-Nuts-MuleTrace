# MuleTrace — Status

_Updated after: backend engine + API complete; frontend next._

## Complete
- T0–T13 backend: ingestion, profiles, Fund-Flow Engine (gate passed), signals, identity, cases/roles/indicator,
  mitigations, qualification, scoring, explanations, store, API, network/trace views, demo generator, fallback engine.
- `data/demo.csv` generated deterministically by `scripts/make_demo.py` (hero network, 2 more rings, decoys, 7 bad rows).

## In progress / next
- T14–T17 frontend (Vite + React + Tailwind + Cytoscape), then T18 integration + README + DEMO guide.

## Blocked
- Nothing.

## Tests
- `backend\.venv\Scripts\python -m pytest -q backend\tests` → 52 passed.
- Covers flow invariants (gate), S1–S4, A1–A15 (A11 inside S2), G1–G13, demo dataset, API, fallback (G12), trace cap (G10).

## Active decisions (clarifications of the frozen spec, no redesign)
- Analysis results are derived and recomputed from the stored CSV (SQLite stores CSV, dispositions, audit).
- Episode conservation uses `forwarded / max(inflow, outflow)` (amount match both ways), plus per-lot window test;
  unlinked lots (hidden behind a reservoir) still get the window test.
- Case edges are only the transactions of episodes/paths that made an account flow-active (raw ≥ MODERATE);
  not every historical linked payment. (Fixed V2 victim misclassification; regression in test_demo.)
- Identity restoration (G13c) links only flow-active accounts sharing a case — never origins/boundary accounts.
- LAYERED_RECEIPT is re-evaluated at qualification against final relays (ORIGIN accounts are not relays).

## Known limitations
- FIFO attribution is a convention; 72 h horizon; first 7 days are relationship warm-up.
- A mule with a ≥7-day prior relationship to its victim can be read as ORIGIN of that flow (relationship-history rule).
- Fallback engine has no chain/corroboration bonuses (no traced links).
- Single currency per dataset.

## Do NOT change
- Pipeline order, scoring table, tiers, qualification rules, pooled contract (ARCHITECTURE §2, §5–§8).
- Integer minor units / Fraction tracing. No wall clock in analysis.
