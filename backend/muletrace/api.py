"""HTTP API and static frontend hosting (ARCHITECTURE §10)."""
from __future__ import annotations

import csv
import io
import threading
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import network as net
from .config import DEFAULT, Config
from .explain import indicator_view
from .flow import TIER_NAMES
from .ingest import IngestError, parse_csv
from .pipeline import Analysis, analyze
from .store import Store
from .summary import case_summary

ROOT = Path(__file__).resolve().parents[2]
DIST = ROOT / "frontend" / "dist"
DEMO_CSV = ROOT / "data" / "demo.csv"
PATTERNS = ("RELAY", "HUB", "LAYERED_RECEIPT", "ROUND_TRIP", "IDENTITY")
PATTERN_LABELS = {"RELAY": "Pass-through", "HUB": "Fan-in → fan-out", "LAYERED_RECEIPT": "Layered funds received",
                  "ROUND_TRIP": "Circular flow", "IDENTITY": "Shared attributes"}
# Observation kinds that state why activity was considered and set aside (§9). NO_PATTERN ("nothing notable")
# is not one of them. The Overview count and the "Not flagged" page both use exactly this scope.
REVIEW_KINDS = ("MITIGATED", "ORIGIN_ZEROED", "INFRA_ATTRIBUTE", "ISOLATED_RELAY", "POOLED", "UNCORROBORATED",
                "NEAR_MISS", "ORIGIN", "RECIPROCAL", "HISTORY_UNAVAILABLE")
CASE_TIMELINE_LIMIT = 200
SIGNAL_TIMELINE_LIMIT = 60


class ResetBody(BaseModel):
    analyst: str = "analyst"


class DispositionBody(BaseModel):
    status: str
    note: str = ""
    analyst: str = "analyst"


class State:
    def __init__(self, store: Store, cfg: Config):
        self.store = store
        self.cfg = cfg
        self.lock = threading.Lock()
        self.dataset: dict | None = None
        self.report: dict | None = None
        self.analysis: Analysis | None = None

    def load(self, name: str, data: bytes, persist: bool = True) -> None:
        res = parse_csv(data, self.cfg)
        if not res.txns:
            raise IngestError("No valid transactions in file", {"report": res.report})
        an = analyze(res.txns, self.cfg, res.report["currency"])
        with self.lock:
            self.dataset = self.store.add_dataset(name, data) if persist else self.dataset
            self.report = res.report
            self.analysis = an

    def restore(self) -> None:
        row = self.store.active_dataset()
        if row:
            res = parse_csv(row["csv"], self.cfg)
            self.analysis = analyze(res.txns, self.cfg, res.report["currency"])
            self.report = res.report
            self.dataset = {"id": row["id"], "name": row["name"], "sha256": row["sha256"]}

    def require(self) -> Analysis:
        if self.analysis is None:
            raise HTTPException(409, "No dataset loaded. Upload a CSV or load the demo dataset.")
        return self.analysis

    def dispositions(self) -> dict:
        return self.store.dispositions(self.dataset["sha256"]) if self.dataset else {}


def create_app(db_path: Path | str | None = None, cfg: Config = DEFAULT, autoload_demo: bool = True) -> FastAPI:
    app = FastAPI(title="MuleTrace", docs_url="/api/docs", openapi_url="/api/openapi.json")
    state = State(Store(db_path or ROOT / "backend" / "muletrace.db"), cfg)
    state.restore()
    if state.analysis is None and autoload_demo and DEMO_CSV.exists():
        state.load("demo.csv", DEMO_CSV.read_bytes())
    app.state.mt = state

    def account_or_404(an: Analysis, account: str):
        if account not in an.ds.accounts:
            raise HTTPException(404, f"Unknown account {account}")
        return an.ds.accounts[account]

    def txn_row(an: Analysis, t: int) -> dict:
        tx = an.ds.txns[t]
        return {"txn_id": tx.txn_id, "ts": tx.ts, "sender": tx.sender, "receiver": tx.receiver,
                "amount": tx.amount, "channel": tx.channel}

    def dataset_view() -> dict:
        an = state.analysis
        return {
            "dataset": {**state.dataset, "config_hash": cfg.hash(), "engine": cfg.engine} if state.dataset else None,
            "report": state.report,
            "currency": an.currency if an else None,
            "symbol": an.fmt.symbol if an else None,
            "history_limited": an.history_limited if an else None,
            "establishment_evidence": an.ds.establishment_evidence if an else None,
        }

    def queue_items(an: Analysis, disp: dict) -> list[dict]:
        items, groups = [], {}
        collapsed = an.identity.collapsed_clusters
        for a, r in an.results.items():
            if not r.flagged:
                continue
            q = [k for k, s in r.signals.items() if s.qualifies]
            idsig = r.signals.get("IDENTITY")
            if q == ["IDENTITY"] and idsig and idsig.finding in collapsed:
                g = groups.setdefault(idsig.finding, {"members": [], "r": r})
                g["members"].append(a)
                continue
            items.append({
                "type": "account", "id": a, "score": r.score, "severity": r.severity,
                "status": disp.get(a, {}).get("status", "OPEN"), "patterns": q, "families": r.families,
                "role": an.role(a), "primary_reason": r.primary_reason, "exposure": r.exposure,
                "cases": an.cases.case_of.get(a, []),
            })
        for fid, g in sorted(groups.items()):
            r = g["r"]
            members = sorted(g["members"])
            statuses = {disp.get(m, {}).get("status", "OPEN") for m in members}
            items.append({
                "type": "group", "id": fid, "score": r.score, "severity": r.severity,
                "status": statuses.pop() if len(statuses) == 1 else "MIXED", "patterns": ["IDENTITY"],
                "families": ["IDENTITY"], "role": "CLUSTER_MEMBER", "size": len(members), "members": members,
                "primary_reason": (f"{len(members)} accounts share one IP address; account age unknown, "
                                   "shared network not ruled out (weak evidence)."), "exposure": 0, "cases": [],
            })
        sev = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
        items.sort(key=lambda i: (sev[i["severity"]], -i["score"], -i["exposure"], i["id"]))
        return items

    @app.get("/api/health")
    def health():
        return {"ok": True, "dataset_loaded": state.analysis is not None}

    @app.get("/api/datasets/current")
    def current():
        return dataset_view()

    @app.post("/api/datasets")
    async def upload(file: UploadFile = File(...)):
        data = await file.read()
        if len(data) > cfg.max_upload_bytes:
            raise HTTPException(413, "File too large")
        name = Path(file.filename or "upload.csv").name
        if not name.lower().endswith((".csv", ".txt")):
            raise HTTPException(415, "Please upload a .csv file")
        try:
            state.load(name, data)
        except IngestError as e:
            return JSONResponse(status_code=422, content={"detail": str(e), **e.detail})
        return dataset_view()

    @app.post("/api/datasets/demo")
    def load_demo():
        if not DEMO_CSV.exists():
            raise HTTPException(404, "Demo dataset missing (run: python scripts/make_demo.py)")
        state.load("demo.csv", DEMO_CSV.read_bytes())
        return dataset_view()

    @app.post("/api/reset")
    def reset(body: ResetBody | None = None):
        if not DEMO_CSV.exists():
            raise HTTPException(404, "Demo dataset missing")
        state.load("demo.csv", DEMO_CSV.read_bytes())
        state.store.clear_dispositions(state.dataset["sha256"], (body.analyst if body else "analyst"))
        return dataset_view()

    @app.get("/api/summary")
    def summary():
        an = state.require()
        disp = state.dispositions()
        items = queue_items(an, disp)
        flagged = [r for r in an.results.values() if r.flagged]
        sev = {s: sum(1 for r in flagged if r.severity == s) for s in ("HIGH", "MEDIUM", "LOW")}
        patterns = {p: sum(1 for r in flagged if p in r.signals and r.signals[p].qualifies) for p in PATTERNS}
        status = {s: 0 for s in ("OPEN", "CONFIRMED", "CLEARED")}
        for r in flagged:
            status[disp.get(r.id, {}).get("status", "OPEN")] += 1
        # decisions may be recorded on any account (§10); the queue lists flagged accounts only, so decisions
        # on accounts that are not flagged are reported separately instead of disappearing
        decided_unflagged = [{"id": a, "status": d["status"], "analyst": d.get("analyst"), "at": d.get("updated_at")}
                             for a, d in sorted(disp.items())
                             if d["status"] != "OPEN" and a in an.results and not an.results[a].flagged]
        reviewed = []
        priority = {k: i for i, k in enumerate(REVIEW_KINDS)}
        reviewed_accounts = set()
        seen_infra = set()
        for a in sorted(an.results):
            if an.results[a].flagged:
                continue
            best = None
            for o in an.observations(a):
                if o["kind"] not in priority:
                    continue
                reviewed_accounts.add(a)
                if o["kind"] == "INFRA_ATTRIBUTE" and o["text"] in seen_infra:
                    continue                    # one shared-infrastructure statement is shown once in the preview
                if best is None or priority[o["kind"]] < priority[best["kind"]]:
                    best = o
            if best:
                if best["kind"] == "INFRA_ATTRIBUTE":
                    seen_infra.add(best["text"])
                reviewed.append({"account": a, "kind": best["kind"], "text": best["text"]})
        # interleave kinds so each kind of false-positive defence is visible
        by_kind: dict[str, list] = {}
        for item in sorted(reviewed, key=lambda x: (priority[x["kind"]], x["account"])):
            by_kind.setdefault(item["kind"], []).append(item)
        reviewed = []
        while any(by_kind.values()):
            for k in sorted(by_kind, key=priority.get):
                if by_kind[k]:
                    reviewed.append(by_kind[k].pop(0))
        flagged_cases = [c for c in an.cases.cases if any(an.results[m].flagged for m in c.members)]
        return {
            **dataset_view(),
            "kpis": {
                "accounts": len(an.ds.accounts), "transactions": len(an.ds.txns),
                "flagged": len(flagged), "cases": len(flagged_cases),
                "value_total": sum(t.amount for t in an.ds.txns),
                "exposure": sum(i["exposure"] for i in items),
                "flow_links": len(an.fg.links),
                "time_start": an.ds.start, "time_end": an.ds.end,
            },
            "severity": sev, "patterns": patterns, "pattern_labels": PATTERN_LABELS, "status": status,
            "decided_not_flagged": decided_unflagged,
            # preview: one statement per account, interleaved by kind; total: every not-flagged account with a
            # stated reason, the same accounts the "Not flagged" page lists by default
            "top": items[:6], "reviewed_not_flagged": reviewed[:12], "reviewed_total": len(reviewed_accounts),
            "review_kinds": list(REVIEW_KINDS),
        }

    def filtered_queue(an: Analysis, disp: dict, severity: str | None, status: str | None,
                       pattern: str | None, q: str | None) -> list[dict]:
        """The queue as the analyst filters it; shared by /api/queue and the CSV export."""
        items = queue_items(an, disp)
        if severity:
            items = [i for i in items if i["severity"] in severity.split(",")]
        if status:
            items = [i for i in items if i["status"] in status.split(",")]
        if pattern:
            items = [i for i in items if set(pattern.split(",")) & set(i["patterns"])]
        if q:
            ql = q.lower()
            items = [i for i in items if ql in i["id"].lower() or any(ql in m.lower() for m in i.get("members", []))]
        return items

    @app.get("/api/queue")
    def queue(severity: str | None = None, status: str | None = None, pattern: str | None = None,
              q: str | None = None):
        an = state.require()
        items = filtered_queue(an, state.dispositions(), severity, status, pattern, q)
        return {"items": items, "total": len(items)}

    @app.get("/api/export/queue.csv")
    def export_queue(severity: str | None = None, status: str | None = None, pattern: str | None = None,
                     q: str | None = None):
        an = state.require()
        disp = state.dispositions()
        items = filtered_queue(an, disp, severity, status, pattern, q)
        name = f"muletrace-queue-{state.dataset['sha256'][:12]}-{cfg.hash()}.csv"
        return Response(queue_csv(an, items, disp), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="{name}"'})

    @app.get("/api/search")
    def search(q: str = Query(min_length=1)):
        an = state.require()
        ql = q.lower()
        hits = [a for a in sorted(an.ds.accounts) if ql in a.lower()]
        hits.sort(key=lambda a: (a.lower() != ql, not a.lower().startswith(ql), a))
        return {"items": [{"id": a, "flagged": an.results[a].flagged, "score": an.results[a].score,
                           "severity": an.results[a].severity, "role": an.role(a)} for a in hits[:20]]}

    def signal_view(an: Analysis, sig, r) -> dict:
        txns = an.ds.txns
        idx = sorted(set(sig.txns), key=lambda t: (txns[t].ts, t))
        timeline = []
        last_in = {}
        for t in idx:
            tx = txns[t]
            row = txn_row(an, t)
            if tx.sender in last_in:
                row["dwell_seconds"] = tx.ts - last_in[tx.sender]
            last_in[tx.receiver] = tx.ts
            timeline.append(row)
        from .explain import signal_reason
        return {
            "kind": sig.kind, "label": PATTERN_LABELS[sig.kind], "family": sig.family,
            "raw_tier": TIER_NAMES[sig.raw_tier] if sig.raw_tier is not None else None,
            "final_tier": TIER_NAMES[sig.final_tier] if sig.final_tier is not None else None,
            "qualifies": sig.qualifies, "reason": signal_reason(sig, an.fmt, txns),
            "metrics": _jsonable(sig.metrics), "notes": sig.notes, "finding": sig.finding,
            "timeline": timeline[:SIGNAL_TIMELINE_LIMIT], "timeline_total": len(timeline),
            "path": _path_of(sig, r),
        }

    # Account IDs are free text (they may contain "/", "?", "#"): routes take the encoded ID as a path
    # parameter; the detail route is registered after its sub-routes so it cannot swallow them.
    def account_detail(account: str):
        an = state.require()
        acc = account_or_404(an, account)
        r = an.results[account]
        disp = state.dispositions()
        sha = state.dataset["sha256"]
        return {
            "id": account,
            "profile": {
                "first_seen": acc.first_seen, "last_seen": acc.last_seen,
                "in_count": len(acc.in_txns), "out_count": len(acc.out_txns),
                "in_total": acc.in_total, "out_total": acc.out_total,
                "counterparties": len(acc.counterparties), "created": acc.created,
                "age_days": round(acc.age_days) if acc.age_days is not None else None,
                "establishment": acc.establishment, "establishment_basis": acc.establishment_basis,
                "pooled": acc.pooled, "attributes": {k: sorted(v) for k, v in acc.attrs.items()},
            },
            "flagged": r.flagged, "score": r.score, "severity": r.severity, "families": r.families,
            "exposure": r.exposure, "primary_reason": r.primary_reason,
            "components": [{"family": c.family, "rule": c.rule, "points": c.points, "tier": c.tier,
                            "detail": c.detail, "ref": c.ref} for c in r.components],
            "signals": [signal_view(an, s, r) for s in r.signals.values()],
            "role": an.role(account), "cases": an.cases.case_of.get(account, []),
            "indicator": indicator_view(account, an),
            "chain": _path_json(an, r.chain), "corroborated": _path_json(an, r.corroborated),
            "observations": an.observations(account),
            "disposition": disp.get(account, {"status": "OPEN"}),
            "audit": state.store.audit(sha, account),
        }

    @app.get("/api/accounts/{account:path}/transactions")
    def account_txns(account: str, limit: int = 500):
        an = state.require()
        acc = account_or_404(an, account)
        susp = net.suspicious_txns(an)
        rows = []
        for t in sorted(acc.in_txns + acc.out_txns, key=lambda t: (an.ds.txns[t].ts, t))[-limit:]:
            row = txn_row(an, t)
            row["direction"] = "in" if an.ds.txns[t].receiver == account else "out"
            row["suspicious"] = t in susp
            rows.append(row)
        return {"items": rows, "total": len(acc.in_txns) + len(acc.out_txns)}

    @app.get("/api/accounts/{account:path}/network")
    def account_network(account: str, hops: int = 1, min_amount: int = 0, suspicious_only: bool = False):
        an = state.require()
        account_or_404(an, account)
        return net.network(an, account, hops, min_amount, suspicious_only, state.dispositions())

    @app.get("/api/accounts/{account:path}/trace")
    def account_trace(account: str, dir: str = "fwd"):
        an = state.require()
        account_or_404(an, account)
        if dir not in ("fwd", "back"):
            raise HTTPException(400, "dir must be fwd or back")
        return net.trace_view(an, account, dir, state.dispositions())

    app.get("/api/accounts/{account:path}")(account_detail)

    @app.get("/api/cases")
    def case_list():
        """The cases that contain a flagged account (the Overview "Suspicious cases" count), as a read-only view
        of the analysis. Severity is the highest severity among the case's flagged members (no case score);
        order: that severity, cases whose flagged members are not all confirmed first, then case order."""
        an = state.require()
        disp = state.dispositions()
        sev_rank = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
        items = []
        for pos, c in enumerate(an.cases.cases):
            if c.id not in an.flagged_cases:
                continue
            status = {m: disp.get(m, {}).get("status", "OPEN") for m in c.members}
            flagged = [m for m in c.members if an.results[m].flagged]
            confirmed_flagged = sum(1 for m in flagged if status[m] == "CONFIRMED")
            items.append((pos, {
                "id": c.id,
                "severity": min((an.results[m].severity for m in flagged), key=sev_rank.get),
                "severity_counts": {s: sum(1 for m in flagged if an.results[m].severity == s) for s in sev_rank},
                "accounts": len(c.members), "flagged": len(flagged), "origins": len(c.origins),
                "metrics": c.metrics, "families": sorted({f for m in c.members for f in an.results[m].families}),
                "confirmed": sum(1 for m in c.members if status[m] == "CONFIRMED"),
                "confirmed_flagged": confirmed_flagged,
                "decided_not_flagged": sum(1 for m in c.members if not an.results[m].flagged and status[m] != "OPEN"),
                "fully_confirmed": confirmed_flagged == len(flagged),
            }))
        items.sort(key=lambda pi: (sev_rank[pi[1]["severity"]], pi[1]["fully_confirmed"], pi[0]))
        return {"items": [i for _, i in items], "total": len(items),
                "unflagged_cases": len(an.cases.cases) - len(items)}

    @app.get("/api/cases/{case_id}")
    def case_detail(case_id: str, member: str | None = None):
        an = state.require()
        try:
            c = an.cases.case(case_id)
        except StopIteration:
            raise HTTPException(404, f"Unknown case {case_id}")
        disp = state.dispositions()
        fams = sorted({f for m in c.members for f in an.results[m].families})
        # §7.2: a flow nobody was flagged for does not label its participants — case roles and origins only
        # for a case with a flagged member; otherwise the per-account rule (pooled, cluster member) applies
        labelled = c.id in an.flagged_cases
        role_of = c.roles.get if labelled else an.role
        members = [{"id": m, "role": role_of(m), "score": an.results[m].score,
                    "severity": an.results[m].severity, "flagged": an.results[m].flagged,
                    "status": disp.get(m, {}).get("status", "OPEN")} for m in c.members]
        role_order = {"ORIGIN": 0, "HUB": 1, "COLLECTOR": 2, "DISTRIBUTOR": 3, "RELAY": 4, "POOLED": 5,
                      "SINK": 6, "COUNTERPARTY": 7}
        members.sort(key=lambda m: (role_order.get(m["role"], 9), -m["score"], m["id"]))
        # the timeline is bounded; `timeline_total` says how many case transactions there are, and `member`
        # narrows it to the case transactions of one member (so a selected member's flows are never cut off)
        if member is not None and member not in c.members:
            raise HTTPException(404, f"{member} is not a member of {case_id}")
        edges = c.edges if member is None else [t for t in c.edges
                                                 if member in (an.ds.txns[t].sender, an.ds.txns[t].receiver)]
        timeline = [txn_row(an, t) for t in sorted(edges, key=lambda t: (an.ds.txns[t].ts, t))]
        metrics = c.metrics if labelled else {**c.metrics, "value_from_origins": None}
        return {"id": c.id, "members": members, "metrics": metrics, "families": fams,
                "origins": c.origins if labelled else [], "timeline": timeline[:CASE_TIMELINE_LIMIT],
                "timeline_total": len(timeline), "timeline_member": member,
                "confirmed": sum(1 for m in members if m["status"] == "CONFIRMED"),
                "confirmed_flagged": sum(1 for m in members if m["flagged"] and m["status"] == "CONFIRMED"),
                "decided_not_flagged": sum(1 for m in members if not m["flagged"] and m["status"] != "OPEN"),
                "flagged": sum(1 for m in members if m["flagged"])}

    @app.get("/api/cases/{case_id}/network")
    def case_network(case_id: str):
        an = state.require()
        try:
            c = an.cases.case(case_id)
        except StopIteration:
            raise HTTPException(404, f"Unknown case {case_id}")
        return net.case_network(an, c, state.dispositions())

    @app.get("/api/cases/{case_id}/summary")
    def case_summary_view(case_id: str):
        an = state.require()
        try:
            c = an.cases.case(case_id)
        except StopIteration:
            raise HTTPException(404, f"Unknown case {case_id}")
        return case_summary(an, c)

    @app.get("/api/observations")
    def observations(kind: str | None = None, flagged: bool | None = None, q: str | None = None,
                     limit: int = Query(200, ge=1, le=5000), offset: int = Query(0, ge=0)):
        """Considered-but-not-scored activity. `kind` is a comma list; `counts` are per kind before
        the kind filter, so the UI can show every available reason alongside the filtered list."""
        an = state.require()
        disp = state.dispositions()
        kinds = set(kind.split(",")) if kind else None
        ql = q.lower() if q else None
        out, counts = [], {}
        for a in sorted(an.results):
            r = an.results[a]
            if flagged is not None and r.flagged != flagged:
                continue
            if ql and ql not in a.lower():
                continue
            for o in an.observations(a):
                counts[o["kind"]] = counts.get(o["kind"], 0) + 1
                if kinds and o["kind"] not in kinds:
                    continue
                out.append({"account": a, "flagged": r.flagged, "severity": r.severity, "score": r.score,
                            "role": an.role(a), "status": disp.get(a, {}).get("status", "OPEN"), **o})
        return {"items": out[offset:offset + limit], "total": len(out), "counts": counts}

    @app.post("/api/accounts/{account:path}/disposition")
    def disposition(account: str, body: DispositionBody):
        an = state.require()
        account_or_404(an, account)
        try:
            d = state.store.set_disposition(state.dataset["sha256"], account, body.status.upper(),
                                            body.note.strip()[:1000], body.analyst.strip()[:80] or "analyst")
        except ValueError as e:
            raise HTTPException(400, str(e))
        return {"disposition": d, "audit": state.store.audit(state.dataset["sha256"], account)}

    @app.get("/api/config")
    def config():
        return {"config": cfg.as_dict(), "hash": cfg.hash(), "engine": cfg.engine}

    if DIST.exists():
        app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            target = DIST / path
            if path and target.is_file() and DIST in target.resolve().parents:
                return FileResponse(target)
            return FileResponse(DIST / "index.html")

    return app


def _path_of(sig, r) -> list[str]:
    m = sig.metrics
    if sig.kind == "ROUND_TRIP":
        return m.get("cycle", [])
    if sig.kind == "LAYERED_RECEIPT":
        return m.get("path_accounts", [])
    if sig.kind == "RELAY":
        p = r.corroborated or r.chain
        return p["accounts"] if p else []
    return []


def _path_json(an: Analysis, p: dict | None) -> dict | None:
    if not p:
        return None
    return {"accounts": p["accounts"], "txn_ids": [an.ds.txns[t].txn_id for t in p["txns"]], "span": p["span"]}


def _jsonable(x):
    if isinstance(x, dict):
        return {k: _jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple, set)):
        return [_jsonable(v) for v in x]
    if hasattr(x, "numerator") and not isinstance(x, (int, bool)):
        return float(x)
    return x


QUEUE_CSV_COLUMNS = ["rank", "type", "id", "members", "severity", "score", "patterns", "families", "role",
                     "cases", "exposure", "currency", "exposure_display", "primary_reason",
                     "decision", "decision_analyst", "decision_note", "decision_at_utc"]
_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def csv_safe(value):
    """Text that a spreadsheet would evaluate as a formula is prefixed with an apostrophe."""
    if isinstance(value, str) and value.startswith(_FORMULA_START):
        return "'" + value
    return value


def queue_csv(an: Analysis, items: list[dict], disp: dict) -> bytes:
    """Queue rows in queue order; UTF-8 with BOM so spreadsheet tools read the currency symbol."""
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow(QUEUE_CSV_COLUMNS)
    for rank, i in enumerate(items, start=1):
        d = disp.get(i["id"], {}) if i["type"] == "account" else {}
        at = d.get("updated_at")
        row = [
            rank, i["type"], i["id"], "; ".join(i.get("members", [])), i["severity"], i["score"],
            "; ".join(PATTERN_LABELS.get(p, p) for p in i["patterns"]), "; ".join(i["families"]),
            i["role"] or "", "; ".join(i["cases"]),
            Decimal(i["exposure"]).scaleb(-2), an.currency, an.fmt.money(i["exposure"]) if i["exposure"] else "",
            i["primary_reason"], i["status"], d.get("analyst") or "", d.get("note") or "",
            datetime.fromtimestamp(at, timezone.utc).strftime("%Y-%m-%d %H:%M:%S") if at else "",
        ]
        w.writerow([csv_safe(v) for v in row])
    return ("\ufeff" + buf.getvalue()).encode("utf-8")


def build_with_engine(engine: str) -> Config:
    return replace(DEFAULT, engine=engine)
