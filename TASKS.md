# MuleTrace — Tasks (dependency order)

Status (all tasks complete — see STATUS.md): `[ ]` todo · `[~]` in progress · `[x]` done (acceptance criteria pass)

| ID | Task | Depends | Acceptance |
|---|---|---|---|
| [x] T0 | Bootstrap: repo layout, venv, pinned deps, Vite+TS+Tailwind, `run.py`, `.gitignore` | — | `python run.py` serves SPA + `/api/health`; `pytest` runs |
| [x] T1 | Config + data contracts (`config.py`, frontend `api.ts`) | T0 | thresholds of ARCHITECTURE §5–§8 in one place; config hash stable |
| [x] T2 | Ingestion (`ingest.py`): aliases, time modes, currency, validation, report | T1 | ingestion edge-case tests pass |
| [x] T3 | Profiles, establishment, relationships, pooled (`profiles.py`) | T2 | profile/establishment/relationship tests pass |
| [x] T4 | **Flow engine** (`flow.py`): lots, links, own funds, episodes, tiers, Fraction trace | T3 | conservation + determinism + same-timestamp + pooled-boundary + episode tests pass (**gate**) |
| [x] T5 | Raw signals (`signals.py`): RELAY, HUB, LAYERED_RECEIPT, ROUND_TRIP | T4 | S1–S3, A2, A3, A11, A12, A13, G3, G6, G8 |
| [x] T6 | Identity clusters (`identity.py`) | T3 | S4, A6, A7, A14, G1, IP fallback |
| [x] T7 | Cases, roles, victim indicator (`cases.py`) | T5, T6 | A4, A8, G4 |
| [x] T8 | Mitigations, qualification, scoring (`scoring.py`) | T7 | G2, G5, G11, G13a–c, A1, A9, A10, score invariants |
| [x] T9 | Explanations + observations (`explain.py`) | T8 | every scored signal has txn ids / path; why-not for decoys |
| [x] T10 | Pipeline + store + API (`pipeline.py`, `store.py`, `api.py`) | T9 | upload → summary → account → disposition → restart persists |
| [x] T11 | Network + trace endpoints (`network.py`) | T10 | caps (80 / 50 + aggregate), pooled stop, G9, G10 |
| [x] T12 | Demo + scenario generator (`demo_data.py`), bundled `data/demo.csv` | T5–T8 | hero network HIGH, decoys unflagged, deterministic bytes |
| [x] T13 | Fallback window engine behind the same contract | T10 | G12 |
| [x] T14 | Frontend shell, tokens (light/dark), start + ingestion report | T1 | builds; both themes |
| [x] T15 | Overview + queue | T14, T10 | filters, group items |
| [x] T16 | Investigation: score, signals/evidence, timeline, case card, why-not, disposition | T15, T11 | end-to-end on hero |
| [x] T17 | Graph component (network + trace mode, role shapes, legend, caps) | T16 | trace edges visibly distinct, labelled FIFO attribution |
| [x] T18 | Integration + reset + offline check + README | all | fresh clone → `python run.py` → demo script works |
| [x] T19 | `scripts/evaluate.py` (only if organiser data carries labels) | T10 | precision/recall per pattern |
| [x] T20 | "Reviewed and not flagged" page on `/api/observations` (§9–§11): reason / scope / account filters, identical statements grouped | T15, T10 | every set-aside account browsable; Overview links to it; 375 px, both themes |
| [x] T21 | Queue CSV export `GET /api/export/queue.csv` (§10) + Queue page "Export CSV" carrying the current filters | T15, T10 | rows = `/api/queue` for the same filters (membership, order, score, severity); ₹ survives; decisions included; formula cells prefixed; group = one row; filename has dataset fingerprint + config hash |
| [x] T22 | Case network graph: `GET /api/cases/{id}/network` (§10) + graph on the Case page (select member → its transactions, double-click → investigate) | T11, T16, T17 | nodes = case members, every case transaction on its edge, case roles; capped 80 with a connected drawn part; fallback engine; 375 px, both themes |

Test catalogue (expected outcomes live in `backend/tests/`):
S1–S7 baseline · A1–A15 adversarial · G1–G15 audit regressions · R1–R6 relationship strength · conservation · determinism · shuffle.
