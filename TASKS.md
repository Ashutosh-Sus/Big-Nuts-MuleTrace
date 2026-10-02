# MuleTrace — Tasks (dependency order)

Status: `[ ]` todo · `[~]` in progress · `[x]` done (acceptance criteria pass)

| ID | Task | Depends | Acceptance |
|---|---|---|---|
| T0 | Bootstrap: repo layout, venv, pinned deps, Vite+TS+Tailwind, `run.py`, `.gitignore` | — | `python run.py` serves SPA + `/api/health`; `pytest` runs |
| T1 | Config + data contracts (`config.py`, frontend `types.ts`) | T0 | thresholds of ARCHITECTURE §5–§8 in one place; config hash stable |
| T2 | Ingestion (`ingest.py`): aliases, time modes, currency, validation, report | T1 | ingestion edge-case tests pass |
| T3 | Profiles, establishment, relationships, pooled (`profiles.py`) | T2 | profile/establishment/relationship tests pass |
| T4 | **Flow engine** (`flow.py`): lots, links, own funds, episodes, tiers, Fraction trace | T3 | conservation + determinism + same-timestamp + pooled-boundary + episode tests pass (**gate**) |
| T5 | Raw signals (`signals.py`): RELAY, HUB, LAYERED_RECEIPT, ROUND_TRIP | T4 | S1–S3, A2, A3, A11, A12, A13, G3, G6, G8 |
| T6 | Identity clusters (`identity.py`) | T3 | S4, A6, A7, A14, G1, IP fallback |
| T7 | Cases, roles, victim indicator (`cases.py`) | T5, T6 | A4, A8, G4 |
| T8 | Mitigations, qualification, scoring (`scoring.py`) | T7 | G2, G5, G11, G13a–c, A1, A9, A10, score invariants |
| T9 | Explanations + observations (`explain.py`) | T8 | every scored signal has txn ids / path; why-not for decoys |
| T10 | Pipeline + store + API (`pipeline.py`, `store.py`, `api.py`) | T9 | upload → summary → account → disposition → restart persists |
| T11 | Network + trace endpoints (`network.py`) | T10 | caps (80 / 50 + aggregate), pooled stop, G9, G10 |
| T12 | Demo + scenario generator (`demo_data.py`), bundled `data/demo.csv` | T5–T8 | hero network HIGH, decoys unflagged, deterministic bytes |
| T13 | Fallback window engine behind the same contract | T10 | G12 |
| T14 | Frontend shell, tokens (light/dark), start + ingestion report | T1 | builds; both themes |
| T15 | Overview + queue | T14, T10 | filters, group items |
| T16 | Investigation: score, signals/evidence, timeline, case card, why-not, disposition | T15, T11 | end-to-end on hero |
| T17 | Graph component (network + trace mode, role shapes, legend, caps) | T16 | trace edges visibly distinct, labelled FIFO attribution |
| T18 | Integration + reset + offline check + README | all | fresh clone → `python run.py` → demo script works |
| T19 | `scripts/evaluate.py` (only if organiser data carries labels) | T10 | precision/recall per pattern |

Test catalogue (expected outcomes live in `backend/tests/`):
S1–S7 baseline · A1–A15 adversarial · G1–G13 audit regressions · conservation · determinism · shuffle.
